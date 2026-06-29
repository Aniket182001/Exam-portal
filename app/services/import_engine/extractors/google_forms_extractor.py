"""
Google Forms PDF Extractor  (stub)
====================================
Handles PDFs exported from Google Forms.

Status: ARCHITECTURE STUB
  - Detection routes Google Forms PDFs here correctly.
  - Falls back to TextPdfExtractor heuristics as a best-effort fallback.
  - Full implementation (answer key parsing, section handling) deferred.
"""

from __future__ import annotations

import logging

from app.services.import_engine.extractors.base import BaseExtractor
from app.services.import_engine.extractors.text_pdf_extractor import TextPdfExtractor
from app.services.import_engine.models import (
    DocumentType,
    ExtractionResult,
)

logger = logging.getLogger(__name__)

_PARTIAL_MSG = (
    "Google Forms extractor is partially implemented. "
    "Results were produced using generic text extraction and may be inaccurate. "
    "Review all questions carefully before confirming import."
)


class GoogleFormsExtractor(BaseExtractor):
    extractor_name = "google_forms"

    def extract(self, filepath: str) -> ExtractionResult:
        result = self._make_result(DocumentType.GOOGLE_FORMS)
        result.extractor_name = self.extractor_name
        result.warnings.append(_PARTIAL_MSG)

        fallback_result = TextPdfExtractor().extract(filepath)
        result.questions = fallback_result.questions
        result.total_pages = fallback_result.total_pages
        result.errors.extend(fallback_result.errors)
        result.warnings.extend(fallback_result.warnings)
        result.metadata.update(fallback_result.metadata)

        logger.info(
            "GoogleFormsExtractor: extracted %d questions (fallback mode)",
            len(result.questions),
        )
        return result
