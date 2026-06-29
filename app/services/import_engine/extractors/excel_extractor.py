"""
Excel Extractor
===============
Wraps the existing ExcelParser logic as a modular extractor that returns
an ExtractionResult with fully-typed ExtractedQuestion objects.

Supports up to 6 options (columns A-F).
Expected header row: Question | Opt A | Opt B | Opt C | Opt D | Opt E | Opt F | Correct | Marks
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


class ExcelExtractor(BaseExtractor):
    extractor_name = "excel"

    def extract(self, filepath: str) -> ExtractionResult:
        result = self._make_result(DocumentType.EXCEL)
        result.extractor_name = self.extractor_name

        try:
            import openpyxl
        except ImportError:
            result.errors.append("openpyxl is not installed.")
            return result

        try:
            wb = openpyxl.load_workbook(filepath, data_only=True)
            sheet = wb.active

            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not row:
                    continue

                row_data = list(row)
                while len(row_data) < 9:
                    row_data.append(None)

                q_text   = row_data[0]
                raw_opts = row_data[1:7]   # columns B-G → up to 6 options
                correct  = row_data[7]
                marks_raw = row_data[8]

                if not q_text or not str(q_text).strip():
                    continue

                options = [str(o).strip() for o in raw_opts if o is not None and str(o).strip()]

                q = ExtractedQuestion(
                    question_text=str(q_text).strip(),
                    options=options,
                    marks=self._parse_marks(marks_raw),
                    source_row=row_idx,
                    raw_text=str(row_data),
                )
                q.correct_option_index = self._resolve_answer_index(
                    str(correct) if correct is not None else "", options
                )
                q.confidence = self._question_confidence(q)

                result.questions.append(q)

        except Exception as exc:
            logger.exception("ExcelExtractor failed: %s", exc)
            result.errors.append(f"Extraction error: {exc}")

        return result
