"""
OCR Service
===========
Converts scanned / image-only PDFs into plain text, page by page.

Responsibilities:
  - Detect whether a PDF is image-only (re-uses detector signals when available)
  - Rasterise each PDF page into a PIL Image
  - Run OCR (Tesseract via pytesseract)
  - Return a list of OcrPage objects with page number + extracted text

Design decisions:
  - This service is completely independent: it does NOT import anything from
    the extractor or engine layers, only from models and config.
  - All heavy imports (pdf2image, pytesseract, PIL) are lazy so the app
    starts correctly even when the OCR libraries are not installed.
  - Errors are captured per-page and surfaced in OcrResult without raising.

Dependencies (optional — install when OCR is needed):
    pip install pytesseract pdf2image pillow
    # Also requires Tesseract-OCR and Poppler installed on the OS.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OCR output models (independent of main models.py)
# ---------------------------------------------------------------------------

@dataclass
class OcrPage:
    """OCR result for a single PDF page."""
    page_number: int          # 1-indexed
    text: str                 # OCR output
    word_count: int = 0
    confidence: float = 1.0   # average per-word confidence if available
    error: str | None = None  # set if OCR failed for this page


@dataclass
class OcrResult:
    """Full OCR result for a document."""
    pages: list[OcrPage] = field(default_factory=list)
    total_pages: int = 0
    ocr_engine: str = "unknown"
    language: str = "eng"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenate all page texts with page separators."""
        parts = []
        for page in self.pages:
            parts.append(f"\n--- Page {page.page_number} ---\n{page.text}")
        return "\n".join(parts)

    @property
    def successful_pages(self) -> list[OcrPage]:
        return [p for p in self.pages if p.error is None]

    @property
    def is_empty(self) -> bool:
        return not any(p.text.strip() for p in self.pages)


# ---------------------------------------------------------------------------
# OCR Service
# ---------------------------------------------------------------------------

class OcrService:
    """
    Stateless OCR service.  Instantiate once and call run_ocr() repeatedly.

    Parameters
    ----------
    engine   : 'tesseract' (default) or 'easyocr'
    language : Tesseract language code(s) e.g. 'eng', 'eng+hin'
    dpi      : rasterisation resolution (higher = better quality, slower)
    """

    def __init__(
        self,
        engine: str = "tesseract",
        language: str = "eng",
        dpi: int = 200,
    ) -> None:
        self.engine = engine
        self.language = language
        self.dpi = dpi

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ocr(self, filepath: str) -> OcrResult:
        """
        Run OCR on the PDF at `filepath`.

        Returns an OcrResult.  Never raises.
        """
        result = OcrResult(ocr_engine=self.engine, language=self.language)

        try:
            images = self._rasterise_pdf(filepath)
        except Exception as exc:
            msg = f"PDF rasterisation failed: {exc}"
            logger.error("OcrService: %s", msg)
            result.errors.append(msg)
            return result

        result.total_pages = len(images)

        for page_num, image in enumerate(images, start=1):
            page = self._ocr_image(image, page_num)
            result.pages.append(page)

        if result.is_empty:
            result.warnings.append(
                "OCR produced no text. The document may use an unsupported language "
                "or the image quality may be too low."
            )

        logger.info(
            "OcrService: completed — %d/%d pages successful, total chars=%d",
            len(result.successful_pages),
            result.total_pages,
            sum(len(p.text) for p in result.successful_pages),
        )
        return result

    @staticmethod
    def is_available() -> bool:
        """Returns True if all OCR dependencies are installed."""
        try:
            import pytesseract  # noqa: F401
            import pdf2image    # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def availability_report() -> dict[str, Any]:
        """
        Returns a dict describing which dependencies are present.
        Useful for the Detection Report and admin diagnostics.
        """
        report: dict[str, Any] = {}

        try:
            import pdf2image  # noqa: F401
            report["pdf2image"] = True
        except ImportError:
            report["pdf2image"] = False

        try:
            from PIL import Image  # noqa: F401
            report["pillow"] = True
        except ImportError:
            report["pillow"] = False

        try:
            import pytesseract
            report["pytesseract"] = True
            try:
                ver = pytesseract.get_tesseract_version()
                report["tesseract_version"] = str(ver)
            except Exception:
                report["tesseract_version"] = "unknown (binary not found?)"
        except ImportError:
            report["pytesseract"] = False

        report["ready"] = all([
            report.get("pdf2image"),
            report.get("pillow"),
            report.get("pytesseract"),
        ])
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rasterise_pdf(self, filepath: str) -> list:
        """
        Convert each PDF page to a PIL Image using pdf2image (Poppler).
        Returns a list of PIL Image objects.
        """
        try:
            from pdf2image import convert_from_path
        except ImportError as exc:
            raise RuntimeError(
                "pdf2image is not installed. Run: pip install pdf2image\n"
                "Also ensure Poppler is installed on your system."
            ) from exc

        images = convert_from_path(filepath, dpi=self.dpi)
        logger.debug("OcrService: rasterised %d pages at %d DPI", len(images), self.dpi)
        return images

    def _ocr_image(self, image, page_number: int) -> OcrPage:
        """Run OCR on a single PIL Image and return an OcrPage."""
        try:
            if self.engine == "tesseract":
                return self._tesseract_ocr(image, page_number)
            elif self.engine == "easyocr":
                return self._easyocr_ocr(image, page_number)
            else:
                return OcrPage(
                    page_number=page_number,
                    text="",
                    error=f"Unknown OCR engine: {self.engine}",
                )
        except Exception as exc:
            logger.warning("OcrService: page %d OCR failed: %s", page_number, exc)
            return OcrPage(
                page_number=page_number,
                text="",
                error=str(exc),
            )

    def _tesseract_ocr(self, image, page_number: int) -> OcrPage:
        """Run Tesseract OCR via pytesseract."""
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError(
                "pytesseract is not installed. Run: pip install pytesseract"
            ) from exc

        # Use page segmentation mode 6 (assume uniform block of text)
        config = "--psm 6"
        text = pytesseract.image_to_string(image, lang=self.language, config=config)

        # Attempt confidence extraction
        try:
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
            confs = [c for c in data["conf"] if c != -1]
            avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 1.0
        except Exception:
            avg_conf = 1.0

        words = [w for w in text.split() if w.strip()]
        return OcrPage(
            page_number=page_number,
            text=text.strip(),
            word_count=len(words),
            confidence=round(avg_conf, 3),
        )

    def _easyocr_ocr(self, image, page_number: int) -> OcrPage:
        """Run EasyOCR (alternative OCR backend)."""
        try:
            import easyocr  # noqa: F401
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "easyocr is not installed. Run: pip install easyocr"
            ) from exc

        import easyocr
        import numpy as np

        reader = easyocr.Reader([self.language], gpu=False, verbose=False)
        img_array = np.array(image)
        results = reader.readtext(img_array, detail=1)

        lines = [r[1] for r in results]
        text = "\n".join(lines)
        confs = [r[2] for r in results]
        avg_conf = (sum(confs) / len(confs)) if confs else 1.0

        return OcrPage(
            page_number=page_number,
            text=text.strip(),
            word_count=len(text.split()),
            confidence=round(avg_conf, 3),
        )


# ---------------------------------------------------------------------------
# Module-level helper — creates an OCR service from engine_config
# ---------------------------------------------------------------------------

def get_ocr_service() -> OcrService:
    """
    Factory that reads engine_config and returns a configured OcrService.
    Import this rather than constructing OcrService directly.
    """
    from app.services.import_engine.config import engine_config
    return OcrService(
        engine=engine_config.ocr_engine,
        language=engine_config.ocr_language,
        dpi=engine_config.ocr_dpi,
    )
