import pytest
from unittest.mock import MagicMock, patch
from app.services.pdf_parser import (
    PDFExtractor,
    HierarchyReconstructor,
    RawElement,
    OCROptimizer
)
from app.core.hashing import compute_node_hash, compute_text_hash


def test_pdf_extractor_basic(pdf_v1_bytes):
    """Test PDFExtractor accurately extracts raw elements and detects page count."""
    extractor = PDFExtractor()
    elements, page_count = extractor.extract_document(pdf_v1_bytes)

    assert page_count == 3
    assert len(elements) > 0

    types = {el.node_type for el in elements}
    assert "heading" in types
    assert "paragraph" in types


def test_hierarchy_reconstruction_and_duplicate_headings(pdf_v1_bytes):
    """
    Test hierarchy reconstructor builds a nested tree and properly disambiguates
    duplicate headings under different parent chapters.
    """
    extractor = PDFExtractor()
    elements, _ = extractor.extract_document(pdf_v1_bytes)

    reconstructor = HierarchyReconstructor()
    root_nodes, root_hash = reconstructor.reconstruct(elements)

    assert len(root_nodes) > 0
    assert root_hash is not None
    assert len(root_hash) == 64  # SHA-256 hex string

    flattened = reconstructor.flatten_tree(root_nodes)
    paths = [n.section_path for n in flattened]

    # Verify all section paths are unique (no collisions)
    assert len(paths) == len(set(paths)), "Duplicate section paths detected!"

    # Verify duplicate heading titles "Warnings and Precautions" exist with unique paths
    dup_headings = [n for n in flattened if n.title == "Warnings and Precautions"]
    assert len(dup_headings) == 2
    assert dup_headings[0].section_path != dup_headings[1].section_path
    # One should be under hardware, the other under software
    assert "hardware" in dup_headings[0].section_path or "hardware" in dup_headings[1].section_path
    assert "software" in dup_headings[0].section_path or "software" in dup_headings[1].section_path


def test_content_hashing_determinism():
    """Verify compute_node_hash produces deterministic SHA-256 hashes."""
    h1 = compute_node_hash("heading", "Emergency Stop Protocol", "2.2 Safety")
    h2 = compute_node_hash("heading", "Emergency Stop Protocol", "2.2 Safety")
    h3 = compute_node_hash("heading", "Emergency Stop Protocol - Modified", "2.2 Safety")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_hierarchical_merkle_hashing():
    """Verify modifying a child node's hash alters the parent container's hash."""
    child_hash_v1 = compute_node_hash("paragraph", "Voltage 120 kV")
    child_hash_v2 = compute_node_hash("paragraph", "Voltage 140 kV")

    parent_h1 = compute_node_hash("section", "", "Radiation Safety", children_hashes=[child_hash_v1])
    parent_h2 = compute_node_hash("section", "", "Radiation Safety", children_hashes=[child_hash_v2])

    assert parent_h1 != parent_h2


def test_ocr_fallback_triggered():
    """Verify OCR fallback is invoked when a page has no extractable native text."""
    extractor = PDFExtractor()
    with patch.object(extractor.ocr, "ocr_page_pixmap", return_value="1. Scanned Heading\n\nScanned requirement text.") as mock_ocr:
        # Create an empty 1-page PDF
        import pymupdf
        blank_doc = pymupdf.open()
        blank_doc.new_page(width=400, height=400)
        blank_bytes = blank_doc.tobytes()
        blank_doc.close()

        elements, page_count = extractor.extract_document(blank_bytes)
        assert page_count == 1
        mock_ocr.assert_called_once()
        assert len(elements) >= 1
        assert elements[0].node_type == "heading"
