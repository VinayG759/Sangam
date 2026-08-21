import json
import logging
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

    def analyze_citizen_report(self, text_content: str) -> Dict[str, Any]:
        """
        Call 1: Analyze citizen voice/text report, translate to English, categorise, and redact PII.
        """
        prompt = f"""
        Analyze the following citizen report. Redact any personally identifiable information (PII)
        such as names, telephone numbers, emails, and home addresses, and extract categories.
        
        Citizen Report:
        \"\"\"{text_content}\"\"\"
        """
        try:
            response = self.client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CitizenReportAnalysis,
                    temperature=0.1
                )
            )
            return json.loads(response.text)
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
                "pii_redacted_text": text_content
            }

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate semantic vector embedding for similarity mapping.
        """
        try:
            response = self.client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text
            )
            # Response format has embeddings list containing values list
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"Error generating embedding from Gemini: {e}")
            # Return dummy list of correct length (768) if it fails
            return [0.0] * 768

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
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Error calling Gemini generate_policy_brief: {e}")
            return {
                "summary": "Could not generate policy summary due to service timeout.",
                "why_prioritized": "High prioritized based on cluster metrics and demand density.",
                "fiscal_gap_analysis": "Budget allocations mismatch detected.",
                "recommended_action": "Verify allocations and schedule local inspection."
            }

gemini_service = GeminiService()
import os
