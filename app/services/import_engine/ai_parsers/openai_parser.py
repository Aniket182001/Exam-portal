"""
OpenAI Parser — Skeleton
=========================
Reserved slot for an OpenAI (GPT-4o / GPT-4-vision) implementation.

Status: SKELETON PLACEHOLDER
  - Inherits BaseAIParser and declares provider_name.
  - All methods raise NotImplementedError to make future gaps obvious.
  - Activate in a future phase by implementing parse_document/page/question
    and wiring OPENAI_API_KEY + AI_PROVIDER=openai.
"""

from __future__ import annotations

from app.services.import_engine.ai_parsers.base_ai_parser import (
    AIParseRequest,
    BaseAIParser,
)
from app.services.import_engine.models import ExtractionResult


class OpenAIParser(BaseAIParser):
    provider_name = "openai"

    def _validate_config(self) -> None:
        from app.services.import_engine.config import engine_config
        if not engine_config.openai_api_key:
            import logging
            logging.getLogger(__name__).warning(
                "OpenAIParser: OPENAI_API_KEY is not set."
            )

    def is_configured(self) -> bool:
        from app.services.import_engine.config import engine_config
        return bool(engine_config.openai_api_key)

    def parse_document(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("OpenAIParser.parse_document not yet implemented.")

    def parse_page(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("OpenAIParser.parse_page not yet implemented.")

    def parse_question(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("OpenAIParser.parse_question not yet implemented.")
