import logging
import os
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.services.ingestion_service import ingest_citizen_message
from app.models.models import PendingIntake, CitizenReport
from app.utils.hashing import hash_channel_user
from app.services.location_resolver import resolve_location
from app.services.pack_loader import pack_loader

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v20.0"


def verify_meta_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Verifies Meta's X-Hub-Signature-256 header: HMAC-SHA256 of the raw
    request body, keyed with the WhatsApp app's secret. Unlike Twilio's
    scheme (which signs a reconstructed URL + sorted form params), this
    signs the body directly, so no reverse-proxy URL reconstruction is
    needed here.
    """
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256="):]
    mac = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256)
    computed = mac.hexdigest()
    return hmac.compare_digest(computed, expected)


def extract_message(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Meta wraps every webhook event in entry[].changes[].value -- and the
    same webhook subscription also fires for delivery/read status updates
    (value.statuses instead of value.messages), which callers must ignore
    rather than error on. Returns the first inbound message dict, or None
    if this event has no message (a status callback, or a malformed body).
    """
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages")
        if not messages:
            return None
        return messages[0]
    except (IndexError, AttributeError, TypeError):
        return None


async def handle_whatsapp_update(payload: Dict[str, Any], db: AsyncSession) -> None:
    """
    Extracts the sender + text or media id from a Meta WhatsApp Cloud API
    webhook payload, downloads media via the Graph API, calls
    ingestion_service, and replies via the Graph API messages endpoint.
    """
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    if not access_token or not phone_number_id:
        logger.error("WhatsApp Cloud API credentials not set, cannot handle WhatsApp message")
        return

    message = extract_message(payload)
    if not message:
        # Delivery/read status callbacks land here too; nothing to do.
        return

    from_number = message.get("from")
    if not from_number:
        return

    msg_type = message.get("type")
    text = message.get("text", {}).get("body") if msg_type == "text" else None

    audio_bytes = None
    mime_type = None

    media_id = None
    if msg_type == "audio":
        media_id = message.get("audio", {}).get("id")
    elif msg_type == "image":
        media_id = message.get("image", {}).get("id")

    if media_id:
        try:
            audio_bytes, mime_type = await _download_meta_media(media_id, access_token)
        except Exception as e:
            logger.error(f"Failed to download WhatsApp media: {e}")
            audio_bytes = None
        if audio_bytes is None:
            await _send_whatsapp_message(from_number, "Sorry, I couldn't download your media. Please try again or send a text message.", access_token, phone_number_id)
            return

    # Check for pending intake first
    channel_user_hash = hash_channel_user(from_number)
    stmt = select(PendingIntake).where(
        PendingIntake.channel_user_hash == channel_user_hash,
        PendingIntake.expires_at > datetime.utcnow()
    )
    db_result = await db.execute(stmt)
    pending = db_result.scalar_one_or_none()

    if pending and pending.awaiting == "location" and text:
        region = await resolve_location(
            text,
            pack_loader.load_active_pack().country_code,
            db
        )
        report_id = pending.partial_report.get("report_id")

        # We always delete the pending state after one try
        await db.delete(pending)

        if region and report_id:
            await db.execute(
                update(CitizenReport)
                .where(CitizenReport.id == report_id)
                .values(region_id=region.id)
            )
            await db.commit()

            r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
            r = r_res.scalar_one_or_none()
            tracking_id = r.tracking_id if r else "Unknown"

            await _send_whatsapp_message(from_number, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", access_token, phone_number_id)
            return
        elif report_id:
            await db.commit()
            r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
            r = r_res.scalar_one_or_none()
            tracking_id = r.tracking_id if r else "Unknown"

            await _send_whatsapp_message(from_number, f"We couldn't precisely locate that place, but your report is saved. Tracking ID: {tracking_id}", access_token, phone_number_id)
            return

    if not text and not audio_bytes:
        await _send_whatsapp_message(from_number, "Please send a text message, a voice note, or a photo describing the infrastructure issue.", access_token, phone_number_id)
        return

    try:
        # Ingest
        result = await ingest_citizen_message(
            db=db,
            text=text if text else None,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            channel="whatsapp",
            channel_user_id=from_number
        )

        tracking_id = result["tracking_id"]
        if result.get("needs_location_followup"):
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}), but we couldn't detect a specific location. Could you please reply with the name of the ward, block, or district this relates to?"
        else:
            reply_text = f"Thank you. Your report has been securely received.\n\nTracking ID: {tracking_id}\n\nYou can use this tracking ID to check the status of your report."

        await _send_whatsapp_message(from_number, reply_text, access_token, phone_number_id)
    except Exception as e:
        logger.error(f"Error processing WhatsApp report: {e}")
        await _send_whatsapp_message(from_number, "Sorry, there was an error processing your report. Please try again later.", access_token, phone_number_id)


async def _download_meta_media(media_id: str, access_token: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    The Cloud API gives a media id, not a direct URL like Twilio's stable
    MediaUrl0 -- the actual (short-lived) URL must be looked up first, and
    fetching it requires the same bearer token used for the lookup.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}") as resp:
            if resp.status != 200:
                logger.error(f"Failed to look up WhatsApp media URL. Status: {resp.status}")
                return None, None
            meta = await resp.json()

        media_url = meta.get("url")
        mime_type = meta.get("mime_type")
        if not media_url:
            return None, None

        async with session.get(media_url) as resp:
            if resp.status != 200:
                logger.error(f"Failed to download WhatsApp media. Status: {resp.status}")
                return None, None
            data = await resp.read()

        return data, mime_type


async def _send_whatsapp_message(to_number: str, text: str, access_token: str, phone_number_id: str) -> None:
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": text},
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
            async with session.post(url, json=payload) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Failed to send WhatsApp reply. Status: {resp.status}")
    except Exception as e:
        logger.error(f"Exception sending WhatsApp reply: {e}")
