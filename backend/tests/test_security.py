"""Secrets and personal data stay out of logs; public endpoints are rate-limited."""

import hashlib
import hmac
import json
import logging


def test_http_client_request_urls_are_not_logged():
    # Telegram's API URLs contain the bot token; the HTTP client logs URLs at INFO.
    import app.main  # noqa: F401  (configures logging)

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_phone_numbers_and_bot_tokens_never_reach_the_logs(client, ai, loaded, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr("app.features.intake.whatsapp.send", lambda to, text: True)
    monkeypatch.setattr("app.features.intake.telegram.send", lambda chat, text: True)
    ai.places = ["Southmere"]

    phone = "919845012345"
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"from": phone, "type": "text", "text": {"body": f"No water in Southmere, call me on +{phone}"}}]}}]}]}).encode()
    signature = "sha256=" + hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    client.post("/api/v1/webhooks/whatsapp", content=body,
                headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
    client.post("/api/v1/webhooks/telegram", json={"message": {"chat": {"id": 555123}, "from": {"id": 555123},
                                                               "text": "No water in Southmere"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "test-telegram-secret"})

    assert phone not in caplog.text
    assert "555123" not in caplog.text
    assert "test-bot-token" not in caplog.text


def test_failed_telegram_send_does_not_log_the_token(monkeypatch, caplog):
    import httpx

    from app.core.messaging import send_telegram

    def refuse(url, **kwargs):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", refuse)
    caplog.set_level(logging.DEBUG)
    assert send_telegram(1, "hello") is False
    assert "test-bot-token" not in caplog.text


def test_tracking_lookups_are_rate_limited(client, loaded):
    codes = [client.get("/api/v1/track/SG-NOPE00").status_code for _ in range(31)]
    assert codes[:30] == [404] * 30 and codes[30] == 429
