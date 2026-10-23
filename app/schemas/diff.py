from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class NodeDiffStatus(str, Enum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"


class NodeDiffItem(BaseModel):
    section_path: str
    node_type: str
    title: Optional[str] = None
    status: NodeDiffStatus
    node_id_v1: Optional[str] = None
    node_id_v2: Optional[str] = None
    content_hash_v1: Optional[str] = None
    content_hash_v2: Optional[str] = None
    changes_summary: Optional[str] = None
    unified_diff: Optional[str] = None
    content_v1: Optional[str] = None
    content_v2: Optional[str] = None


class VersionDiffSummary(BaseModel):
    unchanged_count: int = 0
    modified_count: int = 0
    added_count: int = 0
    deleted_count: int = 0
    total_nodes_v1: int = 0
    total_nodes_v2: int = 0


class DocumentCompareResponse(BaseModel):
    document_id: str
    v1_version_id: str
    v1_version_name: str
    v2_version_id: str
    v2_version_name: str
    summary: VersionDiffSummary
    node_diffs: List[NodeDiffItem]
