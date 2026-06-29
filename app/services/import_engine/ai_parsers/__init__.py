"""
AI Provider Registry
====================
Resolves the active AI provider from configuration.

Usage:
    from app.services.import_engine.ai_parsers import get_ai_parser

    parser = get_ai_parser()          # reads AI_PROVIDER env var
    result = parser.parse_document(request)

Adding a new provider:
    1. Create a new module in ai_parsers/ that inherits BaseAIParser.
    2. Add an entry to _PROVIDER_MAP below.
    3. Set AI_PROVIDER=<your_key> in the environment.
    No other changes are required.
"""

from __future__ import annotations

import logging

from app.services.import_engine.ai_parsers.base_ai_parser import BaseAIParser
from app.services.import_engine.ai_parsers.claude_parser import ClaudeParser
from app.services.import_engine.ai_parsers.gemini_parser import GeminiParser
from app.services.import_engine.ai_parsers.local_parser import LocalParser
from app.services.import_engine.ai_parsers.openai_parser import OpenAIParser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider registry — maps AI_PROVIDER value → parser class
# ---------------------------------------------------------------------------
_PROVIDER_MAP: dict[str, type[BaseAIParser]] = {
    "gemini":  GeminiParser,
    "openai":  OpenAIParser,
    "claude":  ClaudeParser,
    "local":   LocalParser,
}


def get_ai_parser(provider: str | None = None) -> BaseAIParser:
    """
    Resolve and instantiate the configured AI provider.

    Parameters
    ----------
    provider : override the AI_PROVIDER env var (useful for tests)

    Returns
    -------
    An instance of the appropriate BaseAIParser subclass.
    Defaults to GeminiParser if the provider name is unrecognised.
    """
    from app.services.import_engine.config import engine_config

    name = (provider or engine_config.ai_provider).lower()
    cls = _PROVIDER_MAP.get(name)

    if cls is None:
        logger.warning(
            "AI provider %r not found in registry, falling back to Gemini. "
            "Valid providers: %s",
            name,
            list(_PROVIDER_MAP),
        )
        cls = GeminiParser

    instance = cls()
    logger.info("AI parser resolved: %s", instance)
    return instance


def list_providers() -> list[str]:
    """Return a list of all registered provider names."""
    return list(_PROVIDER_MAP)


__all__ = [
    "BaseAIParser",
    "GeminiParser",
    "OpenAIParser",
    "ClaudeParser",
    "LocalParser",
    "get_ai_parser",
    "list_providers",
]
