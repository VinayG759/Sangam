"""
Sending a message to a citizen on a channel. Shared by intake (replies) and
notify (status updates). Every function returns True only if the channel
accepted the message.
"""

import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org"
GRAPH = "https://graph.facebook.com/v20.0"


def send_telegram(chat_id: int | str, text: str) -> bool:
    token = get_settings().TELEGRAM_BOT_TOKEN
    try:
        response = httpx.post(f"{TELEGRAM_API}/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text},
                              timeout=15)
        return response.status_code == 200
    except Exception as exc:
        log.error("Telegram send failed: %s", exc)
        return False


def _whatsapp(payload: dict) -> bool:
    settings = get_settings()
    try:
        response = httpx.post(f"{GRAPH}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                              headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                              json={"messaging_product": "whatsapp", **payload}, timeout=15)
        return response.status_code in (200, 201)
    except Exception as exc:
        log.error("WhatsApp send failed: %s", exc)
        return False


def send_whatsapp_text(to: str, text: str) -> bool:
    """Free text. Only delivered within 24 hours of the citizen's last message."""
    return _whatsapp({"to": to, "type": "text", "text": {"body": text}})


def send_whatsapp_template(to: str, template: str, language: str, parameters: list[str]) -> bool:
    """A Meta-approved template: the only way to message a citizen after the 24-hour window."""
    return _whatsapp({"to": to, "type": "template", "template": {
        "name": template, "language": {"code": language},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}],
    }})
