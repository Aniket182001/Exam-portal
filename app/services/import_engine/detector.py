"""
Detector Layer
==============
Classifies an uploaded file into a DocumentType by inspecting:
  - File extension / MIME type
  - PDF metadata (producer, creator)
  - Presence of selectable text
  - Common platform signatures embedded in PDF
  - Layout characteristics (image-heavy = likely scanned)

Returns a DetectionResult with a single DocumentType and a confidence score.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from typing import Any

from app.services.import_engine.config import engine_config
from app.services.import_engine.models import DetectionResult, DocumentType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection thresholds — driven by engine_config (env vars) so they can be
# tuned without code changes.
# ---------------------------------------------------------------------------
# These are read at call time via properties, not module load time.

# ---------------------------------------------------------------------------
# Known PDF platform signatures
# Tuple of (substring_to_search, document_type, weight)
# These are searched in PDF metadata fields: Producer, Creator, Author.
# ---------------------------------------------------------------------------
_PDF_PLATFORM_SIGNATURES: list[tuple[str, DocumentType, float]] = [
    # Microsoft Forms exports
    ("microsoft forms",     DocumentType.MICROSOFT_FORMS,   0.90),
    ("microsoft office",    DocumentType.MICROSOFT_FORMS,   0.55),
    ("word",                DocumentType.MICROSOFT_FORMS,   0.40),

    # Google Forms exports
    ("google",              DocumentType.GOOGLE_FORMS,      0.70),
    ("chromium",            DocumentType.GOOGLE_FORMS,      0.55),
    ("skia",                DocumentType.GOOGLE_FORMS,      0.60),  # Chrome PDF renderer

    # AIQM LMS exports
    ("aiqm",                DocumentType.AIQM_LMS,          0.95),
    ("aiqm lms",            DocumentType.AIQM_LMS,          0.99),
]

# Text-based signatures searched in the first ~1000 chars of extracted text
_TEXT_CONTENT_SIGNATURES: list[tuple[str, DocumentType, float]] = [
    # AIQM LMS
    ("aiqm",                DocumentType.AIQM_LMS,          0.90),
    ("examination portal",  DocumentType.AIQM_LMS,          0.75),

    # Microsoft Forms
    ("microsoft forms",     DocumentType.MICROSOFT_FORMS,   0.85),

    # Google Forms
    ("google forms",        DocumentType.GOOGLE_FORMS,      0.85),
]

_MIN_TEXT_CHARS_PER_PAGE = 80  # kept for reference; engine_config.ocr_chars_per_page_threshold is used at runtime


class DocumentDetector:
    """
    Stateless detector — call detect() with file path + optional mime type.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, filepath: str, mime_type: str | None = None) -> DetectionResult:
        """
        Inspect the file and return a DetectionResult.
        Never raises; returns DocumentType.UNKNOWN on any internal error.
        """
        signals: dict[str, Any] = {}

        try:
            ext = os.path.splitext(filepath)[1].lower()
            signals["extension"] = ext

            # Resolve MIME type if not provided
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(filepath)
            signals["mime_type"] = mime_type

            # --- Non-PDF formats resolved by extension alone ---------------
            if ext in (".xlsx", ".xls"):
                return DetectionResult(
                    doc_type=DocumentType.EXCEL,
                    confidence=0.99,
                    signals=signals,
                )

            if ext in (".docx", ".doc"):
                return DetectionResult(
                    doc_type=DocumentType.WORD,
                    confidence=0.99,
                    signals=signals,
                )

            # --- PDF analysis ---------------------------------------------
            if ext == ".pdf" or (mime_type and "pdf" in mime_type):
                return self._detect_pdf(filepath, signals)

            # --- Unknown ---------------------------------------------------
            logger.warning("DocumentDetector: unrecognised extension %s", ext)
            return DetectionResult(
                doc_type=DocumentType.UNKNOWN,
                confidence=0.5,
                signals=signals,
            )

        except Exception as exc:
            logger.exception("DocumentDetector.detect() failed: %s", exc)
            signals["error"] = str(exc)
            return DetectionResult(
                doc_type=DocumentType.UNKNOWN,
                confidence=0.0,
                signals=signals,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_pdf(self, filepath: str, signals: dict) -> DetectionResult:
        """Deep inspection for PDF files."""
        try:
            import pypdf  # imported lazily so the detector works without pypdf
        except ImportError:
            logger.error("pypdf not installed — cannot deep-inspect PDF")
            return DetectionResult(
                doc_type=DocumentType.TEXT_PDF,
                confidence=0.40,
                requires_ocr=False,
                signals={**signals, "error": "pypdf_unavailable"},
            )

        with open(filepath, "rb") as fh:
            reader = pypdf.PdfReader(fh)
            total_pages = len(reader.pages)
            signals["total_pages"] = total_pages

            # --- Metadata probe -------------------------------------------
            meta = reader.metadata or {}
            producer = (meta.get("/Producer") or "").lower()
            creator  = (meta.get("/Creator")  or "").lower()
            author   = (meta.get("/Author")   or "").lower()
            meta_blob = f"{producer} {creator} {author}"
            signals["pdf_producer"] = producer
            signals["pdf_creator"]  = creator

            platform_type, platform_conf = self._match_platform_signatures(meta_blob)
            signals["platform_match"] = platform_type.value if platform_type else None

            # --- Text extraction probe ------------------------------------
            total_chars = 0
            first_page_text = ""
            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    if i == 0:
                        first_page_text = text
                    total_chars += len(text)
                except Exception:
                    pass

            chars_per_page = total_chars / max(total_pages, 1)
            signals["chars_per_page"] = round(chars_per_page, 1)
            signals["total_chars"]    = total_chars
            has_text = chars_per_page >= _MIN_TEXT_CHARS_PER_PAGE

            # --- Content signature probe (first 1000 chars) ---------------
            content_type, content_conf = self._match_content_signatures(
                first_page_text[:1000]
            )
            signals["content_match"] = content_type.value if content_type else None

            # --- Decision logic -------------------------------------------
            #
            # Priority order:
            #   1. AIQM LMS   – very specific, highest priority
            #   2. Platform signatures from metadata (Forms exports)
            #   3. Platform signatures from page content
            #   4. Text density classification (OCR / low-density / normal)

            # Read thresholds from config at call time (honours env var changes)
            ocr_threshold      = engine_config.ocr_chars_per_page_threshold
            low_density_limit  = engine_config.low_density_warning_threshold

            # Enrich signals with density classification
            if chars_per_page < ocr_threshold:
                signals["text_density"] = "image_only"
                signals["ocr_recommended"] = True
            elif chars_per_page < low_density_limit:
                signals["text_density"] = "low"
                signals["ocr_recommended"] = True   # advisory — not forced
            else:
                signals["text_density"] = "normal"
                signals["ocr_recommended"] = False

            # Annotate OCR availability for the Detection Report
            from app.services.import_engine.ocr_service import OcrService
            signals["ocr_available"] = OcrService.is_available()
            signals["ocr_enabled"]   = engine_config.ocr_enabled
            signals["ai_enabled"]    = engine_config.ai_enabled
            signals["ai_provider"]   = engine_config.ai_provider

            if platform_type == DocumentType.AIQM_LMS or content_type == DocumentType.AIQM_LMS:
                return DetectionResult(
                    doc_type=DocumentType.AIQM_LMS,
                    confidence=0.95,
                    requires_ocr=not has_text,
                    signals=signals,
                )

            if platform_type in (DocumentType.MICROSOFT_FORMS, DocumentType.GOOGLE_FORMS):
                return DetectionResult(
                    doc_type=platform_type,
                    confidence=platform_conf,
                    requires_ocr=not has_text,
                    signals=signals,
                )

            if content_type in (DocumentType.MICROSOFT_FORMS, DocumentType.GOOGLE_FORMS):
                return DetectionResult(
                    doc_type=content_type,
                    confidence=content_conf,
                    requires_ocr=not has_text,
                    signals=signals,
                )

            # Generic text vs. scanned fallback
            if has_text:
                if chars_per_page < low_density_limit:
                    # Text present but sparse — annotate as low density
                    return DetectionResult(
                        doc_type=DocumentType.TEXT_PDF,
                        confidence=0.75,
                        requires_ocr=True,   # advisory: may benefit from OCR
                        signals={**signals, "low_density_warning": True},
                    )
                return DetectionResult(
                    doc_type=DocumentType.TEXT_PDF,
                    confidence=0.85,
                    requires_ocr=False,
                    signals=signals,
                )
            else:
                return DetectionResult(
                    doc_type=DocumentType.OCR_PDF,
                    confidence=0.80,
                    requires_ocr=True,
                    signals=signals,
                )

    def _match_platform_signatures(
        self, meta_blob: str
    ) -> tuple[DocumentType | None, float]:
        best_type: DocumentType | None = None
        best_conf = 0.0
        for substr, dtype, weight in _PDF_PLATFORM_SIGNATURES:
            if substr in meta_blob and weight > best_conf:
                best_type = dtype
                best_conf = weight
        return best_type, best_conf

    def _match_content_signatures(
        self, text: str
    ) -> tuple[DocumentType | None, float]:
        text_lower = text.lower()
        best_type: DocumentType | None = None
        best_conf = 0.0
        for substr, dtype, weight in _TEXT_CONTENT_SIGNATURES:
            if substr in text_lower and weight > best_conf:
                best_type = dtype
                best_conf = weight
        return best_type, best_conf


# Singleton — import and call detect() directly
detector = DocumentDetector()
