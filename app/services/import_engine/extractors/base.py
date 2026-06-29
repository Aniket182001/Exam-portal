"""
Base Extractor Interface
========================
All concrete extractors must inherit from BaseExtractor and implement
the extract() method.  The base class provides shared helper utilities
so individual extractors stay focused on format-specific parsing logic.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Iterator

from app.services.import_engine.models import (
    DocumentType,
    ExtractedQuestion,
    ExtractionResult,
    ValidationMessage,
    ValidationSeverity,
)

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base for all format extractors."""

    # Subclasses must declare this so the engine can log which extractor ran.
    extractor_name: str = "base"

    # ------------------------------------------------------------------ API

    @abstractmethod
    def extract(self, filepath: str) -> ExtractionResult:
        """
        Parse the file at `filepath` and return an ExtractionResult.
        Must never raise — wrap errors in result.errors instead.
        """

    # ------------------------------------------------------------------ helpers shared by subclasses

    @staticmethod
    def _make_result(doc_type: DocumentType) -> ExtractionResult:
        result = ExtractionResult()
        result.doc_type = doc_type
        return result

    @staticmethod
    def _blank_question() -> ExtractedQuestion:
        return ExtractedQuestion()

    # ---- Answer resolution ----

    @staticmethod
    def _resolve_answer_index(
        answer_raw: str,
        options: list[str],
    ) -> int | None:
        """
        Turn a raw answer hint (e.g. 'A', 'b', 'Option B', or full text)
        into a 0-based index.  Returns None if unresolvable.
        """
        if not answer_raw:
            return None

        a = answer_raw.strip().lower()

        # Single letter: A → 0, B → 1 …
        if len(a) == 1 and a in "abcdef":
            idx = ord(a) - ord("a")
            return idx if idx < len(options) else None

        # "option a" / "option 1"
        m = re.match(r"option\s+([a-f1-9])", a)
        if m:
            char = m.group(1)
            if char.isdigit():
                idx = int(char) - 1
            else:
                idx = ord(char) - ord("a")
            return idx if idx < len(options) else None

        # Exact text match
        for i, opt in enumerate(options):
            if opt.strip().lower() == a:
                return i

        return None

    # ---- Marks parsing ----

    @staticmethod
    def _parse_marks(raw: str | None, default: float = 1.0) -> float:
        if raw is None:
            return default
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            return default

    # ---- Confidence helpers ----

    @staticmethod
    def _question_confidence(q: ExtractedQuestion) -> float:
        """
        Heuristic confidence for a single extracted question.
        Fully-formed question = 1.0; degrades with missing parts.
        """
        score = 1.0
        if not q.question_text.strip():
            score -= 0.4
        if len(q.options) < 2:
            score -= 0.3
        if q.correct_option_index is None:
            score -= 0.2
        return max(0.0, round(score, 2))

    # ---- Line iterators used by text-based extractors ----

    @staticmethod
    def _non_empty_lines(text: str) -> Iterator[str]:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                yield stripped
