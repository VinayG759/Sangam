import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.ingestion_service import ingest_citizen_message
from app.models.models import CitizenReport

@pytest.mark.asyncio
async def test_ingest_citizen_message_populates_fields(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()  # AsyncSession.add() is sync even on an async session
    mock_session.execute.return_value.scalar_one.return_value = CitizenReport(
        tracking_id="SNG-ABCD",
        channel="telegram",
        reporter_hash="0"*64,
        raw_text="Redacted",
        pii_redacted_text="The road is broken"
    )
    
    # Mock gemini service responses
    class MockGeminiService:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": "The road is broken",
                "sector": "roads",
                "specific_issue": "pothole",
                "urgency_score": 3.0,
                "sentiment": "negative",
                "pii_redacted_text": "The road is broken"
            }
            
        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiService())

    # Call the service
    result = await ingest_citizen_message(
        db=mock_session,
        text="My name is John and the road is broken",
        channel="telegram",
        channel_user_id="user_123"
    )

    assert result["status"] == "success"
    assert "tracking_id" in result
    assert result["tracking_id"].startswith("SNG-")
    
    # Find the added CitizenReport
    added_report = None
    for call in mock_session.add.call_args_list:
        if isinstance(call[0][0], CitizenReport):
            added_report = call[0][0]
            break
            
    assert added_report is not None

    assert added_report.tracking_id == result["tracking_id"]
    assert added_report.channel == "telegram"
    assert added_report.reporter_hash is not None
    assert len(added_report.reporter_hash) == 64
    assert added_report.raw_text == "Redacted"  # Because PII redaction succeeded
    assert added_report.pii_redacted_text == "The road is broken"

@pytest.mark.asyncio
async def test_ingest_citizen_message_fallback_raw_text(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()  # AsyncSession.add() is sync even on an async session

    class MockGeminiServiceFail:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "unknown",
                "english_translation": text_content,
                "sector": "other",
                "specific_issue": "Failed to analyze report automatically",
                "urgency_score": 1.0,
                "sentiment": "neutral",
                "pii_redacted_text": text_content
            }
            
        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiServiceFail())

    text_input = "Here is some input that fails redaction."
    result = await ingest_citizen_message(
        db=mock_session,
        text=text_input,
        channel="web"
    )

    # Find the added CitizenReport
    added_report = None
    for call in mock_session.add.call_args_list:
        if isinstance(call[0][0], CitizenReport):
            added_report = call[0][0]
            break
            
    assert added_report is not None

    assert added_report.tracking_id == result["tracking_id"]
    assert added_report.channel == "web"
    assert added_report.reporter_hash is None # No channel_user_id provided
    assert added_report.raw_text == text_input  # Because PII redaction failed (or rather fallback triggered)

@pytest.mark.asyncio
async def test_ingest_citizen_message_gemini_failure_degrades_gracefully(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    class MockGeminiServiceCrash:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            raise Exception("503 Service Unavailable: Rate limited")
            
        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiServiceCrash())

    text_input = "This report will fail analysis but still persist."
    result = await ingest_citizen_message(
        db=mock_session,
        text=text_input,
        channel="web"
    )

    assert result["status"] == "success"
    assert "tracking_id" in result
    assert result["tracking_id"].startswith("SNG-")
    assert result["analysis_extracted"] is None
    
    # Find the added CitizenReport
    added_report = None
    for call in mock_session.add.call_args_list:
        if isinstance(call[0][0], CitizenReport):
            added_report = call[0][0]
            break
            
    assert added_report is not None
    assert added_report.tracking_id == result["tracking_id"]
    assert added_report.status == "pending_analysis"
    assert added_report.raw_text == text_input
    assert added_report.english_translation is None
    assert added_report.sector == "unknown"

