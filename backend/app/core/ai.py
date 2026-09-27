"""
The only place Sangam talks to Gemini. Three calls, each with a contract:

  understand()     live   — voice/photo/text → structured fields
  embed()          live   — English text → meaning vector
  write_summary()  batch  — closed evidence bundle → 2–3 sentence explanation

Every failure raises AIUnavailable. Nothing here ever returns a placeholder
(such as a vector of zeros) that could be stored as if it were real — callers
decide how to degrade.
"""

import json
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.pack import Pack

log = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """Gemini could not be reached or returned something unusable."""


class Understanding(BaseModel):
    language: str = Field(description="ISO 639-1 code of the language the citizen used, e.g. kn, hi, en")
    transcript: str = Field(description="What the citizen said, in their own language. Replace personal names, phone numbers and ID numbers with [redacted].")
    text_en: str = Field(description="Faithful English translation of the transcript, with the same redactions.")
    sector: str = Field(description="Exactly one need key from the allowed list.")
    urgency: int = Field(ge=1, le=5, description="1 = minor inconvenience, 5 = danger to life or health right now.")
    place_names: list[str] = Field(default_factory=list, description="Place names mentioned, romanised to standard English spelling, most specific first (a village before the larger areas that contain it).")
    is_actionable: bool = Field(description="False for greetings, tests, spam or messages with no infrastructure need.")


class Summary(BaseModel):
    summary: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class AIClient(Protocol):
    def understand(self, pack: Pack, text: str | None, media: bytes | None, mime_type: str | None) -> Understanding: ...
    def embed(self, text: str) -> list[float]: ...
    def write_summary(self, facts: list[dict], context: str) -> Summary: ...


class GeminiClient:
    def __init__(self) -> None:
        from google import genai

        settings = get_settings()
        if not settings.GEMINI_API_KEY:
            raise AIUnavailable("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._settings = settings

    def _generate(self, contents: list, schema: type[BaseModel]) -> BaseModel:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=schema, temperature=0
                ),
            )
            # response_schema constrains the output but does not guarantee it — validate.
            return schema.model_validate_json(response.text)
        except Exception as exc:  # network, quota, safety block, malformed JSON
            log.warning("Gemini generate failed: %s", exc)
            raise AIUnavailable(str(exc)) from exc

    def understand(self, pack: Pack, text: str | None, media: bytes | None, mime_type: str | None) -> Understanding:
        from google.genai import types

        needs = "\n".join(f"- {n.key}: {n.label_en} (e.g. {'; '.join(n.examples_en[:3])})" for n in pack.needs)
        prompt = (
            f"A citizen in {pack.country_name} is reporting a local infrastructure problem to the government. "
            f"They may write or speak in any language; common ones here: {', '.join(pack.languages)}.\n"
            f"If audio is attached, transcribe it first. If a photo is attached, describe the problem it shows.\n"
            f"Classify the need as exactly one of these keys, or '{pack.fallback_need}' if none fits:\n{needs}\n"
            "Never invent a place name that was not mentioned."
        )
        contents: list = [prompt]
        if media and mime_type:
            contents.append(types.Part.from_bytes(data=media, mime_type=mime_type))
        if text:
            contents.append(f"Citizen message:\n{text}")
        result = self._generate(contents, Understanding)
        if result.sector not in pack.need_keys:
            result.sector = pack.fallback_need
        return result

    def embed(self, text: str) -> list[float]:
        dim = self._settings.EMBEDDING_DIM
        try:
            response = self._client.models.embed_content(
                model=self._settings.GEMINI_EMBEDDING_MODEL, contents=text, config={"output_dimensionality": dim}
            )
            values = list(response.embeddings[0].values)
        except Exception as exc:
            log.warning("Gemini embed failed: %s", exc)
            raise AIUnavailable(str(exc)) from exc
        if len(values) != dim or not any(values):
            raise AIUnavailable(f"embedding unusable: {len(values)} dims, all-zero={not any(values)}")
        return values

    def write_summary(self, facts: list[dict], context: str) -> Summary:
        prompt = (
            "Write 2-3 plain sentences for a government planning officer explaining this recommendation.\n"
            f"Context: {context}\n"
            "Use ONLY the facts below. Every number you write must appear in a fact's value, exactly. "
            "Do not add numbers, dates, names or causes that are not in the facts. "
            "List the ids of the facts you used in cited_fact_ids.\n"
            f"Facts:\n{json.dumps(facts, ensure_ascii=False, indent=1)}"
        )
        return self._generate([prompt], Summary)


class NoAI:
    """Used when Gemini is not configured at all: every call degrades."""

    def understand(self, *args, **kwargs) -> Understanding:
        raise AIUnavailable("AI not configured")

    def embed(self, text: str) -> list[float]:
        raise AIUnavailable("AI not configured")

    def write_summary(self, facts: list[dict], context: str) -> Summary:
        raise AIUnavailable("AI not configured")


_client: AIClient | None = None


def get_ai() -> AIClient:
    """FastAPI dependency (tests override it). Without an API key every call degrades."""
    global _client
    if _client is None:
        try:
            _client = GeminiClient()
        except AIUnavailable:
            log.warning("GEMINI_API_KEY not set — intake will store reports for later processing")
            return NoAI()
    return _client
