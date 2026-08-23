import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.ingestion_service import ingest_citizen_message
from app.models.models import CitizenReport


@pytest.fixture(autouse=True)
def _no_background_reprocess(monkeypatch):
    # ingest_citizen_message schedules a real asyncio background task on
    # success (see reprocess_scheduler.py) -- these tests care about the
    # report row it builds, not that side effect, and leaving it real would
    # spawn a task that outlives the test (it sleeps DEBOUNCE_SECONDS
    # before doing anything real).
    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "schedule_reprocess", MagicMock())


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


@pytest.mark.asyncio
async def test_needs_location_followup_upserts_pending_intake(monkeypatch):
    # channel_user_hash is PendingIntake's primary key -- a plain insert
    # crashes with a UniqueViolationError if this user already has an
    # earlier, unanswered location question outstanding (reproduced live:
    # a voice note that itself needed a location follow-up collided with
    # one from a still-unresolved text report). Must be an upsert instead.
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    class MockGeminiService:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": text_content,
                "sector": "roads",
                "specific_issue": "pothole",
                "urgency_score": 3.0,
                "sentiment": "negative",
                "location_text_latin": "Some Unknown Place",
                "pii_redacted_text": text_content,
            }

        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiService())
    # Force the "couldn't resolve a location" branch regardless of what
    # regions exist in whatever DB this suite happens to run against.
    monkeypatch.setattr(ingestion_module, "resolve_location", AsyncMock(return_value=None))

    result = await ingest_citizen_message(
        db=mock_session,
        text="Potholes somewhere unspecified",
        channel="telegram",
        channel_user_id="user_123",
    )

    assert result["needs_location_followup"] is True

    # Find the PendingIntake upsert among the execute() calls (the
    # CitizenReport insert itself goes through db.add(), not execute()).
    upsert_call = None
    for call in mock_session.execute.call_args_list:
        stmt = call[0][0]
        if "pending_intake" in str(stmt).lower():
            upsert_call = stmt
            break

    assert upsert_call is not None, "expected a statement touching pending_intake"
    compiled = str(upsert_call.compile(dialect=__import__("sqlalchemy.dialects.postgresql", fromlist=["dialect"]).dialect()))
    assert "ON CONFLICT" in compiled.upper()

