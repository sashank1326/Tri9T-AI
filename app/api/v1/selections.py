from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.sqlite import get_db
from app.schemas.selection import SelectionCreateRequest, SelectionResponse
from app.services.selection_service import SelectionService

router = APIRouter(prefix="/selections", tags=["Selections"])


@router.post(
    "",
    response_model=SelectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create version-pinned document selection"
)
def create_selection(req: SelectionCreateRequest, db: Session = Depends(get_db)):
    """
    Select document sections and save them with their exact version ID
    and content hash. Original text snapshot remains immutable across future uploads.
    """
    service = SelectionService(db)
    return service.create_selection(req)


@router.get(
    "/{selection_id}",
    response_model=SelectionResponse,
    summary="Retrieve a selection by ID"
)
def get_selection(selection_id: str, db: Session = Depends(get_db)):
    """Retrieve selection details including pinned version, content snapshot, and hash."""
    service = SelectionService(db)
    return service.get_selection(selection_id)


@router.get(
    "",
    response_model=List[SelectionResponse],
    summary="List document selections"
)
def list_selections(
    document_id: Optional[str] = Query(None, description="Filter selections by document ID"),
    db: Session = Depends(get_db)
):
    """List all saved selections, optionally filtered by document."""
    service = SelectionService(db)
    return service.list_selections(document_id)
