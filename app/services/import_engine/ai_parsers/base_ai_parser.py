"""
AI Parser Interface
===================
Abstract base for all AI-powered document parsers.

Provider implementations (GeminiParser, OpenAIParser, etc.) must inherit
from BaseAIParser and implement its abstract methods.  The ImportEngine
talks only to this interface — it never imports provider code directly.

Why keep this separate from BaseExtractor?
  - AI parsers receive different inputs: raw text + images, not file paths.
  - AI parsers can parse at document, page, or individual question granularity.
  - An AI parser may be invoked after OCR, after text extraction, or both.
  - Keeping the interface clean allows swapping providers with zero engine changes.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.services.import_engine.models import ExtractionResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AI-specific input/output types
# ---------------------------------------------------------------------------

@dataclass
class AIParseRequest:
    """
    Input payload for any AI parser.
    Fill only the fields relevant to the granularity of the call.
    """
    # Document-level inputs
    full_text: str = ""                     # full extracted/OCR text
    page_texts: list[str] = field(default_factory=list)  # per-page texts
    images: list[bytes] = field(default_factory=list)    # raw page image bytes

    # Page-level inputs (used by parse_page)
    page_number: int | None = None
    page_text: str = ""
    page_image: bytes | None = None

    # Question-level inputs (used by parse_question)
    question_block: str = ""                # raw text block for one question

    # Contextual hints for the AI
    hints: dict[str, Any] = field(default_factory=dict)
    """
    Example hints:
        {"expected_questions": 20, "marks_per_question": 1, "language": "en"}
    """


@dataclass
class AIParseResponse:
    """
    Raw response from an AI provider before standardisation.
    Provider implementations fill this; the base class normalises it into
    an ExtractionResult.
    """
    raw_output: str = ""          # raw text / JSON string from the AI
    parsed_json: Any = None       # parsed JSON if the provider returns JSON
    provider: str = ""            # e.g. "gemini", "openai"
    model: str = ""               # e.g. "gemini-1.5-flash"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract Base
# ---------------------------------------------------------------------------

class BaseAIParser(ABC):
    """
    Abstract AI parser.  Every concrete provider must implement the three
    abstract methods below.  Optional helper methods can be overridden.

    Lifecycle
    ---------
    1. Caller invokes parse_document() for full-document AI parsing, or
       parse_page() for page-by-page, or parse_question() for a single block.
    2. The provider builds a prompt, calls the API, and returns AIParseResponse.
    3. _normalise_response() converts the provider response into ExtractionResult.
    """

    #: Human-readable name for this provider, e.g. "gemini"
    provider_name: str = "base"

    def __init__(self) -> None:
        self._validate_config()

    # ------------------------------------------------------------------
    # Abstract methods — must be implemented by every provider
    # ------------------------------------------------------------------

    @abstractmethod
    def parse_document(self, request: AIParseRequest) -> ExtractionResult:
        """
        Parse the entire document at once.
        Best for short documents where the full text fits in the context window.
        """

    @abstractmethod
    def parse_page(self, request: AIParseRequest) -> ExtractionResult:
        """
        Parse a single page.
        Used when documents are too long for a single API call.
        Results from all pages are merged by the caller.
        """

    @abstractmethod
    def parse_question(self, request: AIParseRequest) -> ExtractionResult:
        """
        Parse a single question block (already extracted text).
        Used for re-parsing ambiguous questions extracted by a text extractor.
        """

    # ------------------------------------------------------------------
    # Optional override: provider-specific configuration validation
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        """
        Called in __init__. Raise ValueError if the provider is misconfigured
        (e.g. missing API key).  Base implementation does nothing.
        """

    # ------------------------------------------------------------------
    # Shared helpers — providers may call these
    # ------------------------------------------------------------------

    @staticmethod
    def _make_empty_result() -> ExtractionResult:
        from app.services.import_engine.models import DocumentType
        result = ExtractionResult()
        result.doc_type = DocumentType.UNKNOWN
        return result

    @staticmethod
    def _merge_results(results: list[ExtractionResult]) -> ExtractionResult:
        """Merge multiple page-level results into one document-level result."""
        from app.services.import_engine.models import DocumentType
        merged = ExtractionResult()
        merged.doc_type = DocumentType.UNKNOWN
        for r in results:
            merged.questions.extend(r.questions)
            merged.warnings.extend(r.warnings)
            merged.errors.extend(r.errors)
        return merged

    def is_configured(self) -> bool:
        """
        Override in subclasses to check whether all required config
        (API keys, endpoints, etc.) is present.
        """
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name!r}>"
