import re
import uuid
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple

from app.core.hashing import compute_node_hash
from app.services.pdf_parser.extractor import RawElement


def slugify(text: str) -> str:
    """Convert text to a URL-safe, lowercase slug."""
    text = (text or "").strip().lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text[:64].strip('-') or "node"


class ParsedNode:
    """In-memory representation of a node in the reconstructed hierarchy."""

    def __init__(
        self,
        node_type: str,
        content: str,
        page_number: int,
        title: Optional[str] = None,
        section_number: Optional[str] = None,
        level: int = 0,
        bounding_box: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.id = str(uuid.uuid4())
        self.node_type = node_type
        self.content = content
        self.page_number = page_number
        self.title = title
        self.section_number = section_number
        self.level = level
        self.bounding_box = bounding_box
        self.metadata = metadata or {}

        self.parent: Optional['ParsedNode'] = None
        self.parent_id: Optional[str] = None
        self.children: List['ParsedNode'] = []
        self.order_index: int = 0
        self.section_path: str = ""
        self.content_hash: str = ""

    def add_child(self, child: 'ParsedNode'):
        child.parent = self
        child.parent_id = self.id
        child.order_index = len(self.children)
        self.children.append(child)


class HierarchyReconstructor:
    """
    Reconstructs tree hierarchy from a flat sequence of extracted raw elements,
    disambiguates duplicate headings, builds semantic section paths,
    and calculates bottom-up content hashes for all nodes.
    """

    def reconstruct(self, elements: List[RawElement]) -> Tuple[List[ParsedNode], str]:
        """
        Reconstructs the hierarchical tree of ParsedNode objects.
        Returns:
            - List of top-level ParsedNode roots
            - Root Merkle hash representing the entire document state
        """
        if not elements:
            return [], ""

        root_nodes: List[ParsedNode] = []
        heading_stack: List[ParsedNode] = []  # Stack of active headings [(level, node)]
        path_counters: Dict[str, int] = {}    # Tracks sibling slug collisions to disambiguate duplicates

        for el in elements:
            node = ParsedNode(
                node_type=el.node_type,
                content=el.content,
                page_number=el.page_number,
                title=el.title,
                section_number=el.section_number,
                level=el.level,
                bounding_box=el.bounding_box,
                metadata=el.metadata
            )

            if el.node_type == "heading":
                # Find appropriate parent in the stack based on heading level
                while heading_stack and heading_stack[-1].level >= el.level:
                    heading_stack.pop()

                if heading_stack:
                    parent = heading_stack[-1]
                    parent.add_child(node)
                    base_slug = slugify(node.title or f"heading-{node.level}")
                    raw_path = f"{parent.section_path}/{base_slug}"
                else:
                    node.order_index = len(root_nodes)
                    root_nodes.append(node)
                    base_slug = slugify(node.title or f"heading-{node.level}")
                    raw_path = f"/{base_slug}"

                # Disambiguate duplicate headings under the same path prefix
                count = path_counters.get(raw_path, 0) + 1
                path_counters[raw_path] = count
                if count > 1:
                    node.section_path = f"{raw_path}-{count}"
                else:
                    node.section_path = raw_path

                heading_stack.append(node)

            else:
                # Leaf node: paragraph, list, table, figure
                if heading_stack:
                    parent = heading_stack[-1]
                    parent.add_child(node)
                    leaf_slug = slugify(node.title or f"{node.node_type}-{node.order_index + 1}")
                    raw_path = f"{parent.section_path}/{leaf_slug}"
                else:
                    # Content appearing before any heading
                    node.order_index = len(root_nodes)
                    root_nodes.append(node)
                    leaf_slug = slugify(node.title or f"{node.node_type}-{node.order_index + 1}")
                    raw_path = f"/{leaf_slug}"

                count = path_counters.get(raw_path, 0) + 1
                path_counters[raw_path] = count
                if count > 1:
                    node.section_path = f"{raw_path}-{count}"
                else:
                    node.section_path = raw_path

        # Bottom-up post-order traversal to calculate deterministic content hashes
        for root in root_nodes:
            self._compute_hashes_bottom_up(root)

        # Compute document-level Merkle root hash
        root_hashes = [r.content_hash for r in root_nodes]
        combined_root_str = "|".join(root_hashes)
        document_root_hash = hashlib.sha256(combined_root_str.encode("utf-8")).hexdigest()

        return root_nodes, document_root_hash

    def _compute_hashes_bottom_up(self, node: ParsedNode) -> str:
        """Recursively calculate content hashes bottom-up."""
        children_hashes = []
        for child in node.children:
            child_hash = self._compute_hashes_bottom_up(child)
            children_hashes.append(child_hash)

        node.content_hash = compute_node_hash(
            node_type=node.node_type,
            content=node.content,
            title=node.title,
            children_hashes=children_hashes,
            metadata=node.metadata
        )
        return node.content_hash

    def flatten_tree(self, root_nodes: List[ParsedNode]) -> List[ParsedNode]:
        """Flatten hierarchical tree into a pre-order list of nodes for persistence."""
        flat: List[ParsedNode] = []

        def _dfs(n: ParsedNode):
            flat.append(n)
            for child in n.children:
                _dfs(child)

        for root in root_nodes:
            _dfs(root)

        return flat
