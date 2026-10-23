import hashlib
import json
from typing import Any, List, Optional


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash for a given text string after normalization."""
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_node_hash(
    node_type: str,
    content: str,
    title: Optional[str] = None,
    children_hashes: Optional[List[str]] = None,
    metadata: Optional[dict] = None
) -> str:
    """
    Compute deterministic SHA-256 hash for a document node.
    For leaf nodes: hashes normalized type + title + content.
    For container nodes: combines direct content with child node hashes (Merkle-style).
    """
    normalized_content = " ".join((content or "").strip().split())
    normalized_title = " ".join((title or "").strip().split())

    payload = {
        "type": node_type.lower(),
        "title": normalized_title,
        "content": normalized_content,
        "children_hashes": sorted(children_hashes or [])
    }

    if metadata and isinstance(metadata, dict):
        # Include structural indicators if relevant (e.g. table dimensions)
        filtered_meta = {
            k: v for k, v in metadata.items()
            if k in ("rows", "cols", "caption", "list_type")
        }
        if filtered_meta:
            payload["meta"] = filtered_meta

    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
