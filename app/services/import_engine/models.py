"""
Import Engine Data Models
=========================
Standardised data structures shared across all layers of the pipeline:
  Detector → Extractor → Validator → Engine

Nothing here has side effects; it is safe to import from anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Document Classification
# ---------------------------------------------------------------------------

class DocumentType(Enum):
    """
    Every supported document category.
    The detector returns exactly one of these values.
    """
    EXCEL             = "excel"
    WORD              = "word"
    TEXT_PDF          = "text_pdf"
    OCR_PDF           = "ocr_pdf"          # scanned / image-only
    MICROSOFT_FORMS   = "microsoft_forms"
    GOOGLE_FORMS      = "google_forms"
    AIQM_LMS          = "aiqm_lms"
    UNKNOWN           = "unknown"


# ---------------------------------------------------------------------------
# Validation Messages
# ---------------------------------------------------------------------------

class ValidationSeverity(Enum):
    INFO    = "info"
    WARNING = "warning"
    ERROR   = "error"


@dataclass
class ValidationMessage:
    """A single validation note attached to an extracted question."""
    severity: ValidationSeverity
    code: str           # machine-readable key, e.g. "MISSING_ANSWER"
    message: str        # human-readable description


# ---------------------------------------------------------------------------
# Per-Question Result
# ---------------------------------------------------------------------------

@dataclass
class ExtractedQuestion:
    """
    Standardised per-question payload produced by every extractor.
    Every field that is not available is left at its default value so
    the downstream validator can flag it without crashing.
    """
    # A unique identifier for tracking edits in the UI
    id: str = field(default_factory=lambda: __import__('uuid').uuid4().hex)

    # Core content
    question_text: str = ""
    options: list[str] = field(default_factory=list)

    # Answer resolution
    correct_option_index: int | None = None   # 0-based; None = not detected
    correct_option_text: str | None = None    # raw text if index not determined

    # Scoring
    marks: float = 1.0

    # Rich content (future-ready)
    images: list[bytes] = field(default_factory=list)   # raw PNG/JPEG bytes

    # Provenance
    source_page: int | None = None          # page number in PDF / sheet index
    source_row: int | None = None           # row index in Excel
    raw_text: str = ""                      # verbatim extracted block

    # Extraction quality
    confidence: float = 1.0                 # 0.0–1.0

    # Validation output (populated by ValidatorLayer)
    validation_messages: list[ValidationMessage] = field(default_factory=list)

    # Arbitrary extractor-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers

    @property
    def is_valid(self) -> bool:
        """True if no ERROR-level validation messages exist."""
        return not any(
            m.severity == ValidationSeverity.ERROR
            for m in self.validation_messages
        )

    @property
    def has_warnings(self) -> bool:
        return any(
            m.severity == ValidationSeverity.WARNING
            for m in self.validation_messages
        )

    def to_legacy_dict(self) -> dict:
        """
        Convert to the dict format expected by the existing import preview
        and confirm_import routes so that the legacy workflow keeps working.
        """
        return {
            "question": self.question_text,
            "options": self.options,
            "correct_option_index": self.correct_option_index or 0,
            "marks": self.marks,
        }

    def to_dict(self) -> dict:
        """
        Export full rich data for the AI Review Workspace.
        Retains legacy fields for backward compatibility.
        """
        legacy = self.to_legacy_dict()
        
        # Add rich properties
        legacy.update({
            "id": self.id,
            "confidence": self.confidence,
            "reason": self.metadata.get("ai_reason", ""),
            "raw_text": self.raw_text,
            "source_page": self.source_page,
            "is_valid": self.is_valid,
            "has_warnings": self.has_warnings,
            "validation_messages": [
                {"message": m.message, "severity": m.severity.value} 
                for m in self.validation_messages
            ],
            "metadata": self.metadata
        })
        return legacy


# ---------------------------------------------------------------------------
# Top-level Extraction Result
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    """Output produced by the Detector layer."""
    doc_type: DocumentType
    confidence: float               # 0.0–1.0 how confident the detector is
    requires_ocr: bool = False
    signals: dict[str, Any] = field(default_factory=dict)  # debug info


@dataclass
class ExtractionResult:
    """
    Top-level object returned by ImportEngine.process().
    Consumers can iterate result.questions directly and also inspect
    metadata about how the file was classified.
    """
    questions: list[ExtractedQuestion] = field(default_factory=list)

    # Classification metadata
    doc_type: DocumentType = DocumentType.UNKNOWN
    detection_confidence: float = 0.0
    detection_signals: dict[str, Any] = field(default_factory=dict)

    # Pipeline metadata
    extractor_name: str = ""
    total_pages: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Extractor-specific debug metadata (not exposed to the UI by default)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers

    @property
    def valid_questions(self) -> list[ExtractedQuestion]:
        return [q for q in self.questions if q.is_valid]

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def to_legacy_list(self) -> list[dict]:
        """
        Returns the list-of-dicts format that the existing import_parsers
        pipeline and preview UI expect, ensuring 100 % backward compatibility.
        """
        return [q.to_legacy_dict() for q in self.valid_questions]

    def to_dict_list(self) -> list[dict]:
        """
        Returns all questions (valid and invalid) as dicts, containing
        rich metadata for the review workspace.
        """
        return [q.to_dict() for q in self.questions]
