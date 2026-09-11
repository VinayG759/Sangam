import os
import sys
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion_service import ingest_citizen_message
from app.services.telegram_adapter import handle_telegram_update
from app.services.whatsapp_adapter import handle_whatsapp_update
from app.utils.validate_pack import validate_pack, main as validator_main


@pytest.mark.asyncio
async def test_ingest_citizen_message_rejects_media_over_10mb(monkeypatch):
    """
    Assert that a media payload >10 MB is rejected with a friendly message
    and without calling Gemini.
    """
    mock_session = AsyncMock()

    mock_gemini = MagicMock()
    mock_gemini.analyze_citizen_report.side_effect = AssertionError("Gemini must NOT be called for oversize media!")
    import app.services.ingestion_service as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "gemini_service", mock_gemini)

    # 10 MB + 1 byte
    oversize_bytes = b"0" * (10 * 1024 * 1024 + 1)

    result = await ingest_citizen_message(
        db=mock_session,
        audio_bytes=oversize_bytes,
        mime_type="audio/ogg",
        channel="web"
    )

    assert result["status"] == "rejected"
    assert "maximum size is 10 MB" in result["message"]
    assert result["report_id"] is None
    mock_gemini.analyze_citizen_report.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_adapter_rejects_reported_file_size_over_10mb(monkeypatch):
    """
    Assert that Telegram updates declaring file_size > 10MB are rejected immediately
    without downloading or calling Gemini.
    """
    mock_session = AsyncMock()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")

    mock_send = AsyncMock()
    import app.services.telegram_adapter as tg_mod
    monkeypatch.setattr(tg_mod, "_send_telegram_message", mock_send)

    mock_ingest = AsyncMock()
    monkeypatch.setattr(tg_mod, "ingest_citizen_message", mock_ingest)

    payload = {
        "message": {
            "chat": {"id": 98765},
            "voice": {
                "file_id": "large_voice_file",
                "file_size": 11 * 1024 * 1024,  # 11 MB
                "mime_type": "audio/ogg"
            }
        }
    }

    await handle_telegram_update(payload, mock_session)

    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "maximum size is 10 MB" in sent_text
    mock_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_whatsapp_adapter_rejects_downloaded_media_over_10mb(monkeypatch):
    """
    Assert that WhatsApp adapter rejects media exceeding 10MB after download.
    """
    mock_session = AsyncMock()
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "test_phone_id")

    mock_send = AsyncMock()
    import app.services.whatsapp_adapter as wa_mod
    monkeypatch.setattr(wa_mod, "_send_whatsapp_message", mock_send)

    # Mock download returning 10.5 MB
    large_bytes = b"A" * int(10.5 * 1024 * 1024)
    monkeypatch.setattr(wa_mod, "_download_meta_media", AsyncMock(return_value=(large_bytes, "audio/ogg")))

    mock_ingest = AsyncMock()
    monkeypatch.setattr(wa_mod, "ingest_citizen_message", mock_ingest)

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919876543210",
                        "type": "audio",
                        "audio": {"id": "media_large_123"}
                    }]
                }
            }]
        }]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "maximum size is 10 MB" in sent_text
    mock_ingest.assert_not_called()


def test_pack_validator_passes_on_real_pack():
    """
    Assert that validate_pack passes cleanly on the actual india_karnataka pack.
    """
    is_valid, msg = validate_pack("india_karnataka")
    assert is_valid is True
    assert "[PASS]" in msg
    assert "IND (Karnataka)" in msg
    assert "water" in msg


def test_pack_validator_fails_on_broken_pack(tmp_path):
    """
    Assert that validate_pack fails clearly on a pack missing required fields or with invalid weights.
    """
    broken_pack_dir = tmp_path / "broken_pack"
    broken_pack_dir.mkdir()
    broken_yaml = broken_pack_dir / "pack.yaml"

    # Missing sectors and invalid weight value (> 1.0)
    broken_data = {
        "country_code": "BAD",
        "region_name": "Broken Region",
        "languages": [{"code": "en", "name": "English"}],
        "weights": {
            "demand_density": 1.5,  # Invalid: must be <= 1.0
            "vulnerability_index": 0.5,
            "expenditure_gap": 0.0,
            "urgency": 0.0
        }
    }
    with open(broken_yaml, "w", encoding="utf-8") as f:
        yaml.dump(broken_data, f)

    is_valid, msg = validate_pack(str(broken_pack_dir))
    assert is_valid is False
    assert "[FAIL]" in msg


def test_pack_validator_cli_main(monkeypatch):
    """
    Assert that running the CLI main function exits 0 on valid pack and 1 on broken target.
    """
    monkeypatch.setattr(sys, "argv", ["validate_pack", "india_karnataka"])
    ret_code = validator_main()
    assert ret_code == 0

    monkeypatch.setattr(sys, "argv", ["validate_pack", "non_existent_pack_xyz"])
    ret_code_bad = validator_main()
    assert ret_code_bad == 1
