import pytest
from app.services.document_service import DocumentService
from app.services.selection_service import SelectionService
from app.services.staleness_service import StalenessService
from app.schemas.selection import SelectionCreateRequest
from app.schemas.test_case import StalenessStatusEnum
from app.db.models import DocumentNode


def test_staleness_detection_lifecycle(db_session, pdf_v1_bytes, pdf_v2_bytes):
    """
    Test staleness detection across 4 scenarios:
    1. Same version evaluation -> UP_TO_DATE
    2. Modified requirement in v2 -> STALE_MODIFIED with diff summary
    3. Deleted requirement in v2 -> STALE_DELETED
    4. Unchanged requirement in v2 -> UP_TO_DATE
    """
    doc_svc = DocumentService(db_session)
    sel_svc = SelectionService(db_session)
    staleness_svc = StalenessService(db_session)

    # 1. Ingest v1
    v1_res = doc_svc.ingest_pdf(
        document_id="CT-200-STALE-TEST",
        title="CT-200 Staleness Test",
        version_name="v1",
        file_bytes=pdf_v1_bytes,
        file_name="CT-200_v1.pdf"
    )

    # Find modified section in v1 (120 kV voltage)
    mod_node_v1 = db_session.query(DocumentNode).filter(
        DocumentNode.version_id == v1_res.id,
        DocumentNode.content.like("%120 kV%")
    ).first()
    assert mod_node_v1 is not None

    # Find deleted section in v1 (hardware warnings)
    del_node_v1 = db_session.query(DocumentNode).filter(
        DocumentNode.version_id == v1_res.id,
        DocumentNode.content.like("%patient table locking pins%")
    ).first()
    assert del_node_v1 is not None

    # Find unchanged section in v1 (system overview)
    unchanged_node_v1 = db_session.query(DocumentNode).filter(
        DocumentNode.version_id == v1_res.id,
        DocumentNode.content.like("%simulated multi-slice imaging system%")
    ).first()
    assert unchanged_node_v1 is not None

    # Scenario 1: Same version evaluation (before v2 exists)
    stale_same = staleness_svc.evaluate_staleness(
        document_id="CT-200-STALE-TEST",
        source_version_id=v1_res.id,
        source_hash=mod_node_v1.content_hash,
        source_snapshot=mod_node_v1.content,
        node_ids=[mod_node_v1.id]
    )
    assert stale_same.overall_status == StalenessStatusEnum.UP_TO_DATE
    assert stale_same.is_stale is False

    # 2. Ingest v2
    v2_res = doc_svc.ingest_pdf(
        document_id="CT-200-STALE-TEST",
        title="CT-200 Staleness Test",
        version_name="v2",
        file_bytes=pdf_v2_bytes,
        file_name="CT-200_v2.pdf"
    )

    # Scenario 2: Requirement was modified in v2 (120 kV -> 140 kV)
    stale_mod = staleness_svc.evaluate_staleness(
        document_id="CT-200-STALE-TEST",
        source_version_id=v1_res.id,
        source_hash=mod_node_v1.content_hash,
        source_snapshot=mod_node_v1.content,
        node_ids=[mod_node_v1.id]
    )
    assert stale_mod.overall_status == StalenessStatusEnum.STALE_MODIFIED
    assert stale_mod.is_stale is True
    assert stale_mod.diff_summary is not None
    assert stale_mod.unified_diff is not None
    assert "140 kV" in stale_mod.unified_diff or "line(s)" in stale_mod.diff_summary

    # Scenario 3: Requirement was deleted in v2 (hardware chapter removed)
    stale_del = staleness_svc.evaluate_staleness(
        document_id="CT-200-STALE-TEST",
        source_version_id=v1_res.id,
        source_hash=del_node_v1.content_hash,
        source_snapshot=del_node_v1.content,
        node_ids=[del_node_v1.id]
    )
    assert stale_del.overall_status == StalenessStatusEnum.STALE_DELETED
    assert stale_del.is_stale is True
    assert "deleted" in stale_del.diff_summary.lower()

    # Scenario 4: Requirement was unchanged in v2 (system overview)
    stale_unchanged = staleness_svc.evaluate_staleness(
        document_id="CT-200-STALE-TEST",
        source_version_id=v1_res.id,
        source_hash=unchanged_node_v1.content_hash,
        source_snapshot=unchanged_node_v1.content,
        node_ids=[unchanged_node_v1.id]
    )
    assert stale_unchanged.overall_status == StalenessStatusEnum.UP_TO_DATE
    assert stale_unchanged.is_stale is False
