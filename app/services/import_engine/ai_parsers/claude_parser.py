"""
Claude Parser — Skeleton
=========================
Reserved slot for an Anthropic Claude implementation.

Status: SKELETON PLACEHOLDER
"""

from __future__ import annotations

from app.services.import_engine.ai_parsers.base_ai_parser import (
    AIParseRequest,
    BaseAIParser,
)
from app.services.import_engine.models import ExtractionResult


class ClaudeParser(BaseAIParser):
    provider_name = "claude"

    def _validate_config(self) -> None:
        from app.services.import_engine.config import engine_config
        if not engine_config.claude_api_key:
            import logging
            logging.getLogger(__name__).warning(
                "ClaudeParser: CLAUDE_API_KEY is not set."
            )

    def is_configured(self) -> bool:
        from app.services.import_engine.config import engine_config
        return bool(engine_config.claude_api_key)

    def parse_document(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("ClaudeParser.parse_document not yet implemented.")

    def parse_page(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("ClaudeParser.parse_page not yet implemented.")

    def parse_question(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("ClaudeParser.parse_question not yet implemented.")
