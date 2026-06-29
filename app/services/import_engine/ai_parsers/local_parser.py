"""
Local Parser — Skeleton
========================
Reserved slot for a locally-hosted LLM (e.g. Ollama, llama.cpp).

Status: SKELETON PLACEHOLDER
"""

from __future__ import annotations

from app.services.import_engine.ai_parsers.base_ai_parser import (
    AIParseRequest,
    BaseAIParser,
)
from app.services.import_engine.models import ExtractionResult


class LocalParser(BaseAIParser):
    """
    Placeholder for a locally-hosted model (Ollama, llama.cpp, etc.).
    Configure via LOCAL_MODEL_URL and LOCAL_MODEL_NAME env vars.
    """
    provider_name = "local"

    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("LOCAL_MODEL_URL"))

    def parse_document(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("LocalParser.parse_document not yet implemented.")

    def parse_page(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("LocalParser.parse_page not yet implemented.")

    def parse_question(self, request: AIParseRequest) -> ExtractionResult:
        raise NotImplementedError("LocalParser.parse_question not yet implemented.")
