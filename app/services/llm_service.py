import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.config import get_settings
from app.core.exceptions import LLMGenerationError
from app.core.hashing import compute_text_hash
from app.db.mongo import get_generations_collection, get_test_cases_collection
from app.schemas.test_case import (
    QATestCaseItem,
    GeminiTestCaseOutput,
    GenerationBatchResponse
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Medical Device QA & Verification Engineer adhering to ISO 13485, IEC 62304, and FDA CDRH design control principles.
Analyze the provided medical manual requirements text and generate between 3 and 5 rigorous, clinically relevant QA test cases.

Each test case must include:
- test_case_id: Sequential ID, e.g., "TC-001"
- title: Concise, descriptive title
- description: Verification objective and medical safety purpose
- type: One of "functional", "safety", "boundary", "performance", "regulatory"
- preconditions: Clear initial device states / prerequisites
- steps: Actionable, step-by-step verification instructions
- expected_results: Explicit, measurable passing criteria
- severity: One of "critical", "high", "medium", "low"
- traceability: Dictionary containing "requirement_quote" (verbatim quote from source text) and "section_title"

Return strictly valid JSON adhering to the specified schema with exactly 3 to 5 test cases. Do not include markdown code fences or conversational text."""


class LLMService:
    """Service for generating medical document QA test cases using Gemini API and storing them in MongoDB."""

    def __init__(self, use_mock: bool = False):
        self.settings = get_settings()
        self.use_mock = use_mock or (self.settings.GEMINI_API_KEY in (None, "", "mock-or-dev-key"))
        self._client = None

    def _get_gemini_client(self):
        if self._client is None:
            if not self.settings.GEMINI_API_KEY:
                raise LLMGenerationError("GEMINI_API_KEY environment variable is not configured.")
            from google import genai
            self._client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        return self._client

    def generate_test_cases(
        self,
        source_text: str,
        document_id: str,
        source_version_id: str,
        source_version_name: str,
        selection_id: Optional[str] = None,
        node_ids: Optional[List[str]] = None,
        num_test_cases: int = 4
    ) -> GenerationBatchResponse:
        """
        Generate 3-5 QA test cases from source document text, validate with Pydantic,
        and persist generation batch and individual test cases in MongoDB.
        """
        source_text = (source_text or "").strip()
        if not source_text:
            raise LLMGenerationError("Source text for test-case generation cannot be empty.")

        source_hash = compute_text_hash(source_text)
        generation_id = str(uuid.uuid4())
        node_ids = node_ids or []

        # Execute generation (Mock or Real Gemini API)
        if self.use_mock:
            logger.info("Generating test cases using Mock Gemini engine.")
            output = self._mock_gemini_response(source_text, num_test_cases)
            raw_text = json.dumps(output.model_dump())
        else:
            logger.info("Calling live Gemini API (%s) for test case generation.", self.settings.GEMINI_MODEL)
            output, raw_text = self._call_gemini_api(source_text, num_test_cases)

        now = datetime.now(timezone.utc)

        # 1. Save generation batch in MongoDB
        generations_col = get_generations_collection()
        gen_doc = {
            "_id": generation_id,
            "generation_id": generation_id,
            "selection_id": selection_id,
            "document_id": document_id,
            "source_version_id": source_version_id,
            "source_version_name": source_version_name,
            "source_snapshot": source_text,
            "source_hash": source_hash,
            "node_ids": node_ids,
            "model_name": self.settings.GEMINI_MODEL if not self.use_mock else "mock-gemini-3.8-flash",
            "test_cases": [tc.model_dump() for tc in output.test_cases],
            "raw_response": raw_text,
            "generated_at": now.isoformat()
        }
        generations_col.insert_one(gen_doc)

        # 2. Save individual test cases in MongoDB for direct retrieval
        test_cases_col = get_test_cases_collection()
        for idx, tc in enumerate(output.test_cases):
            tc_doc = tc.model_dump()
            tc_mongo = {
                "_id": f"{generation_id}_{tc.test_case_id}",
                "test_case_id": tc.test_case_id,
                "generation_id": generation_id,
                "selection_id": selection_id,
                "document_id": document_id,
                "source_version_id": source_version_id,
                "source_version_name": source_version_name,
                "source_node_ids": node_ids,
                "source_content_hash": source_hash,
                "source_snapshot": source_text,
                **tc_doc,
                "created_at": now.isoformat()
            }
            test_cases_col.insert_one(tc_mongo)

        return GenerationBatchResponse(
            generation_id=generation_id,
            selection_id=selection_id,
            document_id=document_id,
            source_version_id=source_version_id,
            source_version_name=source_version_name,
            source_snapshot=source_text,
            source_hash=source_hash,
            model_name=self.settings.GEMINI_MODEL if not self.use_mock else "mock-gemini-3.8-flash",
            node_ids=node_ids,
            test_cases=output.test_cases,
            staleness=None,
            generated_at=now
        )

    def _call_gemini_api(self, source_text: str, num_test_cases: int) -> tuple[GeminiTestCaseOutput, str]:
        """Invoke Gemini API using google-genai SDK with structured output validation."""
        try:
            client = self._get_gemini_client()
            from google.genai import types

            prompt = (
                f"Source Requirement Specification:\n"
                f"\"\"\"\n{source_text}\n\"\"\"\n\n"
                f"Generate exactly {num_test_cases} comprehensive medical verification test cases."
            )

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=GeminiTestCaseOutput.model_json_schema(),
                temperature=0.2
            )

            response = client.models.generate_content(
                model=self.settings.GEMINI_MODEL,
                contents=prompt,
                config=config
            )

            raw_text = response.text or ""
            parsed_data = self._clean_and_parse_json(raw_text)
            validated = GeminiTestCaseOutput.model_validate(parsed_data)
            return validated, raw_text

        except LLMGenerationError:
            raise
        except Exception as exc:
            logger.error("Gemini API call failed: %s", str(exc), exc_info=True)
            raise LLMGenerationError(f"Gemini API failure: {str(exc)}") from exc

    def _clean_and_parse_json(self, raw_text: str) -> dict:
        """Strip markdown code fences and parse JSON robustly."""
        cleaned = raw_text.strip()
        # Remove markdown fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
            cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Malformed JSON received from LLM: %s", raw_text)
            raise LLMGenerationError(
                f"LLM returned malformed JSON: {str(exc)}",
                details={"raw_output": raw_text[:500]}
            ) from exc

    def _mock_gemini_response(self, source_text: str, count: int = 4) -> GeminiTestCaseOutput:
        """Generate high-fidelity synthetic QA test cases for deterministic offline testing."""
        count = max(3, min(5, count))
        # Extract a short quote from the source text
        snippet = source_text[:120].replace("\n", " ").strip()

        test_cases = [
            QATestCaseItem(
                test_case_id="TC-001",
                title="Verify Operational Normal Limits and Boundary Tolerance",
                description="Validate that the medical device operates accurately within specified power and voltage limits under standard clinical load.",
                type="boundary",
                preconditions=[
                    "Device connected to calibrated power supply",
                    "Calibration diagnostic tool connected to service port"
                ],
                steps=[
                    "Power on the device in service verification mode",
                    "Increment voltage to 90% of maximum specified threshold",
                    "Record output sensor readings every 10 seconds for 5 minutes",
                    "Verify thermal sensor readout remains within nominal operating envelope"
                ],
                expected_results=[
                    "All sensor readings remain within +/- 1.5% specified tolerance",
                    "No overload or warning flags are triggered in the system log"
                ],
                severity="critical",
                traceability={
                    "requirement_quote": snippet,
                    "section_title": "System Specifications"
                }
            ),
            QATestCaseItem(
                test_case_id="TC-002",
                title="Emergency Interlock and Fail-Safe Shutdown Verification",
                description="Ensure the emergency shutdown mechanism triggers within required latency bounds when interlock circuit is broken.",
                type="safety",
                preconditions=[
                    "System actively executing standard scan simulation",
                    "Digital oscilloscope attached to emergency stop circuit"
                ],
                steps=[
                    "Initiate continuous operational cycle",
                    "Depress emergency stop button or simulate interlock breach",
                    "Measure time delta between contact break and total subsystem power cutoff"
                ],
                expected_results=[
                    "All radiation and high-voltage generation ceases in less than 20 milliseconds",
                    "Safety interlock trip event is logged in persistent non-volatile memory"
                ],
                severity="critical",
                traceability={
                    "requirement_quote": snippet,
                    "section_title": "Safety Protections"
                }
            ),
            QATestCaseItem(
                test_case_id="TC-003",
                title="Continuous Duty Cycle and Thermal Regulation Test",
                description="Verify thermal equilibrium and acoustic alarm alert thresholds during sustained continuous duty cycles.",
                type="performance",
                preconditions=[
                    "Ambient room temperature stabilized at 22°C +/- 2°C",
                    "Thermal monitoring sensors installed on tube housing"
                ],
                steps=[
                    "Execute 10 back-to-back full acquisition sequence simulations",
                    "Monitor gantry temperature telemetry at 1-minute intervals",
                    "Check cooling fan activation profile and tachometer feedback"
                ],
                expected_results=[
                    "Gantry temperature does not exceed 65°C threshold",
                    "Cooling fans modulate proportional to heat exchanger thermistor readings"
                ],
                severity="high",
                traceability={
                    "requirement_quote": snippet,
                    "section_title": "Operating Conditions"
                }
            ),
            QATestCaseItem(
                test_case_id="TC-004",
                title="Regulatory Labeling and User Interface Warning Consistency",
                description="Verify that required IEC 60601 hazard warnings and regulatory compliance notices appear as specified.",
                type="regulatory",
                preconditions=[
                    "Operator console booted to primary clinical interface"
                ],
                steps=[
                    "Navigate to system status and tube warm-up menu",
                    "Inspect on-screen radiation hazard iconography and warning text strings",
                    "Cross-reference displayed text against medical specification requirements"
                ],
                expected_results=[
                    "Required yellow warning triangle symbol is clearly visible and unoccluded",
                    "Warning text matches specification verbatim without truncation"
                ],
                severity="medium",
                traceability={
                    "requirement_quote": snippet,
                    "section_title": "Regulatory Compliance"
                }
            )
        ]

        return GeminiTestCaseOutput(test_cases=test_cases[:count])
