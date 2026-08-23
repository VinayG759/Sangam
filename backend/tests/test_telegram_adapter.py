import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.telegram_adapter import handle_telegram_update

@pytest.mark.asyncio
async def test_handle_telegram_update_photo(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.telegram_adapter as telegram_module
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {
        "message": {
            "chat": {"id": 123456},
            "photo": [
                {"file_id": "low_res_file", "file_size": 1000},
                {"file_id": "high_res_file", "file_size": 5000}
            ]
        }
    }

    class MockResponse:
        def __init__(self, json_data=None, bytes_data=None):
            self.status = 200
            self.json_data = json_data
            self.bytes_data = bytes_data
        async def json(self):
            return self.json_data
        async def read(self):
            return self.bytes_data
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockClientSession:
        def get(self, url):
            if "getFile" in url:
                assert "high_res_file" in url
                return MockResponse(json_data={"result": {"file_path": "photos/high_res.jpg"}})
            else:
                assert "photos/high_res.jpg" in url
                return MockResponse(bytes_data=b"fake_image_bytes")
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", MockClientSession)

    await handle_telegram_update(update_payload, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text=None,
        audio_bytes=b"fake_image_bytes",
        mime_type="image/jpeg",
        channel="telegram",
        channel_user_id="123456"
    )

    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_handle_telegram_update_start_command_is_not_ingested(monkeypatch):
    # Telegram sends "/start" the moment someone opens the bot -- this must
    # not be treated as citizen report content (reproduced live: it was
    # going straight to Gemini and getting saved as a real report).
    mock_session = AsyncMock()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")

    mock_ingest = AsyncMock()
    import app.services.telegram_adapter as telegram_module
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "/start"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_ingest.assert_not_called()
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == 123456
    assert "Welcome" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_pending_location_reply_that_crashes_still_gets_a_reply(monkeypatch):
    # Reproduced live: a citizen sent a message right after a location
    # prompt and got total silence -- an exception in this block used to
    # propagate past webhooks.py's own try/except, which only logs and
    # returns 200 to Telegram, so nothing ever reached the user.
    import app.services.telegram_adapter as telegram_module
    from app.models.models import PendingIntake

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location",
        partial_report={"report_id": 42},
        expires_at=telegram_module.datetime(2999, 1, 1),
    )

    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    mock_session.rollback = AsyncMock()

    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    mock_session.execute.side_effect = [pending_lookup]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    monkeypatch.setattr(telegram_module, "resolve_location", AsyncMock(side_effect=RuntimeError("boom")))

    mock_ingest = AsyncMock()
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)
    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "anything"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_session.rollback.assert_called_once()
    mock_ingest.assert_not_called()
    mock_send.assert_called_once()
    assert "error" in mock_send.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_pending_location_reply_that_fails_to_resolve_is_ingested_as_new_report(monkeypatch):
    # A reply to "what's the location?" that doesn't match a known place
    # name is far more often unrelated new content than a genuine failed
    # location guess -- it must not be silently discarded. See the comment
    # at the fall-through site in telegram_adapter.py.
    import app.services.telegram_adapter as telegram_module
    from app.models.models import PendingIntake, CitizenReport

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location",
        partial_report={"report_id": 42},
        expires_at=telegram_module.datetime(2999, 1, 1),
    )
    old_report = MagicMock(spec=CitizenReport)
    old_report.tracking_id = "SNG-OLD1"

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = AsyncMock()

    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    old_report_lookup = MagicMock()
    old_report_lookup.scalar_one_or_none.return_value = old_report
    mock_session.execute.side_effect = [pending_lookup, old_report_lookup]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    monkeypatch.setattr(telegram_module, "resolve_location", AsyncMock(return_value=None))

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-NEW2"})
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "who is narendra modi"}}

    await handle_telegram_update(update_payload, mock_session)

    # The new text must actually be ingested as its own report, not dropped.
    mock_ingest.assert_called_once_with(
        db=mock_session,
        text="who is narendra modi",
        audio_bytes=None,
        mime_type=None,
        channel="telegram",
        channel_user_id="123456",
    )
    # One message about the old report's fate, one about the new report.
    assert mock_send.call_count == 2
    assert "SNG-OLD1" in mock_send.call_args_list[0][0][1]
    assert "SNG-NEW2" in mock_send.call_args_list[1][0][1]


@pytest.mark.asyncio
async def test_handle_telegram_update_other_command_is_not_ingested(monkeypatch):
    mock_session = AsyncMock()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")

    mock_ingest = AsyncMock()
    import app.services.telegram_adapter as telegram_module
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "/help@Ghgggggjsbcjzgabckxbot"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_ingest.assert_not_called()
    mock_send.assert_called_once()
