import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.core.diff import generate_text_diff, summarize_text_changes
from app.core.exceptions import DocumentNotFoundError, VersionNotFoundError
from app.core.hashing import compute_text_hash
from app.db.models import Document, DocumentVersion, DocumentNode, VersionPinnedSelection
from app.db.mongo import get_staleness_audits_collection
from app.schemas.test_case import StalenessReport, StalenessStatusEnum

logger = logging.getLogger(__name__)


class StalenessService:
    """Service to evaluate whether AI test cases generated from past versions are stale against current requirements."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate_staleness(
        self,
        document_id: str,
        source_version_id: str,
        source_hash: str,
        source_snapshot: str,
        node_ids: Optional[List[str]] = None,
        selection_id: Optional[str] = None,
        target_version_id: Optional[str] = None
    ) -> StalenessReport:
        """
        Evaluate staleness by comparing the original source snapshot and hashes
        against the specified target version (or latest version by default).
        """
        # Validate Document
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(document_id)

        # Retrieve source version
        source_ver = self.db.query(DocumentVersion).filter(
            DocumentVersion.id == source_version_id
        ).first()
        if not source_ver:
            raise VersionNotFoundError(document_id, source_version_id)

        # Resolve target version (default: latest version)
        if target_version_id:
            target_ver = self.db.query(DocumentVersion).filter(
                DocumentVersion.document_id == document_id,
                (DocumentVersion.id == target_version_id) | (DocumentVersion.version_name == target_version_id)
            ).first()
            if not target_ver:
                raise VersionNotFoundError(document_id, target_version_id)
        else:
            # Latest version by creation time
            target_ver = self.db.query(DocumentVersion).filter(
                DocumentVersion.document_id == document_id
            ).order_by(DocumentVersion.created_at.desc()).first()

        # If target version is identical to source version
        if target_ver.id == source_ver.id:
            return StalenessReport(
                overall_status=StalenessStatusEnum.UP_TO_DATE,
                is_stale=False,
                source_version_id=source_ver.id,
                source_version_name=source_ver.version_name,
                target_version_id=target_ver.id,
                target_version_name=target_ver.version_name,
                source_content_hash=source_hash,
                target_content_hash=source_hash,
                diff_summary="Test cases are generated from the current document version.",
                unified_diff="",
                affected_nodes=[],
                explanation="Requirements match the active document version."
            )

        # If selection_id was provided, resolve node_ids if omitted
        effective_node_ids = list(node_ids or [])
        if selection_id and not effective_node_ids:
            sel = self.db.query(VersionPinnedSelection).filter(
                VersionPinnedSelection.id == selection_id
            ).first()
            if sel:
                effective_node_ids = sel.get_node_ids()

        # Retrieve original source nodes to obtain their section paths
        source_nodes = []
        if effective_node_ids:
            source_nodes = self.db.query(DocumentNode).filter(
                DocumentNode.version_id == source_ver.id,
                DocumentNode.id.in_(effective_node_ids)
            ).order_by(DocumentNode.order_index).all()

        if not source_nodes:
            # Fallback if specific node IDs are not present: compare entire document root hash
            if source_ver.root_hash == target_ver.root_hash:
                return StalenessReport(
                    overall_status=StalenessStatusEnum.UP_TO_DATE,
                    is_stale=False,
                    source_version_id=source_ver.id,
                    source_version_name=source_ver.version_name,
                    target_version_id=target_ver.id,
                    target_version_name=target_ver.version_name,
                    source_content_hash=source_hash,
                    target_content_hash=target_ver.root_hash,
                    diff_summary="Document root hashes are identical.",
                    unified_diff="",
                    affected_nodes=[],
                    explanation="No changes detected in document hierarchy."
                )

        # Map source section paths to target version nodes
        deleted_paths = []
        target_nodes_matching = []
        node_pairs = []

        for sn in source_nodes:
            match = self.db.query(DocumentNode).filter(
                DocumentNode.version_id == target_ver.id,
                DocumentNode.section_path == sn.section_path
            ).first()
            if not match:
                deleted_paths.append(sn.section_path)
            else:
                target_nodes_matching.append(match)
                node_pairs.append((sn, match))

        # Case 1: Requirement nodes were deleted in target version
        if deleted_paths:
            affected = [sn.id for sn in source_nodes if sn.section_path in deleted_paths]
            report = StalenessReport(
                overall_status=StalenessStatusEnum.STALE_DELETED,
                is_stale=True,
                source_version_id=source_ver.id,
                source_version_name=source_ver.version_name,
                target_version_id=target_ver.id,
                target_version_name=target_ver.version_name,
                source_content_hash=source_hash,
                target_content_hash=None,
                diff_summary=f"Requirement node(s) deleted in {target_ver.version_name}: {', '.join(deleted_paths)}",
                unified_diff=f"- Source requirement was removed from {target_ver.version_name}",
                affected_nodes=affected,
                explanation=f"Requirements were removed in version {target_ver.version_name}. Associated test cases are obsolete."
            )
            self._log_audit(report, document_id)
            return report

        # Case 2: Check node-by-node content hash changes
        modified_pairs = [pair for pair in node_pairs if pair[0].content_hash != pair[1].content_hash]

        if not modified_pairs:
            # All source nodes exist in target version and have identical hashes
            report = StalenessReport(
                overall_status=StalenessStatusEnum.UP_TO_DATE,
                is_stale=False,
                source_version_id=source_ver.id,
                source_version_name=source_ver.version_name,
                target_version_id=target_ver.id,
                target_version_name=target_ver.version_name,
                source_content_hash=source_hash,
                target_content_hash=source_hash,
                diff_summary="Requirement content is identical across versions.",
                unified_diff="",
                affected_nodes=[],
                explanation=f"Requirements unchanged in version {target_ver.version_name}. Test cases remain valid."
            )
            self._log_audit(report, document_id)
            return report

        # Case 3: Matching nodes were modified
        target_snapshot_parts = []
        for _, tn in node_pairs:
            prefix = f"[{tn.title}] " if tn.title else ""
            target_snapshot_parts.append(f"{prefix}{tn.content}")
        target_snapshot = "\n\n".join(target_snapshot_parts)
        target_hash = compute_text_hash(target_snapshot)

        diff_info = summarize_text_changes(source_snapshot, target_snapshot)
        affected_modified = [tn.id for _, tn in modified_pairs]

        report = StalenessReport(
            overall_status=StalenessStatusEnum.STALE_MODIFIED,
            is_stale=True,
            source_version_id=source_ver.id,
            source_version_name=source_ver.version_name,
            target_version_id=target_ver.id,
            target_version_name=target_ver.version_name,
            source_content_hash=source_hash,
            target_content_hash=target_hash,
            diff_summary=f"Requirements modified in {target_ver.version_name}: {diff_info['summary']}",
            unified_diff=diff_info["unified_diff"],
            affected_nodes=affected_modified,
            explanation=f"Requirement text changed in version {target_ver.version_name}. Test cases must be regenerated or reviewed."
        )
        self._log_audit(report, document_id)
        return report

    def _log_audit(self, report: StalenessReport, document_id: str):
        """Record staleness evaluation in MongoDB audit log collection."""
        try:
            audits_col = get_staleness_audits_collection()
            audits_col.insert_one({
                "document_id": document_id,
                "overall_status": report.overall_status.value,
                "is_stale": report.is_stale,
                "source_version_id": report.source_version_id,
                "target_version_id": report.target_version_id,
                "diff_summary": report.diff_summary,
                "evaluated_at": report.source_version_name
            })
        except Exception as e:
            logger.warning("Could not record staleness audit in MongoDB: %s", str(e))
