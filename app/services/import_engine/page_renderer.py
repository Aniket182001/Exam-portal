"""
Page Renderer
=============
Standalone service responsible for rasterising PDF pages into images.
This keeps vision-based AI capabilities decoupled from local OCR logic.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PageRenderer:
    """
    Converts PDF pages into raw image bytes using pdf2image.
    """
    
    @staticmethod
    def is_available() -> bool:
        try:
            import fitz
            return True
        except ImportError:
            return False

    @staticmethod
    def render_pages(filepath: str, dpi: int = 200, limit: Optional[int] = 10) -> list[bytes]:
        """
        Renders the first `limit` pages of a PDF to JPEG byte arrays.
        """
        if not PageRenderer.is_available():
            logger.warning("PageRenderer: PyMuPDF is not installed. Cannot render PDF pages to images.")
            return []

        import fitz
        
        try:
            doc = fitz.open(filepath)
            limit = min(limit, len(doc)) if limit else len(doc)
            
            image_bytes_list = []
            # Calculate zoom factor for DPI (72 dpi is default, so dpi/72)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            for i in range(limit):
                page = doc[i]
                pix = page.get_pixmap(matrix=mat, alpha=False)
                # Output to JPEG byte array
                image_bytes_list.append(pix.tobytes("jpeg", 85))
                
            doc.close()
            return image_bytes_list
        except Exception as exc:
            logger.exception("PageRenderer: failed to render pages for %s", filepath)
            return []
