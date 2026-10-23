from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class NodeBase(BaseModel):
    node_type: str = Field(..., description="heading, section, subsection, paragraph, list, table, figure")
    title: Optional[str] = None
    section_number: Optional[str] = None
    section_path: str
    content: str
    level: int = 0
    order_index: int = 0
    page_number: int = 1
    bounding_box: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


class NodeResponse(NodeBase):
    id: str
    version_id: str
    parent_id: Optional[str] = None
    content_hash: str

    model_config = {"from_attributes": True}


class NodeTreeNode(NodeResponse):
    children: List[NodeTreeNode] = []

    model_config = {"from_attributes": True}


class SectionSummary(BaseModel):
    id: str
    title: Optional[str] = None
    section_number: Optional[str] = None
    section_path: str
    level: int
    page_number: int
    children_count: int = 0


class DocumentVersionResponse(BaseModel):
    id: str
    document_id: str
    version_name: str
    file_name: str
    file_hash: str
    page_count: int
    root_hash: Optional[str] = None
    created_at: datetime
    node_count: Optional[int] = 0

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: List[DocumentVersionResponse] = []

    model_config = {"from_attributes": True}


class DocumentSearchResult(BaseModel):
    node_id: str
    version_id: str
    version_name: str
    node_type: str
    title: Optional[str] = None
    section_path: str
    page_number: int
    content_snippet: str
    content_hash: str
    relevance_score: float = 1.0


class DocumentSearchResponse(BaseModel):
    query: str
    document_id: str
    version_id: str
    total_matches: int
    results: List[DocumentSearchResult]
