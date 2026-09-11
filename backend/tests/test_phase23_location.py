import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.location_resolver import resolve_location, resolve_location_with_confidence
from app.models.models import AdminRegion, CitizenReport, PendingIntake
from app.services.ingestion_service import ingest_citizen_message
from app.services.telegram_adapter import handle_telegram_update
from app.services.whatsapp_adapter import handle_whatsapp_update

@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    
    hiriyur = AdminRegion(
        id=10,
        country_code="IN",
        level="subdistrict",
        name="Hiriyur",
        name_variants="Hiriyur Taluk"
    )
    bengaluru = AdminRegion(
        id=11,
        country_code="IN",
        level="district",
        name="Bengaluru",
        name_variants="Bangalore|Bengaluru Urban"
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [hiriyur, bengaluru]
    mock_session.execute.return_value = mock_result
    
    return mock_session


@pytest.mark.asyncio
async def test_resolve_location_confidence_tiers(mock_db_session):
    # High confidence: exact match
    res_exact = await resolve_location_with_confidence("Hiriyur", "IN", mock_db_session)
    assert res_exact["confidence"] == "high"
    assert res_exact["region"] is not None
    assert res_exact["region"].name == "Hiriyur"
    assert res_exact["candidate"] is None

    # High confidence: fuzzy match >= 85
    res_high = await resolve_location_with_confidence("Hiriyuru", "IN", mock_db_session)
    assert res_high["confidence"] == "high"
    assert res_high["region"] is not None
    assert res_high["region"].name == "Hiriyur"

    # Medium confidence: e.g. "Hiyur" scores ~83 against "Hiriyur"
    res_med = await resolve_location_with_confidence("Hiyur", "IN", mock_db_session)
    assert res_med["confidence"] == "medium"
    assert res_med["region"] is None
    assert res_med["candidate"] is not None
    assert res_med["candidate"].name == "Hiriyur"

    # Low confidence: unrecognizable string
    res_low = await resolve_location_with_confidence("CompletelyDifferentPlaceXYZ", "IN", mock_db_session)
    assert res_low["confidence"] == "low"
    assert res_low["region"] is None
    assert res_low["candidate"] is None


@pytest.mark.asyncio
async def test_ingest_citizen_message_with_gps(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    class MockGemini:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": text_content,
                "sector": "roads",
                "specific_issue": "pothole",
                "urgency_score": 3.0,
                "sentiment": "negative",
                "location_text_latin": None,
                "pii_redacted_text": text_content,
            }
        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGemini())

    result = await ingest_citizen_message(
        db=mock_session,
        text="Big pothole on the road",
        latitude=13.9446,
        longitude=76.6172,
        channel="telegram",
        channel_user_id="12345"
    )

    assert result["status"] == "success"
    assert result["needs_location_followup"] is False
    assert result["needs_location_confirmation"] is False

    # Verify that added report has geometry location set
    added_report = None
    for call in mock_session.add.call_args_list:
        if isinstance(call[0][0], CitizenReport):
            added_report = call[0][0]
            break

    assert added_report is not None
    assert added_report.location == "SRID=4326;POINT(76.6172 13.9446)"


@pytest.mark.asyncio
async def test_ingest_citizen_message_medium_confidence_triggers_confirmation(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    class MockGemini:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "kn",
                "english_translation": "water problem in Hiyur",
                "sector": "water",
                "specific_issue": "leak",
                "urgency_score": 2.0,
                "sentiment": "negative",
                "location_text_latin": "Hiyur",
                "pii_redacted_text": "water problem in Hiyur",
            }
        def get_embedding(self, text):
            return [0.1] * 768

    candidate_region = AdminRegion(id=42, name="Hiriyur", country_code="IN", level="subdistrict")

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGemini())
    monkeypatch.setattr(ingestion_module, "resolve_location", AsyncMock(return_value=None))
    monkeypatch.setattr(ingestion_module, "resolve_location_with_confidence", AsyncMock(return_value={
        "region": None,
        "candidate": candidate_region,
        "confidence": "medium",
        "score": 75.0
    }))

    result = await ingest_citizen_message(
        db=mock_session,
        text="neerina samasye ide Hiyur nalli",
        channel="telegram",
        channel_user_id="user_789"
    )

    assert result["needs_location_confirmation"] is True
    assert result["candidate_region_name"] == "Hiriyur"


@pytest.mark.asyncio
async def test_telegram_confirm_candidate_location_with_yes(monkeypatch):
    mock_session = AsyncMock()
    pending = PendingIntake(
        channel_user_hash="hash_123",
        channel="telegram",
        partial_report={"report_id": 99, "candidate_region_id": 42, "candidate_region_name": "Hiriyur"},
        awaiting="location_confirmation",
        expires_at=None
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pending
    mock_session.execute.return_value = mock_result

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_bot_token")
    mock_send = AsyncMock()
    import app.services.telegram_adapter as tg_module
    monkeypatch.setattr(tg_module, "_send_telegram_message", mock_send)
    monkeypatch.setattr(tg_module, "hash_channel_user", lambda uid: "hash_123")

    update_payload = {
        "message": {
            "chat": {"id": 12345},
            "text": "yes"
        }
    }

    await handle_telegram_update(update_payload, mock_session)

    # Pending deleted
    mock_session.delete.assert_called_once_with(pending)
    # Message sent confirming Hiriyur
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "Location confirmed as Hiriyur" in sent_text


@pytest.mark.asyncio
async def test_telegram_pending_location_update_via_gps(monkeypatch):
    mock_session = AsyncMock()
    pending = PendingIntake(
        channel_user_hash="hash_123",
        channel="telegram",
        partial_report={"report_id": 99},
        awaiting="location",
        expires_at=None
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pending
    mock_session.execute.return_value = mock_result

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_bot_token")
    mock_send = AsyncMock()
    import app.services.telegram_adapter as tg_module
    monkeypatch.setattr(tg_module, "_send_telegram_message", mock_send)
    monkeypatch.setattr(tg_module, "hash_channel_user", lambda uid: "hash_123")

    # User sends a native Telegram GPS pin
    update_payload = {
        "message": {
            "chat": {"id": 12345},
            "location": {"latitude": 13.9446, "longitude": 76.6172}
        }
    }

    await handle_telegram_update(update_payload, mock_session)

    mock_session.delete.assert_called_once_with(pending)
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "Location updated successfully with GPS coordinates" in sent_text


@pytest.mark.asyncio
async def test_whatsapp_confirm_candidate_location_with_haudu(monkeypatch):
    mock_session = AsyncMock()
    pending = PendingIntake(
        channel_user_hash="hash_wa_123",
        channel="whatsapp",
        partial_report={"report_id": 105, "candidate_region_id": 42, "candidate_region_name": "Hiriyur"},
        awaiting="location_confirmation",
        expires_at=None
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pending
    mock_session.execute.return_value = mock_result

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_access_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "test_phone_id")
    mock_send = AsyncMock()
    import app.services.whatsapp_adapter as wa_module
    monkeypatch.setattr(wa_module, "_send_whatsapp_message", mock_send)
    monkeypatch.setattr(wa_module, "hash_channel_user", lambda uid: "hash_wa_123")

    # User sends Kannada affirmative "haudu"
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919876543210",
                        "type": "text",
                        "text": {"body": "Haudu"}
                    }]
                }
            }]
        }]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_session.delete.assert_called_once_with(pending)
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "Location confirmed as Hiriyur" in sent_text


@pytest.mark.asyncio
async def test_whatsapp_pending_location_update_via_gps(monkeypatch):
    mock_session = AsyncMock()
    pending = PendingIntake(
        channel_user_hash="hash_wa_123",
        channel="whatsapp",
        partial_report={"report_id": 105},
        awaiting="location",
        expires_at=None
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pending
    mock_session.execute.return_value = mock_result

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_access_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "test_phone_id")
    mock_send = AsyncMock()
    import app.services.whatsapp_adapter as wa_module
    monkeypatch.setattr(wa_module, "_send_whatsapp_message", mock_send)
    monkeypatch.setattr(wa_module, "hash_channel_user", lambda uid: "hash_wa_123")

    # User sends WhatsApp location type
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919876543210",
                        "type": "location",
                        "location": {
                            "latitude": 13.9446,
                            "longitude": 76.6172
                        }
                    }]
                }
            }]
        }]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_session.delete.assert_called_once_with(pending)
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "Location updated successfully with GPS coordinates" in sent_text
