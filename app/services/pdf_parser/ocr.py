import logging
from typing import Optional
from PIL import Image
import pymupdf
import pytesseract

from app.config import get_settings

logger = logging.getLogger(__name__)


class OCROptimizer:
    """Optical Character Recognition helper using PyTesseract with PyMuPDF pixmaps."""

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.OCR_ENABLED
        self.tesseract_cmd = settings.TESSERACT_CMD
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def is_available(self) -> bool:
        """Check if Tesseract binary is responsive."""
        if not self.enabled:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.warning("Tesseract OCR not accessible: %s", str(e))
            return False

    def ocr_page_pixmap(self, page: pymupdf.Page, dpi: int = 200) -> str:
        """Perform OCR on an entire PDF page."""
        if not self.is_available():
            logger.info("OCR requested but Tesseract is not available or disabled.")
            return ""

        try:
            pix = page.get_pixmap(dpi=dpi)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            logger.error("OCR execution failed for page %s: %s", page.number, str(e))
            return ""

    def ocr_image_rect(self, page: pymupdf.Page, rect: pymupdf.Rect, dpi: int = 200) -> str:
        """Perform OCR on a specific bounding box of a page (e.g. figure or diagram)."""
        if not self.is_available():
            return ""
        try:
            pix = page.get_pixmap(clip=rect, dpi=dpi)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            logger.error("OCR execution failed on rect %s: %s", rect, str(e))
            return ""
