import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DocumentNotFoundError,
    VersionNotFoundError,
    NodeNotFoundError,
    SelectionNotFoundError
)
from app.core.hashing import compute_text_hash
from app.db.models import Document, DocumentVersion, DocumentNode, VersionPinnedSelection
from app.schemas.selection import SelectionCreateRequest, SelectionResponse

logger = logging.getLogger(__name__)


class SelectionService:
    """Service managing version-pinned selections with immutable content snapshots."""

    def __init__(self, db: Session):
        self.db = db

    def create_selection(self, req: SelectionCreateRequest) -> SelectionResponse:
        """
        Create a version-pinned selection capturing the exact text snapshot
        and content hash at the specified version.
        """
        # Validate Document
        doc = self.db.query(Document).filter(Document.id == req.document_id).first()
        if not doc:
            raise DocumentNotFoundError(req.document_id)

        # Validate Version
        version = self.db.query(DocumentVersion).filter(
            DocumentVersion.document_id == req.document_id,
            (DocumentVersion.id == req.version_id) | (DocumentVersion.version_name == req.version_id)
        ).first()
        if not version:
            raise VersionNotFoundError(req.document_id, req.version_id)

        # Fetch selected nodes strictly from this version
        nodes = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == version.id,
            DocumentNode.id.in_(req.node_ids)
        ).order_by(DocumentNode.order_index).all()

        if not nodes:
            raise NodeNotFoundError(
                f"None of the provided node IDs {req.node_ids} exist in document '{req.document_id}' version '{version.version_name}'."
            )

        # Build concatenated content snapshot
        snapshot_parts = []
        for n in nodes:
            prefix = f"[{n.title}] " if n.title else ""
            snapshot_parts.append(f"{prefix}{n.content}")

        pinned_snapshot = "\n\n".join(snapshot_parts)
        content_hash = compute_text_hash(pinned_snapshot)

        # Persist selection
        selection = VersionPinnedSelection(
            document_id=doc.id,
            version_id=version.id,
            title=req.title,
            description=req.description,
            node_ids_json=json.dumps(req.node_ids),
            pinned_content_snapshot=pinned_snapshot,
            content_hash=content_hash,
            tags_json=json.dumps(req.tags or [])
        )
        self.db.add(selection)
        self.db.commit()
        self.db.refresh(selection)

        return SelectionResponse(
            id=selection.id,
            document_id=selection.document_id,
            version_id=selection.version_id,
            version_name=version.version_name,
            title=selection.title,
            description=selection.description,
            node_ids=selection.get_node_ids(),
            pinned_content_snapshot=selection.pinned_content_snapshot,
            content_hash=selection.content_hash,
            tags=selection.get_tags(),
            created_at=selection.created_at
        )

    def get_selection(self, selection_id: str) -> SelectionResponse:
        """Retrieve a version-pinned selection by ID."""
        selection = self.db.query(VersionPinnedSelection).filter(
            VersionPinnedSelection.id == selection_id
        ).first()
        if not selection:
            raise SelectionNotFoundError(selection_id)

        version = self.db.query(DocumentVersion).filter(
            DocumentVersion.id == selection.version_id
        ).first()

        return SelectionResponse(
            id=selection.id,
            document_id=selection.document_id,
            version_id=selection.version_id,
            version_name=version.version_name if version else None,
            title=selection.title,
            description=selection.description,
            node_ids=selection.get_node_ids(),
            pinned_content_snapshot=selection.pinned_content_snapshot,
            content_hash=selection.content_hash,
            tags=selection.get_tags(),
            created_at=selection.created_at
        )

    def list_selections(self, document_id: Optional[str] = None) -> List[SelectionResponse]:
        """List selections, optionally filtered by document ID."""
        query = self.db.query(VersionPinnedSelection)
        if document_id:
            query = query.filter(VersionPinnedSelection.document_id == document_id)

        selections = query.order_by(VersionPinnedSelection.created_at.desc()).all()
        results = []
        for s in selections:
            version = self.db.query(DocumentVersion).filter(
                DocumentVersion.id == s.version_id
            ).first()
            results.append(SelectionResponse(
                id=s.id,
                document_id=s.document_id,
                version_id=s.version_id,
                version_name=version.version_name if version else None,
                title=s.title,
                description=s.description,
                node_ids=s.get_node_ids(),
                pinned_content_snapshot=s.pinned_content_snapshot,
                content_hash=s.content_hash,
                tags=s.get_tags(),
                created_at=s.created_at
            ))
        return results
