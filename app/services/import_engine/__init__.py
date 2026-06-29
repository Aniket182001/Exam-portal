"""
AIQM Import Engine
==================
Modular multi-format exam import architecture.

Usage:
    from app.services.import_engine import ImportEngine

    result = ImportEngine.process(filepath, filename, mime_type=None)
    # result.questions  -> list[ExtractedQuestion]
    # result.doc_type   -> DocumentType
    # result.confidence -> float
"""

from app.services.import_engine.engine import ImportEngine
from app.services.import_engine.models import (
    DocumentType,
    ExtractedQuestion,
    ExtractionResult,
    ValidationMessage,
    ValidationSeverity,
)

__all__ = [
    "ImportEngine",
    "DocumentType",
    "ExtractedQuestion",
    "ExtractionResult",
    "ValidationMessage",
    "ValidationSeverity",
]
