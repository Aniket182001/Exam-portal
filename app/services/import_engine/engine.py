"""
Import Engine — Orchestrator
============================
Single entry point for all callers.

Pipeline:
  1. DocumentDetector  → classify the file
  2. ExtractorRouter   → select the correct extractor
  3. Extractor.extract → produce ExtractionResult
  4. ValidatorLayer    → annotate questions with ValidationMessages
  5. Return            ExtractionResult

Public usage:
    from app.services.import_engine import ImportEngine

    result = ImportEngine.process(filepath, filename)

    # New-style consumer
    for q in result.valid_questions:
        print(q.question_text, q.options, q.correct_option_index)

    # Legacy-compatible consumer (existing import routes)
    legacy_list = result.to_legacy_list()
"""

from __future__ import annotations

import logging
import time

from app.services.import_engine.config import engine_config
from app.services.import_engine.detector import detector
from app.services.import_engine.extractors import (
    AiqmLmsExtractor,
    BaseExtractor,
    ExcelExtractor,
    GoogleFormsExtractor,
    MicrosoftFormsExtractor,
    OcrPdfExtractor,
    TextPdfExtractor,
    WordExtractor,
)
from app.services.import_engine.models import (
    DocumentType,
    ExtractionResult,
)
from app.services.import_engine.validator import ValidatorLayer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extractor routing table
# DocumentType → extractor class
# ---------------------------------------------------------------------------
_EXTRACTOR_MAP: dict[DocumentType, type[BaseExtractor]] = {
    DocumentType.EXCEL:           ExcelExtractor,
    DocumentType.WORD:            WordExtractor,
    DocumentType.TEXT_PDF:        TextPdfExtractor,
    DocumentType.OCR_PDF:         OcrPdfExtractor,
    DocumentType.MICROSOFT_FORMS: MicrosoftFormsExtractor,
    DocumentType.GOOGLE_FORMS:    GoogleFormsExtractor,
    DocumentType.AIQM_LMS:        AiqmLmsExtractor,
    DocumentType.UNKNOWN:         TextPdfExtractor,   # best-effort fallback
}

_validator = ValidatorLayer()


class ImportEngine:
    """
    Static-only orchestrator.  No instances needed.
    """

    @staticmethod
    def process(
        filepath: str,
        filename: str | None = None,
        mime_type: str | None = None,
        run_validation: bool = True,
    ) -> ExtractionResult:
        """
        Run the full pipeline on the uploaded file.

        Parameters
        ----------
        filepath      : absolute or relative path to the saved file
        filename      : original filename (used for extension hint when filepath
                        lacks an extension); if omitted, filepath is used
        mime_type     : optional MIME type from the HTTP upload
        run_validation: whether to run the ValidatorLayer (default True)

        Returns
        -------
        """
        start_time = time.perf_counter()
        probe_path = filepath if filename is None else _rewrite_extension(filepath, filename)

        # ------------------------------------------------------------------
        # Stage 1 — Detection
        # ------------------------------------------------------------------
        try:
            detection = detector.detect(probe_path, mime_type=mime_type)
        except Exception as exc:
            logger.exception("ImportEngine: detection failed")
            result = ExtractionResult()
            result.errors.append(f"Detection failed: {exc}")
            return result

        logger.info(
            "ImportEngine: detected %s (confidence=%.0f%%) for %s",
            detection.doc_type.value,
            detection.confidence * 100,
            filepath,
        )

        # ------------------------------------------------------------------
        # Stage 2 — Extractor selection
        # ------------------------------------------------------------------
        extractor_cls = _EXTRACTOR_MAP.get(detection.doc_type, TextPdfExtractor)
        extractor = extractor_cls()

        # ------------------------------------------------------------------
        # Stage 3 — Extraction
        # ------------------------------------------------------------------
        try:
            result = extractor.extract(filepath)
        except Exception as exc:
            logger.exception("ImportEngine: extraction failed")
            result = ExtractionResult()
            result.errors.append(f"Extraction error: {exc}")

        # Attach detection metadata to result
        result.doc_type = detection.doc_type
        result.detection_confidence = detection.confidence
        result.detection_signals = detection.signals
        result.extractor_name = extractor.extractor_name

        if detection.requires_ocr and detection.doc_type != DocumentType.OCR_PDF:
            ocr_msg = "This file may require OCR. Text extraction results could be incomplete."
            if not engine_config.ocr_enabled:
                ocr_msg += " (OCR is currently disabled — set ENABLE_OCR=true to enable it.)"
            result.warnings.append(ocr_msg)

        # ------------------------------------------------------------------
        # Stage 3.2 — Page Rendering for Vision (if OCR/Scanned)
        # ------------------------------------------------------------------
        if detection.requires_ocr or detection.doc_type == DocumentType.OCR_PDF:
            from app.services.import_engine.page_renderer import PageRenderer
            if PageRenderer.is_available():
                logger.info("ImportEngine: rasterising pages for Vision AI")
                images = PageRenderer.render_pages(filepath, limit=10)
                if images:
                    result.metadata["images"] = images

        # ------------------------------------------------------------------
        # Stage 3.5 — AI Enhancement (if enabled)
        # ------------------------------------------------------------------
        if engine_config.ai_enabled:
            from app.services.import_engine.ai_parsers import get_ai_parser
            ai_parser = get_ai_parser()
            
            full_text = result.metadata.get("full_text")
            images = result.metadata.get("images", [])
            
            if (full_text or images) and ai_parser.is_configured():
                logger.info(
                    "\n" + "="*50 + "\n"
                    "========== IMPORT START ==========\n"
                    f"Detected document   : {detection.doc_type.value}\n"
                    f"Extractor selected  : {extractor.extractor_name}\n"
                    f"AI Enabled          : {engine_config.ai_enabled}\n"
                    f"Provider            : {engine_config.ai_provider}\n"
                    f"API configured      : {ai_parser.is_configured()}\n"
                    f"Full text length    : {len(full_text) if full_text else 0}\n"
                    f"Image count         : {len(images)}\n"
                    "Sending to Gemini...\n"
                    + "="*50
                )
                from app.services.import_engine.ai_parsers.base_ai_parser import AIParseRequest
                
                ai_req = AIParseRequest(full_text=full_text or "", images=images)
                try:
                    ai_result = ai_parser.parse_document(ai_req)
                    
                    if ai_result.questions:
                        # Overwrite standard questions with AI questions
                        result.questions = ai_result.questions
                        result.extractor_name = f"{result.extractor_name} + {ai_result.extractor_name}"
                        
                        # Merge metadata from AI
                        for k, v in ai_result.metadata.items():
                            result.metadata[k] = v
                            
                        # Update doc_type if AI found a more specific one
                        if ai_result.doc_type != DocumentType.UNKNOWN:
                            result.doc_type = ai_result.doc_type
                            
                        result.warnings.extend(ai_result.warnings)
                        result.errors.extend(ai_result.errors)
                        
                        avg_conf = sum(q.confidence for q in result.questions) / len(result.questions)
                        logger.info(
                            "\n" + "="*50 + "\n"
                            "Gemini response received\n"
                            f"Questions returned  : {len(result.questions)}\n"
                            f"Average confidence  : {avg_conf*100:.1f}%\n"
                            "Validation completed\n"
                            "========== IMPORT END ==========\n"
                            + "="*50
                        )
                    else:
                        result.warnings.append("AI unavailable or returned no questions. Legacy extraction used.")
                        result.warnings.extend(ai_result.warnings)
                        logger.warning("AI parser returned 0 questions. Fallback preserved.")
                        
                except Exception as exc:
                    logger.exception("ImportEngine: AI parsing failed")
                    result.warnings.append(f"AI parsing failed: {exc}. Legacy extraction used.")
            elif not ai_parser.is_configured():
                result.warnings.append(f"AI is enabled but {ai_parser.provider_name} is not configured.")
                logger.warning("AI skipped: API Key not configured")
            else:
                result.warnings.append(f"AI is enabled but no text or images were extracted.")
                logger.warning("AI skipped: No text or images extracted")

        # ------------------------------------------------------------------
        # Stage 4 — Validation
        # ------------------------------------------------------------------
        if run_validation:
            try:
                _validator.validate(result)
            except Exception as exc:
                logger.exception("ImportEngine: validation failed")
                result.warnings.append(f"Validation error: {exc}")

        # ------------------------------------------------------------------
        # Stage 5 — Reporting
        # ------------------------------------------------------------------
        duration = time.perf_counter() - start_time
        
        avg_conf = 0.0
        if result.questions:
            avg_conf = sum(q.confidence for q in result.questions) / len(result.questions)
            
        total_warnings = sum(1 for q in result.questions for m in q.validation_messages if m.severity.name == "WARNING")
        
        logger.info(
            "\n" + "="*50 + "\n"
            " AI IMPORT REPORT\n"
            "="*50 + "\n"
            f" Document Type      : {result.doc_type.value}\n"
            f" Extractor Pipeline : {result.extractor_name}\n"
            f" Questions Detected : {result.question_count}\n"
            f" Valid Questions    : {len(result.valid_questions)}\n"
            f" Average Confidence : {avg_conf * 100:.1f}%\n"
            f" Validation Warnings: {total_warnings}\n"
            f" Pipeline Errors    : {len(result.errors)}\n"
            f" Processing Time    : {duration:.2f} seconds\n"
            + "="*50
        )

        return result

    @staticmethod
    def get_supported_extensions() -> list[str]:
        return [".xlsx", ".xls", ".docx", ".doc", ".pdf"]

    @staticmethod
    def get_config_summary() -> dict:
        """
        Return a safe (no secrets) summary of current engine configuration.
        Useful for admin diagnostic pages and the Detection Report.
        """
        return engine_config.as_dict()


def _rewrite_extension(filepath: str, filename: str) -> str:
    """
    Return a path whose extension matches the original filename.
    Used so the detector can read the correct extension even if the temp
    file was saved with a UUID name.
    """
    import os
    _, ext = os.path.splitext(filename)
    if ext:
        # Return a virtual path — we only need the extension for detection
        base, _ = os.path.splitext(filepath)
        return base + ext
    return filepath
