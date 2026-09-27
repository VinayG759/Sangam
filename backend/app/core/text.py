"""Deterministic PII redaction — the second pass after Gemini's own redaction."""

import re

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # email
    re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)"),  # phone numbers, 12-digit IDs (Aadhaar), long digit runs
]


def redact(text: str | None) -> str | None:
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text
