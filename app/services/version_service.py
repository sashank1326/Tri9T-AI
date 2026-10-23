import logging
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.diff import generate_text_diff, summarize_text_changes
from app.core.exceptions import VersionNotFoundError
from app.db.models import DocumentVersion, DocumentNode
from app.schemas.diff import (
    NodeDiffStatus,
    NodeDiffItem,
    VersionDiffSummary,
    DocumentCompareResponse
)

logger = logging.getLogger(__name__)


class VersionService:
    """Service for comparing two document versions, computing diffs, and classifying node states."""

    def __init__(self, db: Session):
        self.db = db

    def compare_versions(
        self,
        document_id: str,
        v1_id_or_name: str,
        v2_id_or_name: str
    ) -> DocumentCompareResponse:
        """
        Compare two versions of a document, identify unchanged, modified,
        added, and deleted nodes, and generate detailed diffs.
        """
        v1 = self._resolve_version(document_id, v1_id_or_name)
        v2 = self._resolve_version(document_id, v2_id_or_name)

        nodes_v1 = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == v1.id
        ).order_by(DocumentNode.order_index).all()

        nodes_v2 = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == v2.id
        ).order_by(DocumentNode.order_index).all()

        v1_by_path: Dict[str, DocumentNode] = {n.section_path: n for n in nodes_v1}
        v2_by_path: Dict[str, DocumentNode] = {n.section_path: n for n in nodes_v2}

        all_paths = list(dict.fromkeys(list(v1_by_path.keys()) + list(v2_by_path.keys())))

        node_diffs: List[NodeDiffItem] = []
        unchanged_count = 0
        modified_count = 0
        added_count = 0
        deleted_count = 0

        for path in all_paths:
            node1 = v1_by_path.get(path)
            node2 = v2_by_path.get(path)

            if node1 and node2:
                # Node exists in both versions
                if node1.content_hash == node2.content_hash:
                    # Unchanged
                    unchanged_count += 1
                    node_diffs.append(NodeDiffItem(
                        section_path=path,
                        node_type=node1.node_type,
                        title=node1.title or node2.title,
                        status=NodeDiffStatus.UNCHANGED,
                        node_id_v1=node1.id,
                        node_id_v2=node2.id,
                        content_hash_v1=node1.content_hash,
                        content_hash_v2=node2.content_hash,
                        changes_summary="Content is identical",
                        unified_diff="",
                        content_v1=node1.content,
                        content_v2=node2.content
                    ))
                else:
                    # Modified
                    modified_count += 1
                    diff_info = summarize_text_changes(node1.content, node2.content)
                    node_diffs.append(NodeDiffItem(
                        section_path=path,
                        node_type=node2.node_type,
                        title=node2.title or node1.title,
                        status=NodeDiffStatus.MODIFIED,
                        node_id_v1=node1.id,
                        node_id_v2=node2.id,
                        content_hash_v1=node1.content_hash,
                        content_hash_v2=node2.content_hash,
                        changes_summary=diff_info["summary"],
                        unified_diff=diff_info["unified_diff"],
                        content_v1=node1.content,
                        content_v2=node2.content
                    ))

            elif node1 and not node2:
                # Deleted in v2
                deleted_count += 1
                node_diffs.append(NodeDiffItem(
                    section_path=path,
                    node_type=node1.node_type,
                    title=node1.title,
                    status=NodeDiffStatus.DELETED,
                    node_id_v1=node1.id,
                    node_id_v2=None,
                    content_hash_v1=node1.content_hash,
                    content_hash_v2=None,
                    changes_summary="Node removed in target version",
                    unified_diff=f"- {node1.content}",
                    content_v1=node1.content,
                    content_v2=None
                ))

            elif not node1 and node2:
                # Added in v2
                added_count += 1
                node_diffs.append(NodeDiffItem(
                    section_path=path,
                    node_type=node2.node_type,
                    title=node2.title,
                    status=NodeDiffStatus.ADDED,
                    node_id_v1=None,
                    node_id_v2=node2.id,
                    content_hash_v1=None,
                    content_hash_v2=node2.content_hash,
                    changes_summary="New node added in target version",
                    unified_diff=f"+ {node2.content}",
                    content_v1=None,
                    content_v2=node2.content
                ))

        summary = VersionDiffSummary(
            unchanged_count=unchanged_count,
            modified_count=modified_count,
            added_count=added_count,
            deleted_count=deleted_count,
            total_nodes_v1=len(nodes_v1),
            total_nodes_v2=len(nodes_v2)
        )

        return DocumentCompareResponse(
            document_id=document_id,
            v1_version_id=v1.id,
            v1_version_name=v1.version_name,
            v2_version_id=v2.id,
            v2_version_name=v2.version_name,
            summary=summary,
            node_diffs=node_diffs
        )

    def _resolve_version(self, document_id: str, version_id_or_name: str) -> DocumentVersion:
        version = self.db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id,
            (DocumentVersion.id == version_id_or_name) | (DocumentVersion.version_name == version_id_or_name)
        ).first()
        if not version:
            raise VersionNotFoundError(document_id, version_id_or_name)
        return version
