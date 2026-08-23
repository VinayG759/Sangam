import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.whatsapp_adapter import handle_whatsapp_update, verify_meta_signature, extract_message


def _text_payload(from_number="911234567890", body="Hello world"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": from_number,
                        "type": "text",
                        "text": {"body": body},
                    }]
                }
            }]
        }]
    }


def test_verify_meta_signature():
    import hmac, hashlib
    body = b'{"entry":[]}'
    app_secret = "test_app_secret"

    mac = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256)
    valid_sig = "sha256=" + mac.hexdigest()

    assert verify_meta_signature(body, valid_sig, app_secret) == True
    assert verify_meta_signature(body, "sha256=deadbeef", app_secret) == False
    assert verify_meta_signature(body, valid_sig, "wrong_secret") == False
    assert verify_meta_signature(body, valid_sig, "") == False
    assert verify_meta_signature(body, "", app_secret) == False
    # Missing the "sha256=" prefix Meta always sends
    assert verify_meta_signature(body, mac.hexdigest(), app_secret) == False
    # Tampered body must not validate against a signature computed for the original
    assert verify_meta_signature(b'{"entry":["tampered"]}', valid_sig, app_secret) == False


def test_extract_message_returns_first_message():
    payload = _text_payload()
    message = extract_message(payload)
    assert message["from"] == "911234567890"
    assert message["text"]["body"] == "Hello world"


def test_extract_message_ignores_status_callbacks():
    # Delivery/read receipts use the same webhook subscription but carry
    # value.statuses instead of value.messages.
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{"id": "wamid.abc", "status": "delivered"}]
                }
            }]
        }]
    }
    assert extract_message(payload) is None


def test_extract_message_handles_malformed_payload():
    assert extract_message({}) is None
    assert extract_message({"entry": []}) is None


@pytest.mark.asyncio
async def test_handle_whatsapp_update_text(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    payload = _text_payload(from_number="911234567890", body="Hello world")

    await handle_whatsapp_update(payload, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text="Hello world",
        audio_bytes=None,
        mime_type=None,
        channel="whatsapp",
        channel_user_id="911234567890"
    )

    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert args[0] == "911234567890"
    assert "SNG-TEST" in args[1]
    assert args[2] == "test_token"
    assert args[3] == "123456789"


@pytest.mark.asyncio
async def test_handle_whatsapp_update_status_callback_is_ignored(monkeypatch):
    mock_session = AsyncMock()

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_ingest = AsyncMock()
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)
    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    payload = {
        "entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.abc", "status": "read"}]}}]}]
    }
    await handle_whatsapp_update(payload, mock_session)

    mock_ingest.assert_not_called()
    mock_send.assert_not_called()


def _media_payload(msg_type, media_id="media-123"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "911234567890",
                        "type": msg_type,
                        msg_type: {"id": media_id},
                    }]
                }
            }]
        }]
    }


class _MockLookupResponse:
    status = 200

    def __init__(self, mime_type):
        self._mime_type = mime_type

    async def json(self):
        return {"url": "https://mmg.whatsapp.net/media/xyz", "mime_type": self._mime_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _MockDownloadResponse:
    status = 200

    def __init__(self, data):
        self._data = data

    async def read(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_mock_session(mime_type, data):
    class MockClientSession:
        def __init__(self, headers=None):
            self.headers = headers

        def get(self, url):
            if url.startswith("https://graph.facebook.com"):
                return _MockLookupResponse(mime_type)
            assert url == "https://mmg.whatsapp.net/media/xyz"
            return _MockDownloadResponse(data)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    return MockClientSession


@pytest.mark.asyncio
async def test_handle_whatsapp_update_audio(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", AsyncMock())

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _make_mock_session("audio/ogg; codecs=opus", b"fake_audio_bytes"))

    payload = _media_payload("audio")
    await handle_whatsapp_update(payload, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text=None,
        audio_bytes=b"fake_audio_bytes",
        mime_type="audio/ogg; codecs=opus",
        channel="whatsapp",
        channel_user_id="911234567890"
    )


@pytest.mark.asyncio
async def test_handle_whatsapp_update_image(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", AsyncMock())

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _make_mock_session("image/jpeg", b"fake_image_bytes"))

    payload = _media_payload("image")
    await handle_whatsapp_update(payload, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text=None,
        audio_bytes=b"fake_image_bytes",
        mime_type="image/jpeg",
        channel="whatsapp",
        channel_user_id="911234567890"
    )
