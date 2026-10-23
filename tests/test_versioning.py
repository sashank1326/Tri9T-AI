import pytest
from app.services.document_service import DocumentService
from app.services.version_service import VersionService
from app.schemas.diff import NodeDiffStatus
from app.core.exceptions import DuplicateVersionError


def test_document_versioning_and_diff(db_session, pdf_v1_bytes, pdf_v2_bytes):
    """
    Test ingesting v1 and v2 of a document, verifying both are preserved,
    and comparing versions to identify unchanged, modified, added, and deleted nodes.
    """
    doc_svc = DocumentService(db_session)
    ver_svc = VersionService(db_session)

    # Ingest Version 1
    v1_res = doc_svc.ingest_pdf(
        document_id="CT-200-TEST",
        title="CT-200 Test Manual",
        version_name="v1",
        file_bytes=pdf_v1_bytes,
        file_name="CT-200_v1.pdf"
    )
    assert v1_res.version_name == "v1"

    # Ingest Version 2
    v2_res = doc_svc.ingest_pdf(
        document_id="CT-200-TEST",
        title="CT-200 Test Manual",
        version_name="v2",
        file_bytes=pdf_v2_bytes,
        file_name="CT-200_v2.pdf"
    )
    assert v2_res.version_name == "v2"

    # Both versions must be preserved independently in database
    doc = doc_svc.get_document("CT-200-TEST")
    assert len(doc.versions) == 2

    # Compare versions
    diff_report = ver_svc.compare_versions("CT-200-TEST", "v1", "v2")

    assert diff_report.document_id == "CT-200-TEST"
    assert diff_report.v1_version_name == "v1"
    assert diff_report.v2_version_name == "v2"

    summary = diff_report.summary
    assert summary.unchanged_count > 0
    assert summary.modified_count > 0
    assert summary.added_count > 0
    assert summary.deleted_count > 0

    # Verify specific modifications
    modified_items = [d for d in diff_report.node_diffs if d.status == NodeDiffStatus.MODIFIED]
    mod_texts = [d.changes_summary for d in modified_items]
    assert len(modified_items) >= 1

    # Verify added nodes
    added_items = [d for d in diff_report.node_diffs if d.status == NodeDiffStatus.ADDED]
    assert any("pediatric" in d.section_path.lower() for d in added_items)

    # Verify deleted nodes
    deleted_items = [d for d in diff_report.node_diffs if d.status == NodeDiffStatus.DELETED]
    assert len(deleted_items) >= 1


def test_duplicate_version_rejected(db_session, pdf_v1_bytes):
    """Verify attempting to ingest the same version name twice raises DuplicateVersionError."""
    doc_svc = DocumentService(db_session)
    doc_svc.ingest_pdf(
        document_id="CT-200-DUP",
        title="CT-200 Duplicate Test",
        version_name="v1",
        file_bytes=pdf_v1_bytes,
        file_name="CT-200_v1.pdf"
    )

    with pytest.raises(DuplicateVersionError):
        doc_svc.ingest_pdf(
            document_id="CT-200-DUP",
            title="CT-200 Duplicate Test",
            version_name="v1",
            file_bytes=pdf_v1_bytes,
            file_name="CT-200_v1.pdf"
        )
