"""
Fingerprint Registry
====================
Provides extensible layout fingerprints and signature definitions 
to decoupled from the main DocumentDetector logic.
"""

from __future__ import annotations

import re
from app.services.import_engine.models import DocumentType

class FingerprintRegistry:
    # ---------------------------------------------------------------------------
    # Known PDF platform signatures
    # Tuple of (substring_to_search, document_type, weight)
    # These are searched in PDF metadata fields: Producer, Creator, Author.
    # ---------------------------------------------------------------------------
    PDF_PLATFORM_SIGNATURES: list[tuple[str, DocumentType, float]] = [
        # Microsoft Forms exports
        ("microsoft forms",     DocumentType.MICROSOFT_FORMS,   0.90),
        ("microsoft office",    DocumentType.MICROSOFT_FORMS,   0.55),
        ("word",                DocumentType.MICROSOFT_FORMS,   0.40),

        # Google Forms exports
        ("google",              DocumentType.GOOGLE_FORMS,      0.70),
        ("chromium",            DocumentType.GOOGLE_FORMS,      0.55),
        ("skia",                DocumentType.GOOGLE_FORMS,      0.60),  # Chrome PDF renderer

        # AIQM LMS exports
        ("aiqm",                DocumentType.AIQM_LMS,          0.95),
        ("aiqm lms",            DocumentType.AIQM_LMS,          0.99),
    ]

    # ---------------------------------------------------------------------------
    # Text-based signatures searched in the first ~1000 chars of extracted text
    # ---------------------------------------------------------------------------
    TEXT_CONTENT_SIGNATURES: list[tuple[str, DocumentType, float]] = [
        # AIQM LMS
        ("aiqm",                DocumentType.AIQM_LMS,          0.90),
        ("examination portal",  DocumentType.AIQM_LMS,          0.75),

        # Microsoft Forms
        ("microsoft forms",     DocumentType.MICROSOFT_FORMS,   0.85),

        # Google Forms
        ("google forms",        DocumentType.GOOGLE_FORMS,      0.85),
    ]

    # Patterns that suggest PDF extraction artefacts
    ARTEFACT_PATTERNS: list[re.Pattern] = [
        re.compile(r"^\d+\s*\.\s*$"),          # lone number like "3."
        re.compile(r"^[^a-zA-Z]{0,3}$"),        # non-alphanumeric junk
        re.compile(r"^\s*page\s+\d+\s*$", re.I),  # page headers
    ]
