"""WhatsApp (Meta Cloud API) adapter: webhook JSON ⇄ Inbound, signature check, reply."""

import hashlib
import hmac
import logging

import httpx

from app.core.config import get_settings
from app.core.messaging import GRAPH
from app.core.messaging import send_whatsapp_text as send  # noqa: F401  (the router replies through this)
from app.features.intake.service import Inbound

log = logging.getLogger(__name__)


def signature_valid(raw_body: bytes, header: str | None) -> bool:
    """Meta signs every POST with HMAC-SHA256 of the raw body, keyed by the app secret."""
    secret = get_settings().WHATSAPP_APP_SECRET
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def parse_payload(payload: dict) -> list[tuple[str, Inbound]]:
    """Returns (phone_number, message) for every citizen message in the webhook."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                sender = message.get("from")
                if not sender:
                    continue
                inbound = Inbound(channel="whatsapp", sender_id=sender, reply_to=sender)
                kind = message.get("type")
                if kind == "text":
                    inbound.text = message["text"].get("body")
                elif kind == "location":
                    inbound.lat, inbound.lon = message["location"]["latitude"], message["location"]["longitude"]
                elif kind in ("audio", "image"):
                    media = message[kind]
                    inbound.media, inbound.mime_type = _download(media["id"])
                    inbound.text = media.get("caption")
                else:
                    continue
                out.append((sender, inbound))
    return out


def _download(media_id: str) -> tuple[bytes | None, str | None]:
    headers = {"Authorization": f"Bearer {get_settings().WHATSAPP_ACCESS_TOKEN}"}
    try:
        meta = httpx.get(f"{GRAPH}/{media_id}", headers=headers, timeout=15).json()
        data = httpx.get(meta["url"], headers=headers, timeout=30).content
        return data, (meta.get("mime_type") or "").split(";")[0] or None
    except Exception as exc:
        log.error("WhatsApp media download failed: %s", exc)
        return None, None

