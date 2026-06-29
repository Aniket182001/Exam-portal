"""
Text PDF Extractor
==================
Parses selectable-text PDFs using pypdf.

Uses the same paragraph-level parsing strategy as the legacy PdfParser
but returns typed ExtractedQuestion objects with per-question confidence.
"""

from __future__ import annotations

import logging

from app.services.import_engine.extractors.base import BaseExtractor
from app.services.import_engine.models import (
    DocumentType,
    ExtractedQuestion,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


class TextPdfExtractor(BaseExtractor):
    extractor_name = "text_pdf"

    def extract(self, filepath: str) -> ExtractionResult:
        result = self._make_result(DocumentType.TEXT_PDF)
        result.extractor_name = self.extractor_name

        try:
            import pypdf
        except ImportError:
            result.errors.append("pypdf is not installed.")
            return result

        try:
            full_text = ""
            with open(filepath, "rb") as fh:
                reader = pypdf.PdfReader(fh)
                result.total_pages = len(reader.pages)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        full_text += extracted + "\n"
            result.metadata["full_text"] = full_text
            result.questions = self._parse_text(full_text)

        except Exception as exc:
            logger.exception("TextPdfExtractor failed: %s", exc)
            result.errors.append(f"Extraction error: {exc}")

        return result

    # ------------------------------------------------------------------

    def _parse_text(self, text: str) -> list[ExtractedQuestion]:
        questions: list[ExtractedQuestion] = []
        current: dict | None = None

        def finalise():
            if current and len(current["options"]) >= 2:
                q = ExtractedQuestion(
                    question_text=current["question"].strip(),
                    options=current["options"][:6],
                    marks=current["marks"],
                    raw_text=current["raw"],
                )
                q.correct_option_index = self._resolve_answer_index(
                    current.get("correct_raw", ""), q.options
                )
                q.confidence = self._question_confidence(q)
                questions.append(q)

        for line in self._non_empty_lines(text):
            ll = line.lower()

            if ll.startswith("question"):
                finalise()
                q_text = line.split(":", 1)[1].strip() if ":" in line else line
                current = {
                    "question": q_text,
                    "options": [],
                    "correct_raw": None,
                    "marks": 1.0,
                    "raw": line,
                }

            elif current is not None:
                if len(line) >= 2 and line[0].upper() in "ABCDEF" and line[1] in ".) ":
                    current["options"].append(line[2:].strip())
                elif ll.startswith("answer"):
                    current["correct_raw"] = line.split(":", 1)[1].strip() if ":" in line else ""
                elif ll.startswith("marks"):
                    current["marks"] = self._parse_marks(
                        line.split(":", 1)[1].strip() if ":" in line else None
                    )
                elif not current["options"] and not current.get("correct_raw"):
                    current["question"] += "\n" + line

        finalise()
        return questions
