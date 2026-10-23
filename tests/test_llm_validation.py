import json
import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from app.schemas.test_case import QATestCaseItem, GeminiTestCaseOutput
from app.services.llm_service import LLMService
from app.core.exceptions import LLMGenerationError
from app.db.mongo import get_test_cases_collection, get_generations_collection


def make_sample_test_case(tc_id: str) -> dict:
    return {
        "test_case_id": tc_id,
        "title": f"Test Case {tc_id}",
        "description": "Verification of safety interlock switch",
        "type": "safety",
        "preconditions": ["System is in idle state"],
        "steps": ["Trigger emergency stop", "Record cutoff delay"],
        "expected_results": ["Power cuts off within 20 ms"],
        "severity": "critical",
        "traceability": {"section": "2.2 Safety"}
    }


def test_pydantic_valid_gemini_output():
    """Verify GeminiTestCaseOutput validates valid payload with 3-5 test cases."""
    payload = {
        "test_cases": [make_sample_test_case(f"TC-00{i}") for i in range(1, 5)]
    }
    validated = GeminiTestCaseOutput.model_validate(payload)
    assert len(validated.test_cases) == 4
    assert validated.test_cases[0].test_case_id == "TC-001"


def test_pydantic_rejects_fewer_than_3_test_cases():
    """Verify validation fails when fewer than 3 test cases are provided."""
    payload = {
        "test_cases": [make_sample_test_case("TC-001"), make_sample_test_case("TC-002")]
    }
    with pytest.raises(ValidationError) as exc:
        GeminiTestCaseOutput.model_validate(payload)
    assert "between 3 and 5" in str(exc.value)


def test_pydantic_rejects_more_than_5_test_cases():
    """Verify validation fails when more than 5 test cases are provided."""
    payload = {
        "test_cases": [make_sample_test_case(f"TC-00{i}") for i in range(1, 7)]
    }
    with pytest.raises(ValidationError) as exc:
        GeminiTestCaseOutput.model_validate(payload)
    assert "between 3 and 5" in str(exc.value)


def test_pydantic_rejects_empty_steps():
    """Verify validation fails when test case steps are empty."""
    bad_tc = make_sample_test_case("TC-001")
    bad_tc["steps"] = []
    with pytest.raises(ValidationError):
        QATestCaseItem.model_validate(bad_tc)


def test_clean_and_parse_json_with_code_fences():
    """Verify clean_and_parse_json successfully extracts JSON from markdown fences."""
    llm = LLMService(use_mock=True)
    raw = '```json\n{"test_cases": []}\n```'
    parsed = llm._clean_and_parse_json(raw)
    assert parsed == {"test_cases": []}


def test_clean_and_parse_json_malformed():
    """Verify clean_and_parse_json raises LLMGenerationError on malformed JSON."""
    llm = LLMService(use_mock=True)
    raw = '{"test_cases": [incomplete json...'
    with pytest.raises(LLMGenerationError) as exc:
        llm._clean_and_parse_json(raw)
    assert "malformed JSON" in str(exc.value)


def test_llm_service_mongo_persistence():
    """Verify test cases and source snapshot are persisted to MongoDB."""
    llm = LLMService(use_mock=True)
    source_req = "The generator maximum tube voltage shall not exceed 120 kV."

    res = llm.generate_test_cases(
        source_text=source_req,
        document_id="CT-200-DOC",
        source_version_id="ver-1",
        source_version_name="v1",
        selection_id="sel-1",
        num_test_cases=3
    )

    assert len(res.test_cases) == 3

    # Check MongoDB generations collection
    gen_col = get_generations_collection()
    gen_rec = gen_col.find_one({"generation_id": res.generation_id})
    assert gen_rec is not None
    assert gen_rec["source_snapshot"] == source_req
    assert gen_rec["source_hash"] == res.source_hash

    # Check MongoDB test_cases collection
    tc_col = get_test_cases_collection()
    tcs = list(tc_col.find({"generation_id": res.generation_id}))
    assert len(tcs) == 3
    assert tcs[0]["source_snapshot"] == source_req


def test_gemini_api_error_handling():
    """Verify API errors are handled and re-raised as LLMGenerationError."""
    llm = LLMService(use_mock=False)
    with patch.object(llm, "_get_gemini_client") as mock_client:
        mock_models = MagicMock()
        mock_models.generate_content.side_effect = RuntimeError("Network timeout contacting Google Gemini API")
        mock_client.return_value.models = mock_models

        with pytest.raises(LLMGenerationError) as exc:
            llm._call_gemini_api("Some requirement", 3)
        assert "Gemini API failure" in str(exc.value)
