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
