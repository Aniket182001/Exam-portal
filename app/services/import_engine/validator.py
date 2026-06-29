"""
Validation Layer
================
Runs after extraction and annotates each ExtractedQuestion with
ValidationMessages covering:

  - MISSING_OPTIONS       question has fewer than 2 options
  - MISSING_ANSWER        correct answer could not be resolved
  - LOW_CONFIDENCE        extractor confidence below threshold
  - DUPLICATE_NUMBER      same question number appears twice
  - EMPTY_OPTION          one or more options are blank
  - SHORT_QUESTION        question text is suspiciously short
  - TOO_MANY_OPTIONS      more than 6 options
  - SUSPICIOUS_FORMAT     question text looks like a formatting artefact

All existing questions are mutated in-place; the same list is returned.
The ExtractionResult.errors list is also augmented with a summary line.
"""

from __future__ import annotations

import re
from collections import Counter

from app.services.import_engine.models import (
    ExtractedQuestion,
    ExtractionResult,
    ValidationMessage,
    ValidationSeverity,
)

# ------------------------------------------------------------------
# Thresholds
# ------------------------------------------------------------------
CONFIDENCE_WARNING_THRESHOLD = 0.70
MIN_QUESTION_LENGTH = 8       # chars
MAX_OPTIONS = 6

# Patterns that suggest PDF extraction artefacts
_ARTEFACT_PATTERNS = [
    re.compile(r"^\d+\s*\.\s*$"),          # lone number like "3."
    re.compile(r"^[^a-zA-Z]{0,3}$"),        # non-alphanumeric junk
    re.compile(r"^\s*page\s+\d+\s*$", re.I),  # page headers
]


class ValidatorLayer:
    """
    Stateless validator — call validate(result) to annotate questions.
    """

    def validate(self, result: ExtractionResult) -> ExtractionResult:
        """
        Annotate every question in result with validation messages.
        Returns the same result object (mutated).
        """
        number_counts: Counter[str] = Counter()

        # First pass: detect duplicate numbering
        for q in result.questions:
            key = q.question_text[:40].strip().lower()
            number_counts[key] += 1

        # Second pass: per-question validation
        for q in result.questions:
            self._validate_question(q, number_counts)

        # Summary warning if many failed
        error_count = sum(
            1 for q in result.questions
            if any(m.severity == ValidationSeverity.ERROR for m in q.validation_messages)
        )
        if error_count:
            result.warnings.append(
                f"{error_count} of {len(result.questions)} questions have validation errors "
                "and will be excluded from the preview unless corrected."
            )

        return result

    # ------------------------------------------------------------------

    def _validate_question(
        self, q: ExtractedQuestion, number_counts: Counter
    ) -> None:
        msgs = q.validation_messages  # mutate in-place

        # Missing options
        if len(q.options) < 2:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.ERROR,
                code="MISSING_OPTIONS",
                message=f"Question has only {len(q.options)} option(s); at least 2 required.",
            ))

        # Too many options
        if len(q.options) > MAX_OPTIONS:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="TOO_MANY_OPTIONS",
                message=f"Question has {len(q.options)} options; maximum supported is {MAX_OPTIONS}. Extra options will be ignored.",
            ))

        # Missing answer
        if q.correct_option_index is None:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="MISSING_ANSWER",
                message="Correct answer could not be determined. It will default to Option A.",
            ))

        # Empty options
        empty_opts = [i for i, o in enumerate(q.options) if not o.strip()]
        if empty_opts:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="EMPTY_OPTION",
                message=f"Option(s) at position(s) {[i+1 for i in empty_opts]} are blank.",
            ))

        # Low confidence
        if q.confidence < CONFIDENCE_WARNING_THRESHOLD:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="LOW_CONFIDENCE",
                message=f"Extraction confidence is {q.confidence:.0%}. Review this question carefully.",
            ))

        # Short question
        if len(q.question_text.strip()) < MIN_QUESTION_LENGTH:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="SHORT_QUESTION",
                message="Question text is very short and may be a formatting artefact.",
            ))

        # Suspicious formatting artefact
        for pat in _ARTEFACT_PATTERNS:
            if pat.match(q.question_text.strip()):
                msgs.append(ValidationMessage(
                    severity=ValidationSeverity.ERROR,
                    code="SUSPICIOUS_FORMAT",
                    message="Question text looks like a formatting artefact and should be reviewed.",
                ))
                break

        # Duplicate content
        key = q.question_text[:40].strip().lower()
        if number_counts[key] > 1:
            msgs.append(ValidationMessage(
                severity=ValidationSeverity.WARNING,
                code="DUPLICATE_QUESTION",
                message="A question with identical or very similar text appears more than once.",
            ))
