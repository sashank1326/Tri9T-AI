import io
import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import pymupdf

from app.core.exceptions import PDFParseError
from app.services.pdf_parser.ocr import OCROptimizer
from app.services.pdf_parser.table_extractor import TableExtractor

logger = logging.getLogger(__name__)

# Regex patterns for section numbers and list items
SECTION_NUMBER_PATTERN = re.compile(
    r'^(?:(?:Section|Chapter|Part)\s+)?(\d+(?:\.\d+)*)\.?\s+(.+)$',
    re.IGNORECASE
)
LIST_ITEM_PATTERN = re.compile(r'^(?:[•\-\*–—]|(?:\(?\d+[\.\)])|(?:\(?[a-zA-Z][\.\)]))\s+(.+)$')
FIGURE_CAPTION_PATTERN = re.compile(r'^(?:Figure|Fig\.|Diagram|Illustration)\s+\d+[:\.\-]?\s*(.*)$', re.IGNORECASE)


class RawElement:
    """Represents an extracted element before hierarchy tree assembly."""
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
        self.node_type = node_type
        self.content = content.strip()
        self.page_number = page_number
        self.title = (title or "").strip() or None
        self.section_number = (section_number or "").strip() or None
        self.level = level
        self.bounding_box = bounding_box
        self.metadata = metadata or {}


class PDFExtractor:
    """Modular PDF content extractor using PyMuPDF and OCR fallback."""

    def __init__(self):
        self.ocr = OCROptimizer()
        self.table_extractor = TableExtractor()

    def extract_document(
        self,
        pdf_source: Union[str, bytes]
    ) -> Tuple[List[RawElement], int]:
        """
        Extract all raw elements (headings, sections, paragraphs, lists, tables, figures)
        from a PDF filepath or raw bytes.
        """
        try:
            if isinstance(pdf_source, bytes):
                doc = pymupdf.open(stream=pdf_source, filetype="pdf")
            else:
                doc = pymupdf.open(pdf_source)
        except Exception as e:
            raise PDFParseError(f"Could not open PDF document: {str(e)}") from e

        page_count = len(doc)
        if page_count == 0:
            raise PDFParseError("PDF document has 0 pages.")

        # First pass: analyze font sizes across document to calibrate body font vs heading font
        body_font_size = self._estimate_body_font_size(doc)
        logger.info("Estimated body font size: %.1f pt across %d pages", body_font_size, page_count)

        raw_elements: List[RawElement] = []

        for page_idx in range(page_count):
            page = doc[page_idx]
            page_num = page_idx + 1

            # 1. Extract Tables
            tables, table_rects = self.table_extractor.extract_tables_from_page(page)

            # 2. Extract Figures / Images
            figure_elements, figure_rects = self._extract_figures(page, page_num)

            # 3. Extract Text Blocks
            page_text_elements = self._extract_text_blocks(
                page=page,
                page_num=page_num,
                body_font_size=body_font_size,
                excluded_rects=table_rects + figure_rects
            )

            # 4. Check if page is empty or scanned (fallback to OCR)
            if not page_text_elements and not tables and not figure_elements:
                logger.info("Page %d has minimal native text. Attempting OCR fallback...", page_num)
                ocr_text = self.ocr.ocr_page_pixmap(page)
                if ocr_text:
                    ocr_elements = self._parse_plain_text_to_elements(ocr_text, page_num, is_ocr=True)
                    page_text_elements.extend(ocr_elements)

            # Merge and sort page elements vertically (top to bottom)
            page_all = []
            for t in tables:
                page_all.append(RawElement(
                    node_type="table",
                    content=t["content"],
                    page_number=page_num,
                    title=t.get("title"),
                    level=0,
                    bounding_box=t.get("bounding_box"),
                    metadata=t.get("metadata")
                ))

            page_all.extend(figure_elements)
            page_all.extend(page_text_elements)

            # Sort by vertical position (y0)
            page_all.sort(key=lambda el: el.bounding_box[1] if el.bounding_box else 0.0)

            raw_elements.extend(page_all)

        doc.close()
        return raw_elements, page_count

    def _estimate_body_font_size(self, doc: pymupdf.Document) -> float:
        """Estimate the predominant body text font size."""
        font_counts: Dict[float, int] = {}
        for page in doc:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            size = round(span.get("size", 10.0), 1)
                            chars = len(span.get("text", "").strip())
                            if chars > 0:
                                font_counts[size] = font_counts.get(size, 0) + chars

        if not font_counts:
            return 11.0
        # Return most frequent font size by character count
        return max(font_counts.items(), key=lambda item: item[1])[0]

    def _extract_figures(self, page: pymupdf.Page, page_num: int) -> Tuple[List[RawElement], List[pymupdf.Rect]]:
        """Identify figure / image bounding boxes and captions."""
        figures = []
        figure_rects = []
        image_list = page.get_images(full=True)

        for img_idx, img in enumerate(image_list):
            try:
                # Find image rect on the page
                rects = page.get_image_rects(img[0])
                for rect in rects:
                    figure_rects.append(rect)
                    # Check for adjacent caption below the image
                    caption_rect = pymupdf.Rect(rect.x0 - 20, rect.y1, rect.x1 + 20, rect.y1 + 40)
                    caption_text = page.get_text("text", clip=caption_rect).strip()

                    title = f"Figure {img_idx + 1}"
                    caption_match = FIGURE_CAPTION_PATTERN.match(caption_text)
                    if caption_match and caption_match.group(1):
                        title = f"Figure {img_idx + 1}: {caption_match.group(1)}"

                    figures.append(RawElement(
                        node_type="figure",
                        content=caption_text if caption_text else f"[Image/Diagram: {title}]",
                        page_number=page_num,
                        title=title,
                        bounding_box=[rect.x0, rect.y0, rect.x1, rect.y1],
                        metadata={"image_index": img_idx, "xref": img[0]}
                    ))
            except Exception as e:
                logger.debug("Figure extraction note for page %s: %s", page_num, str(e))

        return figures, figure_rects

    def _extract_text_blocks(
        self,
        page: pymupdf.Page,
        page_num: int,
        body_font_size: float,
        excluded_rects: List[pymupdf.Rect]
    ) -> List[RawElement]:
        """Extract structured text blocks, headings, paragraphs, and list items."""
        elements: List[RawElement] = []
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # text blocks only
                continue

            bbox = block.get("bbox", [0, 0, 0, 0])
            block_rect = pymupdf.Rect(bbox)

            # Skip if this block is inside an already extracted table or figure
            if any(block_rect.intersects(ex_rect) for ex_rect in excluded_rects):
                continue

            # Analyze block lines and spans
            lines = block.get("lines", [])
            if not lines:
                continue

            block_text = ""
            max_size = 0.0
            is_bold = False

            for line in lines:
                line_text = ""
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    line_text += span_text
                    max_size = max(max_size, span.get("size", 10.0))
                    # PyMuPDF font flags: bit 4 (16) is bold
                    flags = span.get("flags", 0)
                    if flags & 2 or flags & 16 or "bold" in span.get("font", "").lower():
                        is_bold = True
                block_text += line_text + "\n"

            block_text = block_text.strip()
            if not block_text:
                continue

            # Determine element type
            element = self._classify_text_block(
                text=block_text,
                max_size=max_size,
                is_bold=is_bold,
                body_font_size=body_font_size,
                page_num=page_num,
                bbox=bbox
            )
            elements.append(element)

        return elements

    def _classify_text_block(
        self,
        text: str,
        max_size: float,
        is_bold: bool,
        body_font_size: float,
        page_num: int,
        bbox: List[float]
    ) -> RawElement:
        """Classify a text block into heading, list, or paragraph based on size, formatting, and numbering."""
        first_line = text.split("\n")[0].strip()

        # Check for Section Numbering (e.g., "1. Introduction", "2.1 Safety Protocol")
        sec_match = SECTION_NUMBER_PATTERN.match(first_line)
        if sec_match:
            sec_num = sec_match.group(1)
            title = sec_match.group(2).strip()
            # Level based on dot count: "1" -> 1, "1.1" -> 2, "1.1.2" -> 3
            level = sec_num.count(".") + 1
            return RawElement(
                node_type="heading",
                content=text,
                page_number=page_num,
                title=f"{sec_num} {title}",
                section_number=sec_num,
                level=level,
                bounding_box=bbox,
                metadata={"font_size": max_size, "is_bold": is_bold}
            )

        # Check for Heading based on font size / bold styling
        is_large_font = max_size >= (body_font_size * 1.15)
        is_short = len(text) < 140 and len(text.split("\n")) <= 2

        if (is_large_font or (is_bold and is_short)) and not text.endswith("."):
            # Determine level based on relative font scale
            if max_size >= body_font_size * 1.5:
                level = 1
            elif max_size >= body_font_size * 1.3:
                level = 2
            else:
                level = 3

            return RawElement(
                node_type="heading",
                content=text,
                page_number=page_num,
                title=first_line,
                level=level,
                bounding_box=bbox,
                metadata={"font_size": max_size, "is_bold": is_bold}
            )

        # Check for List Item
        list_match = LIST_ITEM_PATTERN.match(first_line)
        if list_match:
            return RawElement(
                node_type="list",
                content=text,
                page_number=page_num,
                level=0,
                bounding_box=bbox,
                metadata={"list_item": True}
            )

        # Regular Paragraph
        return RawElement(
            node_type="paragraph",
            content=text,
            page_number=page_num,
            level=0,
            bounding_box=bbox,
            metadata={"font_size": max_size}
        )

    def _parse_plain_text_to_elements(
        self,
        text: str,
        page_num: int,
        is_ocr: bool = False
    ) -> List[RawElement]:
        """Convert plain text (e.g. from OCR) into structured raw elements."""
        elements = []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        for p in paragraphs:
            first_line = p.split("\n")[0].strip()
            sec_match = SECTION_NUMBER_PATTERN.match(first_line)
            if sec_match:
                sec_num = sec_match.group(1)
                title = sec_match.group(2).strip()
                level = sec_num.count(".") + 1
                elements.append(RawElement(
                    node_type="heading",
                    content=p,
                    page_number=page_num,
                    title=f"{sec_num} {title}",
                    section_number=sec_num,
                    level=level,
                    metadata={"source": "ocr" if is_ocr else "text"}
                ))
            elif LIST_ITEM_PATTERN.match(first_line):
                elements.append(RawElement(
                    node_type="list",
                    content=p,
                    page_number=page_num,
                    metadata={"source": "ocr" if is_ocr else "text"}
                ))
            else:
                elements.append(RawElement(
                    node_type="paragraph",
                    content=p,
                    page_number=page_num,
                    metadata={"source": "ocr" if is_ocr else "text"}
                ))
        return elements
