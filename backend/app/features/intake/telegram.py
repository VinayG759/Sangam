"""Telegram adapter: Telegram update JSON ⇄ Inbound, and sending the reply."""

import logging

import httpx

from app.core.config import get_settings
from app.features.intake.service import Inbound

log = logging.getLogger(__name__)
API = "https://api.telegram.org"
WELCOME = ("Namaskara! Tell us about a problem with water, roads, electricity, health, schools or sanitation "
           "in your area. Send a voice note, a photo or a message in your own language, and say where it is.")


def parse_update(update: dict) -> tuple[int, Inbound] | None:
    """Returns (chat_id, message), or None for updates Sangam ignores."""
    message = update.get("message") or update.get("edited_message")
    if not message or "chat" not in message:
        return None
    chat_id = message["chat"]["id"]
    sender = str((message.get("from") or {}).get("id", chat_id))
    inbound = Inbound(channel="telegram", sender_id=sender, text=message.get("text") or message.get("caption"))
    if location := message.get("location"):
        inbound.lat, inbound.lon = location["latitude"], location["longitude"]
    if voice := (message.get("voice") or message.get("audio")):
        inbound.media, inbound.mime_type = _download(voice["file_id"]), voice.get("mime_type", "audio/ogg")
    elif photos := message.get("photo"):
        inbound.media, inbound.mime_type = _download(photos[-1]["file_id"]), "image/jpeg"
    return chat_id, inbound


def _download(file_id: str) -> bytes | None:
    token = get_settings().TELEGRAM_BOT_TOKEN
    try:
        info = httpx.get(f"{API}/bot{token}/getFile", params={"file_id": file_id}, timeout=15).json()
        path = info["result"]["file_path"]
        return httpx.get(f"{API}/file/bot{token}/{path}", timeout=30).content
    except Exception as exc:
        log.error("Telegram media download failed: %s", exc)
        return None


def send(chat_id: int, text: str) -> None:
    token = get_settings().TELEGRAM_BOT_TOKEN
    try:
        httpx.post(f"{API}/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception as exc:
        log.error("Telegram send failed: %s", exc)
