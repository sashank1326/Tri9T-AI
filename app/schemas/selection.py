from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SelectionCreateRequest(BaseModel):
    document_id: str = Field(..., description="Target document identifier")
    version_id: str = Field(..., description="Target version identifier to pin")
    node_ids: List[str] = Field(..., min_length=1, description="List of node IDs included in the selection")
    title: str = Field(..., min_length=1, max_length=255, description="Selection title or label")
    description: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class SelectionResponse(BaseModel):
    id: str
    document_id: str
    version_id: str
    version_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    node_ids: List[str]
    pinned_content_snapshot: str
    content_hash: str
    tags: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}
