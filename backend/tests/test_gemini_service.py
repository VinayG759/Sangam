"""
Unit tests for GeminiService.

Since the Gemini API requires an API key and network access,
all tests mock the external API calls and focus on:
- Correct prompt construction and response parsing
- Fallback behavior when API calls fail
- Embedding generation and fallback
- Singleton pattern
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from app.services.gemini_service import GeminiService, CitizenReportAnalysis, PolicyBrief


@pytest.fixture
def gemini_service():
    """Create a fresh GeminiService instance with mocked client."""
    # Create new instance (bypass singleton for test isolation)
    service = GeminiService.__new__(GeminiService)
    service._client = MagicMock()
    return service


class TestAnalyzeCitizenReport:
    """Tests for analyze_citizen_report."""

    def test_successful_analysis(self, gemini_service):
        """Should parse Gemini response JSON correctly."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "original_language": "kn",
            "english_translation": "There are potholes on the main road.",
            "sector": "roads",
            "specific_issue": "Dangerous potholes",
            "urgency_score": 4.5,
            "sentiment": "negative",
            "extracted_location_entities": ["Koramangala"],
            "pii_redacted_text": "There are potholes on the main road."
        })

        gemini_service._client.models.generate_content.return_value = mock_response

        result = gemini_service.analyze_citizen_report("ಕೋರಮಂಗಲ ರಸ್ತೆಯಲ್ಲಿ ಗುಂಡಿಗಳಿವೆ")

        assert result["sector"] == "roads"
        assert result["urgency_score"] == 4.5
        assert result["original_language"] == "kn"
        assert "potholes" in result["english_translation"].lower()

    def test_fallback_on_api_error(self, gemini_service):
        """Should return safe fallback when Gemini API fails."""
        gemini_service._client.models.generate_content.side_effect = Exception("API quota exceeded")

        result = gemini_service.analyze_citizen_report("Test report text")

        assert result["sector"] == "other"
        assert result["urgency_score"] == 1.0
        assert result["sentiment"] == "neutral"
        assert result["original_language"] == "unknown"
        # The original text should be preserved in the fallback
        assert result["english_translation"] == "Test report text"

    def test_api_called_with_report_text(self, gemini_service):
        """Should include the citizen report text in the prompt."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "original_language": "en",
            "english_translation": "Water problem",
            "sector": "water",
            "specific_issue": "No water",
            "urgency_score": 3.0,
            "sentiment": "negative",
            "extracted_location_entities": [],
            "pii_redacted_text": "Water problem"
        })
        gemini_service._client.models.generate_content.return_value = mock_response

        gemini_service.analyze_citizen_report("Water problem in our area")

        call_args = gemini_service._client.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents", "") or call_args[1].get("contents", "")
        assert "Water problem in our area" in prompt


class TestGetEmbedding:
    """Tests for get_embedding."""

    def test_successful_embedding(self, gemini_service):
        """Should return embedding values from API response."""
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2, 0.3] + [0.0] * 765  # 768 dimensions
        mock_response.embeddings = [mock_embedding]

        gemini_service._client.models.embed_content.return_value = mock_response

        result = gemini_service.get_embedding("test text")

        assert len(result) == 768
        assert result[0] == 0.1
        assert result[1] == 0.2

    def test_fallback_on_error(self, gemini_service):
        """Should return zero vector on API failure."""
        gemini_service._client.models.embed_content.side_effect = Exception("Network error")

        result = gemini_service.get_embedding("test text")

        assert len(result) == 768
        assert all(v == 0.0 for v in result)


class TestGeneratePolicyBrief:
    """Tests for generate_policy_brief."""

    def test_successful_brief_generation(self, gemini_service):
        """Should parse policy brief JSON from Gemini response."""
        brief_json = {
            "summary": "Water crisis in Ward A with 5 unresolved complaints.",
            "why_prioritized": "High demand density and vulnerability.",
            "fiscal_gap_analysis": "Budget gap of ₹50,00,000 identified.",
            "recommended_action": "Allocate emergency funds for borewell repairs."
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(brief_json)
        gemini_service._client.models.generate_content.return_value = mock_response

        result = gemini_service.generate_policy_brief({"cluster_id": 1, "report_count": 5})

        assert result["summary"] == brief_json["summary"]
        assert result["recommended_action"] == brief_json["recommended_action"]

    def test_fallback_on_api_error(self, gemini_service):
        """Should return safe fallback brief when API fails."""
        gemini_service._client.models.generate_content.side_effect = Exception("timeout")

        result = gemini_service.generate_policy_brief({"cluster_id": 1})

        assert "summary" in result
        assert "why_prioritized" in result
        assert "fiscal_gap_analysis" in result
        assert "recommended_action" in result
        # Should not be empty
        assert len(result["summary"]) > 0

    def test_evidence_bundle_included_in_prompt(self, gemini_service):
        """Should include the evidence bundle JSON in the prompt."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "summary": "Test",
            "why_prioritized": "Test",
            "fiscal_gap_analysis": "Test",
            "recommended_action": "Test"
        })
        gemini_service._client.models.generate_content.return_value = mock_response

        evidence = {"cluster_id": 42, "report_count": 10}
        gemini_service.generate_policy_brief(evidence)

        call_args = gemini_service._client.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents", "") or call_args[1].get("contents", "")
        assert "42" in prompt
        assert "10" in prompt


class TestSingleton:
    """Tests for the singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Two instantiations should return the same object."""
        a = GeminiService()
        b = GeminiService()
        assert a is b


class TestSchemas:
    """Tests for the Pydantic schema definitions used by Gemini service."""

    def test_citizen_report_analysis_schema(self):
        analysis = CitizenReportAnalysis(
            original_language="kn",
            english_translation="Pothole issue",
            sector="roads",
            specific_issue="Big pothole",
            urgency_score=4.0,
            sentiment="negative",
            extracted_location_entities=["Ward 5"],
            pii_redacted_text="Pothole issue"
        )
        assert analysis.sector == "roads"
        assert analysis.urgency_score == 4.0

    def test_policy_brief_schema(self):
        brief = PolicyBrief(
            summary="Test summary",
            why_prioritized="High demand",
            fiscal_gap_analysis="50% gap",
            recommended_action="Allocate funds"
        )
        assert brief.summary == "Test summary"
