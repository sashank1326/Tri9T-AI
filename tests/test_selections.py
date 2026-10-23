import pytest
from app.services.document_service import DocumentService
from app.services.selection_service import SelectionService
from app.schemas.selection import SelectionCreateRequest
from app.db.models import DocumentNode


def test_version_pinned_selection_immutability(db_session, pdf_v1_bytes, pdf_v2_bytes):
    """
    Test that a selection created against v1 retains its original text snapshot
    and content hash even after v2 with modified requirements is ingested.
    """
    doc_svc = DocumentService(db_session)
    sel_svc = SelectionService(db_session)

    # 1. Ingest v1
    v1_res = doc_svc.ingest_pdf(
        document_id="CT-200-PIN-TEST",
        title="CT-200 Pinning Test",
        version_name="v1",
        file_bytes=pdf_v1_bytes,
        file_name="CT-200_v1.pdf"
    )

    # Find the node with 120 kV voltage specification in v1
    node_v1 = db_session.query(DocumentNode).filter(
        DocumentNode.version_id == v1_res.id,
        DocumentNode.content.like("%120 kV%")
    ).first()
    assert node_v1 is not None

    # 2. Create version-pinned selection
    selection_req = SelectionCreateRequest(
        document_id="CT-200-PIN-TEST",
        version_id=v1_res.id,
        node_ids=[node_v1.id],
        title="Pinned Generator Limit v1",
        description="Preserved snapshot of 120 kV limit",
        tags=["safety", "generator"]
    )
    selection = sel_svc.create_selection(selection_req)

    original_snapshot = selection.pinned_content_snapshot
    original_hash = selection.content_hash
    selection_id = selection.id

    assert "120 kV" in original_snapshot
    assert "140 kV" not in original_snapshot

    # 3. Ingest v2 where voltage requirement is changed to 140 kV
    v2_res = doc_svc.ingest_pdf(
        document_id="CT-200-PIN-TEST",
        title="CT-200 Pinning Test",
        version_name="v2",
        file_bytes=pdf_v2_bytes,
        file_name="CT-200_v2.pdf"
    )
    assert v2_res.version_name == "v2"

    # Verify v2 has the new 140 kV text
    node_v2 = db_session.query(DocumentNode).filter(
        DocumentNode.version_id == v2_res.id,
        DocumentNode.content.like("%140 kV%")
    ).first()
    assert node_v2 is not None

    # 4. CRITICAL INVARIANT: Retrieve old selection and verify immutability
    retrieved_selection = sel_svc.get_selection(selection_id)

    assert retrieved_selection.version_id == v1_res.id
    assert retrieved_selection.pinned_content_snapshot == original_snapshot
    assert retrieved_selection.content_hash == original_hash
    assert "120 kV" in retrieved_selection.pinned_content_snapshot
    assert "140 kV" not in retrieved_selection.pinned_content_snapshot
