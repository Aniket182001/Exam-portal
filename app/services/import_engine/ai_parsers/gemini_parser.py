"""
Gemini AI Parser — Skeleton
============================
Implements BaseAIParser for Google's Gemini API.

Status: SKELETON
  - Configuration, request builder, response parser, and JSON schema are
    all defined and ready.
  - The actual API call is stubbed with a NotImplementedError comment.
  - Enable by setting GEMINI_API_KEY and ENABLE_AI_IMPORT=true.
  - No API call is made until a future phase activates this provider.

Configuration (environment variables):
    GEMINI_API_KEY   = your-api-key
    GEMINI_MODEL     = gemini-1.5-flash   (default)
    GEMINI_TIMEOUT   = 30                  (seconds)
    ENABLE_AI_IMPORT = true
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.import_engine.ai_parsers.base_ai_parser import (
    AIParseRequest,
    AIParseResponse,
    BaseAIParser,
)
from app.services.import_engine.config import engine_config
from app.services.import_engine.models import (
    DocumentType,
    ExtractedQuestion,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Schema — defines the structured response Gemini must return
# ---------------------------------------------------------------------------
#
# We ask Gemini to return an array of question objects so we can parse them
# deterministically without free-form text processing.
#
GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "metadata": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": ["Microsoft Forms", "Google Forms", "AIQM LMS", "Moodle", "Generic PDF", "Unknown"],
                    "description": "The detected layout/source platform of the document."
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning for the detected document type."
                }
            },
            "required": ["document_type", "reasoning"]
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question_text", "options", "confidence", "reason"],
                "properties": {
                    "question_text": {
                        "type": "string",
                        "description": "Full text of the question. Preserve wording and numbering exactly."
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "All answer options in their original order."
                    },
                    "correct_option_index": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "0-based index of the correct answer."
                    },
                    "marks": {
                        "type": "number",
                        "description": "Marks awarded for this question."
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Descriptions of any embedded images detected in the question."
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Parser confidence in this extraction (e.g., 0.98)."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reasoning for confidence and extraction (e.g., 'Selected checkbox detected.')."
                    },
                    "source_page": {
                        "type": "integer",
                        "description": "Page number this question was found on"
                    }
                }
            }
        }
    },
    "required": ["metadata", "questions"]
}


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

_DOCUMENT_PROMPT = """\
You are an expert exam question extractor. 

Analyse the following document text and extract all multiple-choice questions.

RULES:
- Preserve question wording exactly.
- Preserve numbering.
- Preserve option order.
- Detect correct answers (if marked, e.g. bold, checkmark, highlight).
- Detect marks (e.g. '[1 mark]').
- Detect embedded images (note their presence).
- Identify document type from layout/signatures.
- Never invent missing content.
- Return confidence per question and reason.
- Return ONLY a valid JSON object matching the schema — no prose.
- If a question has no clear options, skip it.

DOCUMENT TEXT:
{text}
"""

_PAGE_PROMPT = """\
You are an expert exam question extractor. 

Analyse the following single page of text and extract any multiple-choice questions.

RULES:
- Preserve question wording exactly.
- Preserve numbering.
- Preserve option order.
- Detect correct answers.
- Detect marks.
- Detect embedded images.
- Identify document type.
- Never invent missing content.
- Return confidence per question and reason.
- A question may continue from a previous page — include it if you can see it.
- Return ONLY a valid JSON object matching the schema.

PAGE {page_number} TEXT:
{text}
"""

_QUESTION_PROMPT = """\
You are an expert exam question extractor.

Parse the following text block as a single MCQ question and return ONE object (as the only item in the questions array).

RULES:
- Preserve question wording exactly.
- Preserve numbering.
- Preserve option order.
- Detect correct answers.
- Detect marks.
- Detect embedded images.
- Identify document type if possible, otherwise Unknown.
- Never invent missing content.
- Return confidence and reason.
- Return ONLY a valid JSON object matching the schema.

QUESTION BLOCK:
{block}
"""


# ---------------------------------------------------------------------------
# GeminiParser
# ---------------------------------------------------------------------------

class GeminiParser(BaseAIParser):
    """
    Gemini AI parser skeleton.

    When ENABLE_AI_IMPORT=true and GEMINI_API_KEY is set, this class will
    be used by the engine to parse documents using Gemini's language models.

    The three parse methods build prompts and will eventually call
    self._call_api(), which is the only method that needs to be activated
    in the next phase.
    """

    provider_name = "gemini"

    def _validate_config(self) -> None:
        """Warn (don't raise) if the API key is missing."""
        if not engine_config.gemini_api_key:
            logger.warning(
                "GeminiParser: GEMINI_API_KEY is not set. "
                "AI parsing will not function until it is configured."
            )

    def is_configured(self) -> bool:
        return bool(engine_config.gemini_api_key)

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def parse_document(self, request: AIParseRequest) -> ExtractionResult:
        """Parse an entire document in one API call."""
        if not self.is_configured():
            return self._unconfigured_result("parse_document")

        prompt = _DOCUMENT_PROMPT.format(text=request.full_text[:50_000])
        raw_response = self._call_api(prompt=prompt, request=request)
        return self._normalise_response(raw_response)

    def parse_page(self, request: AIParseRequest) -> ExtractionResult:
        """Parse a single page."""
        if not self.is_configured():
            return self._unconfigured_result("parse_page")

        prompt = _PAGE_PROMPT.format(
            page_number=request.page_number or "?",
            text=request.page_text[:10_000],
        )
        raw_response = self._call_api(prompt=prompt, request=request)
        return self._normalise_response(raw_response)

    def parse_question(self, request: AIParseRequest) -> ExtractionResult:
        """Parse a single question block."""
        if not self.is_configured():
            return self._unconfigured_result("parse_question")

        prompt = _QUESTION_PROMPT.format(block=request.question_block[:2_000])
        raw_response = self._call_api(prompt=prompt, request=request)
        return self._normalise_response(raw_response)

    # ------------------------------------------------------------------
    # Request builder
    # ------------------------------------------------------------------

    def _build_request_body(
        self,
        prompt: str,
        include_image: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Build the Gemini REST API request body.
        Uses structured JSON output via response_schema.
        """
        parts: list[dict] = [{"text": prompt}]

        # Attach an image part if provided (for Vision models)
        if include_image:
            import base64
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(include_image).decode("utf-8"),
                }
            })

        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,       # low temp for deterministic extraction
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_RESPONSE_SCHEMA,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
            ],
        }
        return body

    # ------------------------------------------------------------------
    # API call (STUB — to be activated in Phase 3)
    # ------------------------------------------------------------------

    def _call_api(
        self,
        prompt: str,
        request: AIParseRequest | None = None,
    ) -> AIParseResponse:
        """
        Make the actual call to the Gemini REST API.
        """
        import urllib.request
        import json

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{engine_config.gemini_model}:generateContent"
            f"?key={engine_config.gemini_api_key}"
        )
        
        include_image = request.page_image if request else None
        body = self._build_request_body(prompt, include_image=include_image)
        data = json.dumps(body).encode("utf-8")
        
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=engine_config.gemini_timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = exc.read().decode("utf-8")
            logger.error("Gemini API HTTPError: %s - %s", exc.code, err_msg)
            return AIParseResponse(
                error=f"API call failed: HTTP {exc.code} {err_msg}",
                provider=self.provider_name,
                model=engine_config.gemini_model
            )
        except Exception as exc:
            logger.exception("Gemini API call failed")
            return AIParseResponse(
                error=f"API call failed: {exc}",
                provider=self.provider_name,
                model=engine_config.gemini_model
            )

        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return AIParseResponse(
                raw_output=text,
                provider=self.provider_name,
                model=engine_config.gemini_model
            )
        except (KeyError, IndexError) as exc:
            logger.error("Unexpected Gemini API response format: %s", payload)
            return AIParseResponse(
                error=f"Unexpected API response format: {exc}",
                provider=self.provider_name,
                model=engine_config.gemini_model
            )

    # ------------------------------------------------------------------
    # Response parser / normaliser
    # ------------------------------------------------------------------

    def _normalise_response(self, response: AIParseResponse) -> ExtractionResult:
        """
        Convert an AIParseResponse into a standardised ExtractionResult.
        Handles both array and single-object JSON outputs.
        """
        result = self._make_empty_result()
        result.extractor_name = f"ai:{self.provider_name}"

        if response.error:
            result.warnings.append(f"AI parser: {response.error}")

        raw = (response.raw_output or "").strip()
        if not raw:
            return result

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            result.warnings.append(f"AI response JSON parse error: {exc}")
            logger.warning("GeminiParser: JSON decode failed — %s", exc)
            return result

        if not isinstance(payload, dict):
            result.warnings.append("AI response was not a JSON object.")
            return result

        # Parse layout recognition metadata
        metadata = payload.get("metadata", {})
        doc_type_str = metadata.get("document_type", "Unknown")
        reasoning = metadata.get("reasoning", "")
        
        # Try to map doc_type_str to DocumentType Enum
        try:
            doc_type_key = doc_type_str.upper().replace(" ", "_")
            result.doc_type = DocumentType[doc_type_key]
        except KeyError:
            result.doc_type = DocumentType.UNKNOWN
            
        result.metadata["ai_document_type"] = doc_type_str
        result.metadata["ai_reasoning"] = reasoning

        questions_list = payload.get("questions", [])
        if not isinstance(questions_list, list):
            result.warnings.append("AI response 'questions' was not a list.")
            return result

        for item in questions_list:
            q = self._parse_question_item(item)
            if q:
                result.questions.append(q)

        logger.info(
            "GeminiParser: normalised %d questions from AI response",
            len(result.questions),
        )
        return result

    @staticmethod
    def _parse_question_item(item: dict[str, Any]) -> ExtractedQuestion | None:
        """Convert one AI JSON object into an ExtractedQuestion."""
        if not isinstance(item, dict):
            return None

        q_text = str(item.get("question_text", "")).strip()
        if not q_text:
            return None

        options = [str(o).strip() for o in item.get("options", []) if str(o).strip()]
        if len(options) < 2:
            return None

        correct_idx = item.get("correct_option_index")
        if correct_idx is not None:
            try:
                correct_idx = int(correct_idx)
                if correct_idx >= len(options):
                    correct_idx = None
            except (TypeError, ValueError):
                correct_idx = None

        marks = 1.0
        try:
            marks = float(item.get("marks", 1.0))
        except (TypeError, ValueError):
            pass

        confidence = 1.0
        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            pass

        reason = item.get("reason", "")
        source_page = item.get("source_page")
        images = item.get("images", [])

        return ExtractedQuestion(
            question_text=q_text,
            options=options,
            correct_option_index=correct_idx,
            marks=marks,
            confidence=confidence,
            source_page=source_page,
            metadata={
                "ai_provider": "gemini",
                "ai_reason": reason,
                "ai_images": images
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _unconfigured_result(self, method: str) -> ExtractionResult:
        result = self._make_empty_result()
        result.warnings.append(
            f"GeminiParser.{method}: GEMINI_API_KEY is not set. "
            "Configure it to enable AI-assisted parsing."
        )
        return result
