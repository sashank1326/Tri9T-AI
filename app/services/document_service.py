import hashlib
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.exceptions import (
    DocumentNotFoundError,
    VersionNotFoundError,
    NodeNotFoundError,
    DuplicateVersionError,
    PDFParseError
)
from app.db.models import Document, DocumentVersion, DocumentNode
from app.schemas.document import (
    DocumentResponse,
    DocumentVersionResponse,
    NodeResponse,
    NodeTreeNode,
    SectionSummary,
    DocumentSearchResult,
    DocumentSearchResponse
)
from app.services.pdf_parser import PDFExtractor, HierarchyReconstructor

logger = logging.getLogger(__name__)


class DocumentService:
    """Service handling document ingestion, browsing, hierarchy retrieval, and searching."""

    def __init__(self, db: Session):
        self.db = db
        self.extractor = PDFExtractor()
        self.hierarchy_reconstructor = HierarchyReconstructor()

    def ingest_pdf(
        self,
        document_id: str,
        title: str,
        version_name: str,
        file_bytes: bytes,
        file_name: str,
        description: Optional[str] = None
    ) -> DocumentVersionResponse:
        """
        Ingest a PDF file, extract structured hierarchy, compute content hashes,
        and persist Document, DocumentVersion, and DocumentNodes into SQLite.
        """
        document_id = document_id.strip()
        version_name = version_name.strip()
        if not document_id or not version_name:
            raise PDFParseError("document_id and version_name cannot be empty.")

        # Compute raw file SHA-256 hash
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Find or create Document
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            doc = Document(
                id=document_id,
                title=title or document_id,
                description=description
            )
            self.db.add(doc)
            self.db.flush()
        else:
            if title and not doc.title:
                doc.title = title
            if description and not doc.description:
                doc.description = description

        # Check for duplicate version name
        existing_version = self.db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_name == version_name
        ).first()
        if existing_version:
            raise DuplicateVersionError(document_id, version_name)

        # Extract elements using modular PDF parser
        raw_elements, page_count = self.extractor.extract_document(file_bytes)

        # Reconstruct hierarchy tree and compute Merkle hashes
        root_nodes, root_hash = self.hierarchy_reconstructor.reconstruct(raw_elements)
        flattened_nodes = self.hierarchy_reconstructor.flatten_tree(root_nodes)

        # Create DocumentVersion record
        doc_version = DocumentVersion(
            document_id=document_id,
            version_name=version_name,
            file_name=file_name,
            file_hash=file_hash,
            page_count=page_count,
            root_hash=root_hash
        )
        self.db.add(doc_version)
        self.db.flush()

        # Persist DocumentNodes
        for p_node in flattened_nodes:
            db_node = DocumentNode(
                id=p_node.id,
                version_id=doc_version.id,
                parent_id=p_node.parent_id,
                node_type=p_node.node_type,
                title=p_node.title,
                section_number=p_node.section_number,
                section_path=p_node.section_path,
                content=p_node.content,
                content_hash=p_node.content_hash,
                level=p_node.level,
                order_index=p_node.order_index,
                page_number=p_node.page_number,
                bounding_box=json.dumps(p_node.bounding_box) if p_node.bounding_box else None,
                metadata_json=json.dumps(p_node.metadata) if p_node.metadata else None
            )
            self.db.add(db_node)

        self.db.commit()
        self.db.refresh(doc_version)

        # Also persist full structured tree in MongoDB document_trees collection
        try:
            from app.db.mongo import get_document_trees_collection
            trees_col = get_document_trees_collection()
            tree_doc = {
                "document_id": doc_version.document_id,
                "version_id": doc_version.id,
                "version_name": doc_version.version_name,
                "file_name": doc_version.file_name,
                "file_hash": doc_version.file_hash,
                "root_hash": doc_version.root_hash,
                "page_count": doc_version.page_count,
                "node_count": len(flattened_nodes),
                "created_at": doc_version.created_at.isoformat() if doc_version.created_at else None,
                "nodes": [
                    {
                        "id": n.id,
                        "parent_id": n.parent_id,
                        "node_type": n.node_type,
                        "title": n.title,
                        "section_number": n.section_number,
                        "section_path": n.section_path,
                        "content": n.content,
                        "content_hash": n.content_hash,
                        "level": n.level,
                        "order_index": n.order_index,
                        "page_number": n.page_number
                    }
                    for n in flattened_nodes
                ]
            }
            trees_col.replace_one(
                {"document_id": doc_version.document_id, "version_name": doc_version.version_name},
                tree_doc,
                upsert=True
            )
        except Exception as e:
            logger.warning("Could not persist document tree in MongoDB: %s", str(e))

        return DocumentVersionResponse(
            id=doc_version.id,
            document_id=doc_version.document_id,
            version_name=doc_version.version_name,
            file_name=doc_version.file_name,
            file_hash=doc_version.file_hash,
            page_count=doc_version.page_count,
            root_hash=doc_version.root_hash,
            created_at=doc_version.created_at,
            node_count=len(flattened_nodes)
        )

    def list_documents(self) -> List[DocumentResponse]:
        """List all documents with their versions and node counts."""
        docs = self.db.query(Document).order_by(Document.created_at.desc()).all()
        results = []
        for doc in docs:
            versions_resp = []
            for v in doc.versions:
                node_count = self.db.query(DocumentNode).filter(DocumentNode.version_id == v.id).count()
                versions_resp.append(DocumentVersionResponse(
                    id=v.id,
                    document_id=v.document_id,
                    version_name=v.version_name,
                    file_name=v.file_name,
                    file_hash=v.file_hash,
                    page_count=v.page_count,
                    root_hash=v.root_hash,
                    created_at=v.created_at,
                    node_count=node_count
                ))
            results.append(DocumentResponse(
                id=doc.id,
                title=doc.title,
                description=doc.description,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                versions=versions_resp
            ))
        return results

    def get_document(self, document_id: str) -> DocumentResponse:
        """Retrieve a specific document with its versions."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(document_id)

        versions_resp = []
        for v in doc.versions:
            node_count = self.db.query(DocumentNode).filter(DocumentNode.version_id == v.id).count()
            versions_resp.append(DocumentVersionResponse(
                id=v.id,
                document_id=v.document_id,
                version_name=v.version_name,
                file_name=v.file_name,
                file_hash=v.file_hash,
                page_count=v.page_count,
                root_hash=v.root_hash,
                created_at=v.created_at,
                node_count=node_count
            ))

        return DocumentResponse(
            id=doc.id,
            title=doc.title,
            description=doc.description,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            versions=versions_resp
        )

    def get_version(self, document_id: str, version_id_or_name: str) -> DocumentVersion:
        """Helper to resolve a version by either UUID id or version_name (e.g. 'v1')."""
        version = self.db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id,
            (DocumentVersion.id == version_id_or_name) | (DocumentVersion.version_name == version_id_or_name)
        ).first()
        if not version:
            raise VersionNotFoundError(document_id, version_id_or_name)
        return version

    def list_sections(self, document_id: str, version_id: str) -> List[SectionSummary]:
        """List top-level sections (headings) for a document version with child counts."""
        version = self.get_version(document_id, version_id)

        headings = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == version.id,
            DocumentNode.node_type == "heading"
        ).order_by(DocumentNode.order_index).all()

        summaries = []
        for h in headings:
            child_count = self.db.query(DocumentNode).filter(DocumentNode.parent_id == h.id).count()
            summaries.append(SectionSummary(
                id=h.id,
                title=h.title,
                section_number=h.section_number,
                section_path=h.section_path,
                level=h.level,
                page_number=h.page_number,
                children_count=child_count
            ))
        return summaries

    def get_node(self, node_id: str, include_children: bool = False) -> NodeResponse:
        """Retrieve a specific document node by ID."""
        node = self.db.query(DocumentNode).filter(DocumentNode.id == node_id).first()
        if not node:
            raise NodeNotFoundError(node_id)

        bbox = json.loads(node.bounding_box) if node.bounding_box else None
        meta = node.get_metadata()

        return NodeResponse(
            id=node.id,
            version_id=node.version_id,
            parent_id=node.parent_id,
            node_type=node.node_type,
            title=node.title,
            section_number=node.section_number,
            section_path=node.section_path,
            content=node.content,
            content_hash=node.content_hash,
            level=node.level,
            order_index=node.order_index,
            page_number=node.page_number,
            bounding_box=bbox,
            metadata=meta
        )

    def get_version_tree(self, document_id: str, version_id: str) -> List[NodeTreeNode]:
        """Retrieve complete reconstructed hierarchy tree for a document version."""
        version = self.get_version(document_id, version_id)
        nodes = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == version.id
        ).order_by(DocumentNode.order_index).all()

        # Build in-memory tree
        node_map: Dict[str, NodeTreeNode] = {}
        for n in nodes:
            bbox = json.loads(n.bounding_box) if n.bounding_box else None
            meta = n.get_metadata()
            node_map[n.id] = NodeTreeNode(
                id=n.id,
                version_id=n.version_id,
                parent_id=n.parent_id,
                node_type=n.node_type,
                title=n.title,
                section_number=n.section_number,
                section_path=n.section_path,
                content=n.content,
                content_hash=n.content_hash,
                level=n.level,
                order_index=n.order_index,
                page_number=n.page_number,
                bounding_box=bbox,
                metadata=meta,
                children=[]
            )

        root_trees: List[NodeTreeNode] = []
        for n in nodes:
            tree_item = node_map[n.id]
            if n.parent_id and n.parent_id in node_map:
                node_map[n.parent_id].children.append(tree_item)
            else:
                root_trees.append(tree_item)

        return root_trees

    def search_document(
        self,
        document_id: str,
        version_id: str,
        query: str,
        limit: int = 50
    ) -> DocumentSearchResponse:
        """Search document content for keywords with relevance scoring and snippet highlighting."""
        version = self.get_version(document_id, version_id)
        q_clean = query.strip()
        if not q_clean:
            return DocumentSearchResponse(
                query=query,
                document_id=document_id,
                version_id=version.id,
                total_matches=0,
                results=[]
            )

        # Search matching nodes
        like_pattern = f"%{q_clean}%"
        matches = self.db.query(DocumentNode).filter(
            DocumentNode.version_id == version.id,
            (DocumentNode.content.ilike(like_pattern) | DocumentNode.title.ilike(like_pattern))
        ).limit(limit).all()

        results = []
        for m in matches:
            # Extract snippet around match
            text = m.content or ""
            idx = text.lower().find(q_clean.lower())
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(text), idx + len(q_clean) + 40)
                snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
            else:
                snippet = text[:100] + ("..." if len(text) > 100 else "")

            # Simple scoring: exact title match > exact content occurrence
            score = 1.0
            if m.title and q_clean.lower() in m.title.lower():
                score += 1.0
            score += text.lower().count(q_clean.lower()) * 0.2

            results.append(DocumentSearchResult(
                node_id=m.id,
                version_id=version.id,
                version_name=version.version_name,
                node_type=m.node_type,
                title=m.title,
                section_path=m.section_path,
                page_number=m.page_number,
                content_snippet=snippet,
                content_hash=m.content_hash,
                relevance_score=round(score, 2)
            ))

        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return DocumentSearchResponse(
            query=query,
            document_id=document_id,
            version_id=version.id,
            total_matches=len(results),
            results=results
        )
