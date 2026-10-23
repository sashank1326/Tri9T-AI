from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, Query, status
from sqlalchemy.orm import Session

from app.db.sqlite import get_db
from app.db.models import DocumentVersion
from app.core.exceptions import VersionNotFoundError
from app.schemas.document import (
    DocumentResponse,
    DocumentVersionResponse,
    NodeResponse,
    NodeTreeNode,
    SectionSummary,
    DocumentSearchResponse
)
from app.schemas.diff import DocumentCompareResponse, NodeChangeResponse
from app.services.document_service import DocumentService
from app.services.version_service import VersionService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/ingest",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a PDF document version"
)
async def ingest_document(
    document_id: str = Form(..., description="Unique document key, e.g. CT-200-MANUAL"),
    title: str = Form(..., description="Document title"),
    version_name: str = Form(..., description="Version label, e.g. v1, v2"),
    description: Optional[str] = Form(None, description="Optional document description"),
    file: UploadFile = File(..., description="PDF document file"),
    db: Session = Depends(get_db)
):
    """
    Ingest a PDF file, extract headings, sections, subsections, paragraphs, lists,
    tables, and figures, reconstruct hierarchy, compute Merkle content hashes,
    and persist into SQLite.
    """
    file_bytes = await file.read()
    service = DocumentService(db)
    return service.ingest_pdf(
        document_id=document_id,
        title=title,
        version_name=version_name,
        file_bytes=file_bytes,
        file_name=file.filename or f"{document_id}_{version_name}.pdf",
        description=description
    )


@router.get("", response_model=List[DocumentResponse], summary="List all documents")
def list_documents(db: Session = Depends(get_db)):
    """List all ingested documents and their available versions."""
    service = DocumentService(db)
    return service.list_documents()


@router.get("/{document_id}", response_model=DocumentResponse, summary="Get document details")
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Retrieve document metadata and all associated versions."""
    service = DocumentService(db)
    return service.get_document(document_id)


@router.get(
    "/{document_id}/sections",
    response_model=List[SectionSummary],
    summary="List top-level sections (defaults to latest version)"
)
def list_sections_default(
    document_id: str,
    version: Optional[str] = Query(None, description="Version ID or name; defaults to latest"),
    db: Session = Depends(get_db)
):
    """List top-level sections with an optional version parameter (defaults to latest)."""
    service = DocumentService(db)
    if not version:
        latest_ver = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id
        ).order_by(DocumentVersion.created_at.desc()).first()
        if not latest_ver:
            raise VersionNotFoundError(document_id, "latest")
        version = latest_ver.id
    return service.list_sections(document_id, version)


@router.get(
    "/{document_id}/versions/{version_id}/sections",
    response_model=List[SectionSummary],
    summary="List document sections / table of contents for specific version"
)
def list_sections(document_id: str, version_id: str, db: Session = Depends(get_db)):
    """Retrieve top-level headings and sections with child counts for a specific version."""
    service = DocumentService(db)
    return service.list_sections(document_id, version_id)


@router.get(
    "/{document_id}/versions/{version_id}/tree",
    response_model=List[NodeTreeNode],
    summary="Get full hierarchy tree"
)
def get_version_tree(document_id: str, version_id: str, db: Session = Depends(get_db)):
    """Retrieve complete nested hierarchy tree of nodes for a document version."""
    service = DocumentService(db)
    return service.get_version_tree(document_id, version_id)


@router.get(
    "/{document_id}/versions/{version_id}/nodes/{node_id}",
    response_model=NodeResponse,
    summary="Retrieve a specific node"
)
def get_node(document_id: str, version_id: str, node_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific document node, its content, hash, and metadata."""
    service = DocumentService(db)
    return service.get_node(node_id)


@router.get(
    "/{document_id}/nodes/{node_id}/diff",
    response_model=NodeChangeResponse,
    summary="Check if a specific node changed across versions"
)
def get_node_diff(
    document_id: str,
    node_id: str,
    target_version: Optional[str] = Query(None, description="Target version to compare against (defaults to latest)"),
    db: Session = Depends(get_db)
):
    """Given a node ID, return whether it has changed across versions, and if so, a lightweight diff summary."""
    service = VersionService(db)
    return service.compare_node(document_id, node_id, target_version)


@router.get(
    "/{document_id}/versions/{version_id}/search",
    response_model=DocumentSearchResponse,
    summary="Search document content"
)
def search_document(
    document_id: str,
    version_id: str,
    q: str = Query(..., min_length=1, description="Search term or phrase"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Full-text search across document paragraphs, lists, and tables with snippets."""
    service = DocumentService(db)
    return service.search_document(document_id, version_id, q, limit=limit)


@router.get(
    "/{document_id}/compare",
    response_model=DocumentCompareResponse,
    summary="Compare two document versions"
)
def compare_versions(
    document_id: str,
    v1: str = Query(..., description="Source version ID or name (e.g. v1)"),
    v2: str = Query(..., description="Target version ID or name (e.g. v2)"),
    db: Session = Depends(get_db)
):
    """
    Compare v1 and v2 of a manual. Identifies unchanged, modified, added,
    and deleted nodes, generating unified diffs and summary statistics.
    """
    service = VersionService(db)
    return service.compare_versions(document_id, v1, v2)
