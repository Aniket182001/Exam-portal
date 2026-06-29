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
        ExtractionResult  — always returned, never raises
        """
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
        # Stage 3.5 — AI Enhancement (if enabled)
        # ------------------------------------------------------------------
        if engine_config.ai_enabled:
            from app.services.import_engine.ai_parsers import get_ai_parser
            ai_parser = get_ai_parser()
            
            # Text must have been extracted by the standard extractor
            full_text = result.metadata.get("full_text")
            
            if full_text and ai_parser.is_configured():
                logger.info("ImportEngine: dispatching to AI parser (%s)", ai_parser.provider_name)
                from app.services.import_engine.ai_parsers.base_ai_parser import AIParseRequest
                
                ai_req = AIParseRequest(full_text=full_text)
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
                        
                        logger.info("ImportEngine: AI parsed %d questions", len(result.questions))
                    else:
                        result.warnings.append("AI parser returned no questions; falling back to standard extraction.")
                        result.warnings.extend(ai_result.warnings)
                        
                except Exception as exc:
                    logger.exception("ImportEngine: AI parsing failed")
                    result.warnings.append(f"AI parsing failed: {exc}. Falling back to standard extraction.")
            elif not ai_parser.is_configured():
                result.warnings.append(f"AI is enabled but {ai_parser.provider_name} is not configured.")
            elif not full_text:
                result.warnings.append(f"AI is enabled but extractor {extractor.extractor_name} did not provide raw text.")

        # ------------------------------------------------------------------
        # Stage 4 — Validation
        # ------------------------------------------------------------------
        if run_validation:
            try:
                _validator.validate(result)
            except Exception as exc:
                logger.exception("ImportEngine: validation failed")
                result.warnings.append(f"Validation error: {exc}")

        logger.info(
            "ImportEngine: finished — %d questions extracted, %d valid, %d errors",
            result.question_count,
            len(result.valid_questions),
            len(result.errors),
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
