"""
Speech-to-text for voice notes, through Sarvam (built for Indian languages).

Tested 30 Sep on Hindi, Kannada and Tamil: word-perfect transcripts in the
speaker's own script, the same on every run, and the right language detected.
Gemini-lite, listening to the same audio, often romanised Kannada or produced
the wrong alphabet for Tamil.

Optional: without SARVAM_API_KEY, or if Sarvam fails, this returns None and the
caller falls back to Gemini listening to the audio itself. Voice notes never
stop working because of it.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)
URL = "https://api.sarvam.ai/speech-to-text"


@dataclass
class Heard:
    text: str
    language: str | None  # ISO 639-1, e.g. "kn"


def speech_enabled() -> bool:
    return bool(get_settings().SARVAM_API_KEY)


def transcribe(audio: bytes, mime_type: str) -> Heard | None:
    settings = get_settings()
    if not settings.SARVAM_API_KEY:
        return None
    extension = mime_type.split("/")[-1].split(";")[0] or "audio"
    try:
        response = httpx.post(
            URL,
            headers={"api-subscription-key": settings.SARVAM_API_KEY},
            files={"file": (f"voice-note.{extension}", audio, mime_type.split(";")[0])},
            data={"model": settings.SARVAM_STT_MODEL, "language_code": "unknown"},  # "unknown" = detect it
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:  # network, quota, unsupported audio: fall back, never fail the report
        # The exception text can include the response body but never the key, which is only in a header.
        log.warning("Sarvam speech-to-text failed, falling back to Gemini: %s", type(exc).__name__)
        return None
    text = (body.get("transcript") or "").strip()
    if not text:
        return None
    language = (body.get("language_code") or "").split("-")[0] or None  # "kn-IN" -> "kn"
    return Heard(text=text, language=language)
