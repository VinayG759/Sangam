import json
import logging
import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger(__name__)

# call 1 Schema definition
class CitizenReportAnalysis(BaseModel):
    original_language: str = Field(description="ISO language code or language name of the original input")
    english_translation: str = Field(description="Full English translation of the citizen report")
    sector: str = Field(description="Extracted sector: water, roads, sanitation, health, education, electricity, or other")
    specific_issue: str = Field(description="Brief summary of the specific issue reported")
    urgency_score: float = Field(description="Urgency score from 1.0 (low priority) to 5.0 (immediate crisis/danger)")
    sentiment: str = Field(description="Sentiment: positive, neutral, or negative")
    extracted_location_entities: List[str] = Field(default=[], description="List of location entities (wards, streets, landmarks) extracted")
    location_text_latin: Optional[str] = Field(default=None, description="The place name romanized into a standard spelling for gazetteer resolution")
    pii_redacted_text: str = Field(description="English translation text with PII (names, phone numbers, emails) replaced by [REDACTED]")

# call 3 Schema definition
class PolicyBrief(BaseModel):
    summary: str = Field(description="High-level 1-2 sentence executive summary of the issue cluster and the budget gap.")
    why_prioritized: str = Field(description="Detailed explanation of why this issue has a high priority score (density, vulnerability, urgency factors).")
    fiscal_gap_analysis: str = Field(description="Analysis of existing allocations vs. citizen need, highlighting unserved gaps or stalled funds.")
    recommended_action: str = Field(description="Grounded, concrete, actionable recommendation for the local governance administration.")

class GeminiService:
    _instance = None
    _client = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GeminiService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @property
    def client(self):
        if not self._client:
            # Fallback for local testing if API key is not in settings
            api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY is not set. Gemini API calls will fail.")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def analyze_citizen_report(self, text_content: Optional[str] = None, audio_bytes: Optional[bytes] = None, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Call 1: Analyze citizen voice/text report, translate to English, categorise, and redact PII.
        Accepts either text_content or audio_bytes with mime_type.
        """
        prompt = """
        Analyze the following citizen report. Redact any personally identifiable information (PII)
        such as names, telephone numbers, emails, and home addresses, and extract categories.
        If this is an audio file, transcribe it first, then analyze it.
        """
        
        contents = [prompt]
        if audio_bytes and mime_type:
            contents.append(
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
            )
        if text_content:
            contents.append(text_content)

        try:
            response = self.client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CitizenReportAnalysis,
                    temperature=0.1
                )
            )
            # response_schema constrains the model's output; it does not
            # guarantee it. A real response (Kannada input, report id 20 in
            # the local DB) came back with pii_redacted_text missing/null
            # despite every other field being fine -- this went straight
            # into the database as a null redacted-text column because
            # nothing here checked the parsed JSON against the schema it
            # was already importing and passing to the API. Validating
            # catches that class of partial response the same way a full
            # API failure is already caught below, rather than silently
            # trusting whatever came back.
            validated = CitizenReportAnalysis.model_validate_json(response.text)
            return validated.model_dump()
        except Exception as e:
            logger.error(f"Error calling Gemini analyze_citizen_report: {e}")
            # Fallback basic schema on failure
            return {
                "original_language": "unknown",
                "english_translation": text_content,
                "sector": "other",
                "specific_issue": "Failed to analyze report automatically",
                "urgency_score": 1.0,
                "sentiment": "neutral",
                "extracted_location_entities": [],
                "location_text_latin": None,
                "pii_redacted_text": text_content or "[Audio - Failed to process]"
            }

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate semantic vector embedding for similarity mapping.
        """
        dim = settings.GEMINI_EMBEDDING_DIM
        try:
            # output_dimensionality is not optional. gemini-embedding-001
            # defaults to 3072 dimensions; the embedding column is Vector(768),
            # so omitting this raises on insert rather than at call time --
            # a failure that would surface deep in the batch job, not here.
            response = self.client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text,
                config={"output_dimensionality": dim},
            )
            values = list(response.embeddings[0].values)
            if len(values) != dim:
                logger.error(
                    "Embedding model %s returned %d dimensions, expected %d. "
                    "Refusing to return a mis-shaped vector.",
                    settings.GEMINI_EMBEDDING_MODEL, len(values), dim,
                )
                return [0.0] * dim
            return values
        except Exception as e:
            logger.error(f"Error generating embedding from Gemini: {e}")
            return [0.0] * dim

    def generate_policy_brief(self, evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call 3: Generate a grounded policy brief narrative based strictly on evidence bundle values.
        """
        prompt = f"""
        Generate a policy brief narrative based strictly on the provided evidence bundle JSON.
        You must only refer to facts, numbers, and quotes contained in the evidence bundle.
        Do not make up any numbers or insert external assumptions.
        
        Evidence Bundle JSON:
        {json.dumps(evidence_bundle, indent=2)}
        """
        try:
            response = self.client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PolicyBrief,
                    temperature=0.1
                )
            )
            # Same gap as analyze_citizen_report above -- unvalidated, this
            # is worse here: clustering_engine.py reads the result with
            # plain dict indexing (brief_data['summary']), so a response
            # missing a field wouldn't just pass bad data through, it would
            # raise KeyError and crash the whole clustering run.
            validated = PolicyBrief.model_validate_json(response.text)
            return validated.model_dump()
        except Exception as e:
            logger.error(f"Error calling Gemini generate_policy_brief: {e}")
            return {
                "summary": "Could not generate policy summary due to service timeout.",
                "why_prioritized": "High prioritized based on cluster metrics and demand density.",
                "fiscal_gap_analysis": "Budget allocations mismatch detected.",
                "recommended_action": "Verify allocations and schedule local inspection."
            }

gemini_service = GeminiService()
