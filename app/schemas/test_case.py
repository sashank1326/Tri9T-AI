from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class StalenessStatusEnum(str, Enum):
    UP_TO_DATE = "UP_TO_DATE"
    STALE_MODIFIED = "STALE_MODIFIED"
    STALE_DELETED = "STALE_DELETED"
    ORPHANED = "ORPHANED"


class QATestCaseItem(BaseModel):
    test_case_id: str = Field(..., description="Unique identifier for the test case, e.g. TC-001")
    title: str = Field(..., min_length=3, description="Descriptive title of the test case")
    description: str = Field(..., min_length=5, description="Objective and scope of this test case")
    type: str = Field(
        default="functional",
        description="Type: functional, safety, boundary, performance, regulatory"
    )
    preconditions: List[str] = Field(default_factory=list, description="Initial preconditions required")
    steps: List[str] = Field(..., min_length=1, description="Sequential testing steps")
    expected_results: List[str] = Field(..., min_length=1, description="Expected observable outcomes")
    severity: str = Field(
        default="high",
        description="Severity: critical, high, medium, low"
    )
    traceability: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Links to medical requirement, quotes, or node IDs"
    )

    @field_validator("steps", "expected_results")
    @classmethod
    def validate_non_empty_lists(cls, v: List[str]) -> List[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        if not cleaned:
            raise ValueError("Steps and expected results cannot be empty.")
        return cleaned


class GeminiTestCaseOutput(BaseModel):
    test_cases: List[QATestCaseItem] = Field(
        ...,
        description="List of 3 to 5 validated medical document QA test cases"
    )

    @field_validator("test_cases")
    @classmethod
    def validate_count(cls, v: List[QATestCaseItem]) -> List[QATestCaseItem]:
        if len(v) < 3 or len(v) > 5:
            raise ValueError(f"Expected between 3 and 5 test cases, got {len(v)}.")
        return v


class GenerateTestCasesRequest(BaseModel):
    selection_id: Optional[str] = Field(None, description="ID of a version-pinned selection")
    document_id: Optional[str] = Field(None, description="Document ID if specifying nodes directly")
    version_id: Optional[str] = Field(None, description="Version ID if specifying nodes directly")
    node_ids: Optional[List[str]] = Field(None, description="Specific node IDs if selection_id is omitted")
    custom_text: Optional[str] = Field(None, description="Direct text input for test generation")
    num_test_cases: int = Field(default=4, ge=3, le=5, description="Target number of test cases (3-5)")


class StalenessReport(BaseModel):
    overall_status: StalenessStatusEnum
    is_stale: bool
    source_version_id: str
    source_version_name: str
    target_version_id: str
    target_version_name: str
    source_content_hash: str
    target_content_hash: Optional[str] = None
    diff_summary: Optional[str] = None
    unified_diff: Optional[str] = None
    affected_nodes: List[str] = []
    explanation: str


class GenerationBatchResponse(BaseModel):
    generation_id: str
    selection_id: Optional[str] = None
    document_id: str
    source_version_id: str
    source_version_name: str
    source_snapshot: str
    source_hash: str
    model_name: str
    node_ids: List[str] = []
    test_cases: List[QATestCaseItem]
    staleness: Optional[StalenessReport] = None
    generated_at: datetime
