import logging
from typing import List, Dict, Any, Tuple
import pymupdf

logger = logging.getLogger(__name__)


class TableExtractor:
    """Extracts tables from PDF pages using PyMuPDF table finder."""

    @staticmethod
    def extract_tables_from_page(page: pymupdf.Page) -> Tuple[List[Dict[str, Any]], List[pymupdf.Rect]]:
        """
        Find tables on the page.
        Returns:
            - List of table data dicts with markdown, headers, rows, bbox
            - List of table bounding boxes to avoid re-extracting as plain paragraphs
        """
        tables = []
        table_rects = []

        try:
            tab_finder = page.find_tables()
            if tab_finder and tab_finder.tables:
                for idx, tab in enumerate(tab_finder.tables):
                    rect = tab.bbox
                    table_rects.append(pymupdf.Rect(rect))

                    extracted_data = tab.extract()
                    if not extracted_data:
                        continue

                    # First row as header if non-empty
                    headers = [str(col).strip() if col is not None else "" for col in extracted_data[0]]
                    rows = []
                    for row in extracted_data[1:]:
                        rows.append([str(col).strip() if col is not None else "" for col in row])

                    # Build clean Markdown table representation
                    md_lines = []
                    if headers:
                        md_lines.append("| " + " | ".join(headers) + " |")
                        md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                    for row in rows:
                        # Pad row if shorter than headers
                        padded_row = row + [""] * max(0, len(headers) - len(row))
                        md_lines.append("| " + " | ".join(padded_row[:len(headers)]) + " |")

                    markdown_repr = "\n".join(md_lines)

                    tables.append({
                        "node_type": "table",
                        "title": f"Table {idx + 1}",
                        "content": markdown_repr,
                        "headers": headers,
                        "rows": rows,
                        "bounding_box": [rect[0], rect[1], rect[2], rect[3]],
                        "page_number": page.number + 1,
                        "metadata": {
                            "rows_count": len(rows),
                            "cols_count": len(headers),
                            "format": "markdown_table"
                        }
                    })
        except Exception as e:
            logger.warning("Table detection encountered an issue on page %s: %s", page.number + 1, str(e))

        return tables, table_rects
