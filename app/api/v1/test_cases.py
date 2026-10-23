import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.core.exceptions import (
    SelectionNotFoundError,
    GenerationNotFoundError,
    TestCaseNotFoundError,
    DocumentNotFoundError,
    LLMGenerationError
)
from app.db.sqlite import get_db
from app.db.models import Document, DocumentVersion, DocumentNode, VersionPinnedSelection
from app.db.mongo import get_generations_collection, get_test_cases_collection
from app.schemas.test_case import (
    GenerateTestCasesRequest,
    GenerationBatchResponse,
    QATestCaseItem,
    StalenessReport
)
from app.services.llm_service import LLMService
from app.services.selection_service import SelectionService
from app.services.staleness_service import StalenessService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test-cases", tags=["AI Test Cases"])


@router.post(
    "/generate",
    response_model=GenerationBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate AI QA test cases using Gemini"
)
def generate_test_cases(
    req: GenerateTestCasesRequest,
    db: Session = Depends(get_db)
):
    """
    Generate 3-5 QA test cases from selected document text or selection ID.
    Validates output with Pydantic, handles errors, and stores test cases
    and original source snapshot in MongoDB.
    """
    source_text = ""
    document_id = req.document_id
    version_id = req.version_id
    version_name = ""
    node_ids = req.node_ids or []
    selection_id = req.selection_id

    # 1. Resolve source text and metadata
    if req.selection_id:
        sel_service = SelectionService(db)
        selection = sel_service.get_selection(req.selection_id)
        source_text = selection.pinned_content_snapshot
        document_id = selection.document_id
        version_id = selection.version_id
        version_name = selection.version_name or "pinned"
        node_ids = selection.node_ids

    elif req.document_id and req.version_id and req.node_ids:
        # Load from specified nodes
        ver = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == req.document_id,
            (DocumentVersion.id == req.version_id) | (DocumentVersion.version_name == req.version_id)
        ).first()
        if not ver:
            raise DocumentNotFoundError(f"Version '{req.version_id}' not found.")

        version_id = ver.id
        version_name = ver.version_name
        nodes = db.query(DocumentNode).filter(
            DocumentNode.version_id == ver.id,
            DocumentNode.id.in_(req.node_ids)
        ).order_by(DocumentNode.order_index).all()

        if not nodes:
            raise HTTPException(status_code=400, detail="No matching nodes found for generation.")

        parts = []
        for n in nodes:
            prefix = f"[{n.title}] " if n.title else ""
            parts.append(f"{prefix}{n.content}")
        source_text = "\n\n".join(parts)

    elif req.custom_text:
        source_text = req.custom_text
        document_id = document_id or "adhoc-doc"
        version_id = version_id or "adhoc-ver"
        version_name = "custom"

    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either selection_id, or (document_id, version_id, node_ids), or custom_text."
        )

    # 2. Invoke LLM generation service
    llm = LLMService()
    batch_resp = llm.generate_test_cases(
        source_text=source_text,
        document_id=document_id,
        source_version_id=version_id,
        source_version_name=version_name,
        selection_id=selection_id,
        node_ids=node_ids,
        num_test_cases=req.num_test_cases
    )

    # 3. Check staleness against active document version
    try:
        staleness_svc = StalenessService(db)
        staleness = staleness_svc.evaluate_staleness(
            document_id=document_id,
            source_version_id=version_id,
            source_hash=batch_resp.source_hash,
            source_snapshot=batch_resp.source_snapshot,
            node_ids=node_ids,
            selection_id=selection_id
        )
        batch_resp.staleness = staleness
    except Exception as e:
        logger.warning("Staleness check skipped for adhoc or unpersisted doc: %s", str(e))

    return batch_resp


@router.get(
    "/by-generation/{generation_id}",
    response_model=GenerationBatchResponse,
    summary="Retrieve test cases by generation batch ID"
)
def get_by_generation(generation_id: str, db: Session = Depends(get_db)):
    """Retrieve test case generation batch from MongoDB with source snapshot and staleness status."""
    gen_col = get_generations_collection()
    record = gen_col.find_one({"generation_id": generation_id})
    if not record:
        raise GenerationNotFoundError(generation_id)

    # Evaluate staleness against latest document version
    staleness = None
    try:
        staleness_svc = StalenessService(db)
        staleness = staleness_svc.evaluate_staleness(
            document_id=record["document_id"],
            source_version_id=record["source_version_id"],
            source_hash=record["source_hash"],
            source_snapshot=record["source_snapshot"],
            node_ids=record.get("node_ids", []),
            selection_id=record.get("selection_id")
        )
    except Exception as e:
        logger.warning("Could not compute staleness for generation %s: %s", generation_id, str(e))

    return GenerationBatchResponse(
        generation_id=record["generation_id"],
        selection_id=record.get("selection_id"),
        document_id=record["document_id"],
        source_version_id=record["source_version_id"],
        source_version_name=record.get("source_version_name", "v1"),
        source_snapshot=record["source_snapshot"],
        source_hash=record["source_hash"],
        model_name=record.get("model_name", "gemini-3.8-flash"),
        node_ids=record.get("node_ids", []),
        test_cases=[QATestCaseItem(**tc) for tc in record.get("test_cases", [])],
        staleness=staleness,
        generated_at=record.get("generated_at")
    )


@router.get(
    "/by-selection/{selection_id}",
    response_model=List[GenerationBatchResponse],
    summary="Retrieve test cases by selection ID"
)
def get_by_selection(selection_id: str, db: Session = Depends(get_db)):
    """Retrieve all test case generation batches associated with a selection ID, with staleness status."""
    gen_col = get_generations_collection()
    cursor = gen_col.find({"selection_id": selection_id}).sort("generated_at", -1)
    records = list(cursor)

    results = []
    staleness_svc = StalenessService(db)

    for rec in records:
        staleness = None
        try:
            staleness = staleness_svc.evaluate_staleness(
                document_id=rec["document_id"],
                source_version_id=rec["source_version_id"],
                source_hash=rec["source_hash"],
                source_snapshot=rec["source_snapshot"],
                node_ids=rec.get("node_ids", []),
                selection_id=rec.get("selection_id")
            )
        except Exception as e:
            logger.warning("Staleness error: %s", str(e))

        results.append(GenerationBatchResponse(
            generation_id=rec["generation_id"],
            selection_id=rec.get("selection_id"),
            document_id=rec["document_id"],
            source_version_id=rec["source_version_id"],
            source_version_name=rec.get("source_version_name", "v1"),
            source_snapshot=rec["source_snapshot"],
            source_hash=rec["source_hash"],
            model_name=rec.get("model_name", "gemini-3.8-flash"),
            node_ids=rec.get("node_ids", []),
            test_cases=[QATestCaseItem(**tc) for tc in rec.get("test_cases", [])],
            staleness=staleness,
            generated_at=rec.get("generated_at")
        ))

    return results


@router.get(
    "/by-node/{node_id}",
    response_model=List[Dict[str, Any]],
    summary="Retrieve test cases covering a specific node ID"
)
def get_by_node(node_id: str, db: Session = Depends(get_db)):
    """Retrieve test cases covering a specific document node across versions."""
    tc_col = get_test_cases_collection()
    cursor = tc_col.find({"source_node_ids": node_id}).sort("created_at", -1)
    items = list(cursor)

    staleness_svc = StalenessService(db)
    results = []

    for item in items:
        # Convert _id to string for JSON serialization
        item["_id"] = str(item["_id"])
        # Evaluate staleness
        try:
            staleness = staleness_svc.evaluate_staleness(
                document_id=item["document_id"],
                source_version_id=item["source_version_id"],
                source_hash=item["source_content_hash"],
                source_snapshot=item.get("source_snapshot", ""),
                node_ids=[node_id]
            )
            item["staleness"] = staleness.model_dump()
        except Exception:
            item["staleness"] = None

        results.append(item)

    return results


@router.get(
    "/{test_case_id}",
    response_model=Dict[str, Any],
    summary="Retrieve a specific test case by ID"
)
def get_test_case(test_case_id: str, db: Session = Depends(get_db)):
    """Retrieve individual test case with source requirement snapshot and staleness status."""
    tc_col = get_test_cases_collection()
    # Query either by internal _id or test_case_id
    item = tc_col.find_one({"$or": [{"_id": test_case_id}, {"test_case_id": test_case_id}]})
    if not item:
        raise TestCaseNotFoundError(test_case_id)

    item["_id"] = str(item["_id"])

    # Staleness evaluation
    try:
        staleness_svc = StalenessService(db)
        staleness = staleness_svc.evaluate_staleness(
            document_id=item["document_id"],
            source_version_id=item["source_version_id"],
            source_hash=item["source_content_hash"],
            source_snapshot=item.get("source_snapshot", ""),
            node_ids=item.get("source_node_ids", []),
            selection_id=item.get("selection_id")
        )
        item["staleness"] = staleness.model_dump()
    except Exception as e:
        logger.warning("Staleness evaluation note: %s", str(e))
        item["staleness"] = None

    return item
