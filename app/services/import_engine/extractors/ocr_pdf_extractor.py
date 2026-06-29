"""
OCR PDF Extractor
=================
Handles scanned / image-only PDFs.

Pipeline:
  PDF → OcrService.run_ocr() → OcrResult → text_parse (shared logic) → ExtractionResult

Graceful degradation:
  - If OCR libraries are unavailable, returns an ExtractionResult with a
    clear warning and zero questions (same as the old stub).
  - If OCR is disabled via config, skips OCR and returns an informative warning.
  - Errors on individual pages are surfaced in result.warnings, not raised.
"""

from __future__ import annotations

import logging

from app.services.import_engine.config import engine_config
from app.services.import_engine.extractors.base import BaseExtractor
from app.services.import_engine.extractors.text_pdf_extractor import TextPdfExtractor
from app.services.import_engine.models import (
    DocumentType,
    ExtractedQuestion,
    ExtractionResult,
)
from app.services.import_engine.ocr_service import OcrResult, get_ocr_service

logger = logging.getLogger(__name__)


class OcrPdfExtractor(BaseExtractor):
    """
    Full OCR-based extractor for scanned / image-only PDFs.
    Uses the OcrService for rasterisation + OCR, then delegates text
    parsing to the same logic used by TextPdfExtractor.
    """

    extractor_name = "ocr_pdf"

    def extract(self, filepath: str) -> ExtractionResult:
        result = self._make_result(DocumentType.OCR_PDF)
        result.extractor_name = self.extractor_name

        # ------------------------------------------------------------------
        # Guard: check config and library availability
        # ------------------------------------------------------------------
        if not engine_config.ocr_enabled:
            result.warnings.append(
                "OCR is disabled (ENABLE_OCR=false). "
                "Enable it to extract text from scanned PDFs."
            )
            logger.info("OcrPdfExtractor: OCR disabled by config, skipping %s", filepath)
            return result

        from app.services.import_engine.ocr_service import OcrService
        if not OcrService.is_available():
            avail = OcrService.availability_report()
            missing = [k for k, v in avail.items() if k != "ready" and not v]
            result.warnings.append(
                f"OCR dependencies are not installed ({', '.join(missing)}). "
                "Install with: pip install pytesseract pdf2image pillow — "
                "and ensure Tesseract + Poppler are installed on the system."
            )
            result.metadata["ocr_availability"] = avail
            logger.warning("OcrPdfExtractor: dependencies missing — %s", missing)
            return result

        # ------------------------------------------------------------------
        # Stage 1: Run OCR
        # ------------------------------------------------------------------
        ocr_svc = get_ocr_service()
        logger.info(
            "OcrPdfExtractor: running OCR on %s (engine=%s, lang=%s, dpi=%d)",
            filepath,
            ocr_svc.engine,
            ocr_svc.language,
            ocr_svc.dpi,
        )

        ocr_result: OcrResult = ocr_svc.run_ocr(filepath)
        result.total_pages = ocr_result.total_pages
        result.metadata["ocr_engine"]   = ocr_result.ocr_engine
        result.metadata["ocr_language"] = ocr_result.language
        result.metadata["ocr_pages"]    = [
            {
                "page": p.page_number,
                "words": p.word_count,
                "confidence": p.confidence,
                "error": p.error,
            }
            for p in ocr_result.pages
        ]

        # Surface OCR errors as warnings (not result errors) to avoid
        # blocking the partial result
        for page in ocr_result.pages:
            if page.error:
                result.warnings.append(f"Page {page.page_number} OCR error: {page.error}")

        result.warnings.extend(ocr_result.warnings)
        result.errors.extend(ocr_result.errors)

        if ocr_result.errors:
            logger.error(
                "OcrPdfExtractor: OCR stage failed for %s: %s",
                filepath,
                ocr_result.errors,
            )
            return result

        # ------------------------------------------------------------------
        # Stage 2: Parse the OCR text with the same heuristics as TextPdf
        # ------------------------------------------------------------------
        full_text = ocr_result.full_text
        if not full_text.strip():
            result.warnings.append("OCR produced no usable text for this document.")
            return result

        # Reuse TextPdfExtractor's paragraph-level parser
        _text_extractor = TextPdfExtractor()
        questions: list[ExtractedQuestion] = _text_extractor._parse_text(full_text)

        # Attach page provenance from OCR data
        for q in questions:
            q.metadata["ocr_extracted"] = True

        # Apply a slight confidence penalty to reflect OCR uncertainty
        for q in questions:
            q.confidence = round(q.confidence * 0.90, 3)

        result.questions = questions

        logger.info(
            "OcrPdfExtractor: extracted %d questions from %d OCR pages",
            len(questions),
            ocr_result.total_pages,
        )
        return result
