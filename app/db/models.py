import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import relationship
from app.db.sqlite import Base


def utc_now():
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)  # e.g., "CT-200-MANUAL" or UUID
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.created_at"
    )
    selections = relationship(
        "VersionPinnedSelection",
        back_populates="document",
        cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_name = Column(String(64), nullable=False)  # e.g., "v1", "v2"
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256 of raw PDF
    page_count = Column(Integer, default=0)
    root_hash = Column(String(64), nullable=True)  # Merkle tree root hash
    created_at = Column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("document_id", "version_name", name="uq_doc_version"),
    )

    document = relationship("Document", back_populates="versions")
    nodes = relationship(
        "DocumentNode",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="DocumentNode.order_index"
    )
    selections = relationship(
        "VersionPinnedSelection",
        back_populates="version"
    )


class DocumentNode(Base):
    __tablename__ = "document_nodes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("document_nodes.id", ondelete="CASCADE"), nullable=True, index=True)

    node_type = Column(String(32), nullable=False)  # heading, section, subsection, paragraph, list, table, figure
    title = Column(String(255), nullable=True)
    section_number = Column(String(64), nullable=True)  # e.g., "1.1", "2.3.1"
    section_path = Column(String(512), nullable=False, index=True)  # e.g., "/1-overview/1.1-safety"
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 of node content
    level = Column(Integer, default=0)  # Hierarchy depth level (1=h1, 2=h2, etc.)
    order_index = Column(Integer, default=0)  # Sibling sequence order
    page_number = Column(Integer, default=1)
    bounding_box = Column(Text, nullable=True)  # JSON coordinates [x0, y0, x1, y1]
    metadata_json = Column(Text, nullable=True)  # JSON metadata (table headers, font info, etc.)

    version = relationship("DocumentVersion", back_populates="nodes")
    parent = relationship("DocumentNode", remote_side=[id], back_populates="children")
    children = relationship(
        "DocumentNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="DocumentNode.order_index"
    )

    def get_metadata(self) -> dict:
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except Exception:
                return {}
        return {}


class VersionPinnedSelection(Base):
    __tablename__ = "version_pinned_selections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    node_ids_json = Column(Text, nullable=False)  # JSON array of selected node IDs
    pinned_content_snapshot = Column(Text, nullable=False)  # Immutable text snapshot at time of selection
    content_hash = Column(String(64), nullable=False)  # SHA-256 hash of pinned content
    tags_json = Column(Text, nullable=True)  # JSON array of tags
    created_at = Column(DateTime(timezone=True), default=utc_now)

    document = relationship("Document", back_populates="selections")
    version = relationship("DocumentVersion", back_populates="selections")

    def get_node_ids(self) -> List[str]:
        try:
            return json.loads(self.node_ids_json)
        except Exception:
            return []

    def get_tags(self) -> List[str]:
        if self.tags_json:
            try:
                return json.loads(self.tags_json)
            except Exception:
                return []
        return []
