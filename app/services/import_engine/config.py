"""
Import Engine Configuration
============================
All feature flags and API credentials for the import engine are read
exclusively from environment variables.  No default values contain secrets.

Usage:
    from app.services.import_engine.config import engine_config

    if engine_config.ocr_enabled:
        ...
    if engine_config.ai_enabled:
        provider = engine_config.ai_provider
"""

from __future__ import annotations

import os


class ImportEngineConfig:
    """
    Reads configuration at import time from environment variables.
    All attributes are read-only properties so the values are always
    current (respects runtime os.environ mutations in tests).
    """

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    @property
    def ocr_enabled(self) -> bool:
        """Whether to attempt OCR on image-only PDFs."""
        return os.getenv("ENABLE_OCR", "true").strip().lower() in ("1", "true", "yes")

    @property
    def ocr_engine(self) -> str:
        """
        Which OCR backend to use.
        Supported values: 'tesseract' (default), 'easyocr'
        """
        return os.getenv("OCR_ENGINE", "tesseract").strip().lower()

    @property
    def ocr_language(self) -> str:
        """Tesseract language string, e.g. 'eng', 'eng+hin'."""
        return os.getenv("OCR_LANGUAGE", "eng").strip()

    @property
    def ocr_dpi(self) -> int:
        """DPI for PDF → image rasterisation (higher = better quality, slower)."""
        try:
            return int(os.getenv("OCR_DPI", "200"))
        except ValueError:
            return 200

    # ------------------------------------------------------------------
    # AI Parsing
    # ------------------------------------------------------------------

    @property
    def ai_enabled(self) -> bool:
        """Master switch for AI-assisted parsing."""
        return os.getenv("ENABLE_AI_IMPORT", "false").strip().lower() in ("1", "true", "yes")

    @property
    def ai_provider(self) -> str:
        """
        Which AI provider to use.
        Supported values: 'gemini' (default), 'openai', 'claude', 'local'
        """
        return os.getenv("AI_PROVIDER", "gemini").strip().lower()

    @property
    def ai_fallback_to_text(self) -> bool:
        """If True, fall back to text-based extraction when AI parsing fails."""
        return os.getenv("AI_FALLBACK_TO_TEXT", "true").strip().lower() in ("1", "true", "yes")

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    @property
    def gemini_api_key(self) -> str | None:
        return os.getenv("GEMINI_API_KEY") or None

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

    @property
    def gemini_timeout(self) -> int:
        try:
            return int(os.getenv("GEMINI_TIMEOUT", "30"))
        except ValueError:
            return 30

    # ------------------------------------------------------------------
    # OpenAI (future)
    # ------------------------------------------------------------------

    @property
    def openai_api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY") or None

    @property
    def openai_model(self) -> str:
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    # ------------------------------------------------------------------
    # Claude (future)
    # ------------------------------------------------------------------

    @property
    def claude_api_key(self) -> str | None:
        return os.getenv("CLAUDE_API_KEY") or None

    @property
    def claude_model(self) -> str:
        return os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307").strip()

    # ------------------------------------------------------------------
    # Detection thresholds
    # ------------------------------------------------------------------

    @property
    def ocr_chars_per_page_threshold(self) -> int:
        """
        Pages with fewer than this many characters are considered image-only
        and will be routed through OCR.
        """
        try:
            return int(os.getenv("OCR_CHARS_THRESHOLD", "80"))
        except ValueError:
            return 80

    @property
    def low_density_warning_threshold(self) -> int:
        """
        Pages below this (but above ocr_chars_per_page_threshold) trigger
        a 'low text density' annotation in the detection report.
        """
        try:
            return int(os.getenv("LOW_DENSITY_THRESHOLD", "200"))
        except ValueError:
            return 200

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        """Return a safe (no secrets) summary for logging/debugging."""
        return {
            "ocr_enabled":       self.ocr_enabled,
            "ocr_engine":        self.ocr_engine,
            "ocr_language":      self.ocr_language,
            "ocr_dpi":           self.ocr_dpi,
            "ai_enabled":        self.ai_enabled,
            "ai_provider":       self.ai_provider,
            "ai_fallback":       self.ai_fallback_to_text,
            "gemini_model":      self.gemini_model,
            "gemini_key_set":    bool(self.gemini_api_key),
            "openai_key_set":    bool(self.openai_api_key),
            "claude_key_set":    bool(self.claude_api_key),
        }


# Module-level singleton — import this everywhere
engine_config = ImportEngineConfig()
