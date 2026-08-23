import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.whatsapp_adapter import handle_whatsapp_update, verify_twilio_signature
from app.models.models import PendingIntake

def test_verify_twilio_signature():
    url = "https://example.com/api/v1/webhooks/whatsapp"
    params = {
        "From": "whatsapp:+1234567890",
        "Body": "Test message"
    }
    auth_token = "test_auth_token"
    
    # Compute the expected signature manually
    import hmac, hashlib, base64
    data = url + "BodyTest messageFromwhatsapp:+1234567890"
    mac = hmac.new(auth_token.encode('utf-8'), data.encode('utf-8'), hashlib.sha1)
    valid_sig = base64.b64encode(mac.digest()).decode('utf-8')
    
    assert verify_twilio_signature(url, params, auth_token, valid_sig) == True
    assert verify_twilio_signature(url, params, auth_token, "invalid_sig") == False
    assert verify_twilio_signature(url, params, "wrong_token", valid_sig) == False
    
    tampered_params = params.copy()
    tampered_params["Body"] = "Tampered message"
    assert verify_twilio_signature(url, tampered_params, auth_token, valid_sig) == False

@pytest.mark.asyncio
async def test_handle_whatsapp_update_text(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    form_data = {
        "From": "whatsapp:+1234567890",
        "Body": "Hello world",
        "NumMedia": "0"
    }

    await handle_whatsapp_update(form_data, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text="Hello world",
        audio_bytes=None,
        mime_type=None,
        channel="whatsapp",
        channel_user_id="whatsapp:+1234567890"
    )

    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert args[0] == "whatsapp:+1234567890"
    assert "SNG-TEST" in args[1]
    assert args[2] == "test_sid"
    assert args[3] == "test_token"
    assert args[4] == "whatsapp:+14155238886"

@pytest.mark.asyncio
async def test_handle_whatsapp_update_media(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    form_data = {
        "From": "whatsapp:+1234567890",
        "Body": "",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/123",
        "MediaContentType0": "audio/ogg"
    }

    class MockResponse:
        status = 200
        async def read(self):
            return b"fake_audio_bytes"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockClientSession:
        def __init__(self, auth=None):
            self.auth = auth
        def get(self, url):
            assert url == "https://api.twilio.com/media/123"
            return MockResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", MockClientSession)

    await handle_whatsapp_update(form_data, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text=None,
        audio_bytes=b"fake_audio_bytes",
        mime_type="audio/ogg",
        channel="whatsapp",
        channel_user_id="whatsapp:+1234567890"
    )

@pytest.mark.asyncio
async def test_handle_whatsapp_update_image(monkeypatch):
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = db_result

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-TEST"})
    import app.services.whatsapp_adapter as whatsapp_module
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)

    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    form_data = {
        "From": "whatsapp:+1234567890",
        "Body": "",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/123",
        "MediaContentType0": "image/jpeg"
    }

    class MockResponse:
        status = 200
        async def read(self):
            return b"fake_image_bytes"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockClientSession:
        def __init__(self, auth=None):
            self.auth = auth
        def get(self, url):
            assert url == "https://api.twilio.com/media/123"
            return MockResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", MockClientSession)

    await handle_whatsapp_update(form_data, mock_session)

    mock_ingest.assert_called_once_with(
        db=mock_session,
        text=None,
        audio_bytes=b"fake_image_bytes",
        mime_type="image/jpeg",
        channel="whatsapp",
        channel_user_id="whatsapp:+1234567890"
    )

