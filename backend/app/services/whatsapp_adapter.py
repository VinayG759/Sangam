import logging
import os
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from app.services.ingestion_service import ingest_citizen_message
from app.models.models import PendingIntake, CitizenReport
from app.utils.hashing import hash_channel_user
from app.services.location_resolver import resolve_location, resolve_gps_location
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

    latitude = None
    longitude = None
    if msg_type == "location":
        loc_data = message.get("location", {})
        latitude = float(loc_data["latitude"]) if "latitude" in loc_data else None
        longitude = float(loc_data["longitude"]) if "longitude" in loc_data else None

    audio_bytes = None
    mime_type = None

    media_id = None
    if msg_type == "audio":
        media_id = message.get("audio", {}).get("id")
    elif msg_type == "image":
        media_id = message.get("image", {}).get("id")

    MAX_MEDIA_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    if media_id:
        try:
            audio_bytes, mime_type = await _download_meta_media(media_id, access_token)
        except Exception as e:
            logger.error(f"Failed to download WhatsApp media: {e}")
            audio_bytes = None
        if audio_bytes is None:
            await _send_whatsapp_message(from_number, "Sorry, I couldn't download your media. Please try again or send a text message.", access_token, phone_number_id)
            return

        if len(audio_bytes) > MAX_MEDIA_SIZE_BYTES:
            await _send_whatsapp_message(
                from_number,
                "The media file is too large (maximum size is 10 MB). Please send a shorter voice note or smaller image.",
                access_token,
                phone_number_id
            )
            return

    # Check for pending intake first
    channel_user_hash = hash_channel_user(from_number)
    stmt = select(PendingIntake).where(
        PendingIntake.channel_user_hash == channel_user_hash,
        PendingIntake.expires_at > datetime.utcnow()
    )
    db_result = await db.execute(stmt)
    pending = db_result.scalar_one_or_none()

    if pending and pending.awaiting in ("location", "location_confirmation"):
        try:
            report_id = pending.partial_report.get("report_id") if isinstance(pending.partial_report, dict) else None

            def _get_tracking_id(r_obj=None):
                if isinstance(pending.partial_report, dict) and pending.partial_report.get("tracking_id"):
                    return pending.partial_report["tracking_id"]
                if r_obj and hasattr(r_obj, "tracking_id") and r_obj.tracking_id:
                    return r_obj.tracking_id
                return "Unknown"

            # Case A: user sent GPS coordinates to resolve/update location.
            # Resolved to a region immediately (nearest centroid) rather
            # than just storing the raw point and leaving region_id null --
            # clustering_engine.py's own spatial fallback needs
            # AdminRegion.geom, which isn't populated for Karnataka data,
            # so it would otherwise silently attribute this to an arbitrary
            # ward instead of the citizen's real location.
            if latitude is not None and longitude is not None:
                await db.delete(pending)
                if report_id:
                    location_wkt = f"SRID=4326;POINT({longitude} {latitude})"
                    gps_region = await resolve_gps_location(
                        latitude, longitude, pack_loader.load_active_pack().country_code, db
                    )
                    await db.execute(
                        sa_update(CitizenReport)
                        .where(CitizenReport.id == report_id)
                        .values(location=location_wkt, region_id=gps_region.id if gps_region else CitizenReport.region_id)
                    )
                    await db.commit()
                    r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                    r = r_res.scalar_one_or_none()
                    tracking_id = _get_tracking_id(r)
                    await _send_whatsapp_message(from_number, f"Location updated successfully with GPS coordinates. Thank you. Tracking ID: {tracking_id}", access_token, phone_number_id)
                    return

            # Case B: confirmation of a candidate location
            if pending.awaiting == "location_confirmation":
                candidate_id = pending.partial_report.get("candidate_region_id") if isinstance(pending.partial_report, dict) else None
                candidate_name = pending.partial_report.get("candidate_region_name") if isinstance(pending.partial_report, dict) else None
                AFFIRMATIVE_RESPONSES = {"yes", "y", "haudu", "sari", "correct", "true", "ok", "okay", "confirm", "right", "sure"}
                clean_text = text.strip().lower() if text else ""

                if clean_text in AFFIRMATIVE_RESPONSES and candidate_id and report_id:
                    await db.delete(pending)
                    await db.execute(
                        sa_update(CitizenReport)
                        .where(CitizenReport.id == report_id)
                        .values(region_id=candidate_id)
                    )
                    await db.commit()
                    r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                    r = r_res.scalar_one_or_none()
                    tracking_id = _get_tracking_id(r)
                    await _send_whatsapp_message(from_number, f"Location confirmed as {candidate_name}. Thank you. Tracking ID: {tracking_id}", access_token, phone_number_id)
                    return
                else:
                    # User replied with something other than yes - try to resolve as a new location name
                    region = await resolve_location(
                        text,
                        pack_loader.load_active_pack().country_code,
                        db
                    ) if text else None

                    await db.delete(pending)
                    if region and report_id:
                        await db.execute(
                            sa_update(CitizenReport)
                            .where(CitizenReport.id == report_id)
                            .values(region_id=region.id)
                        )
                        await db.commit()
                        r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                        r = r_res.scalar_one_or_none()
                        tracking_id = _get_tracking_id(r)
                        await _send_whatsapp_message(from_number, f"Location updated successfully to {region.name}. Thank you. Tracking ID: {tracking_id}", access_token, phone_number_id)
                        return
                    elif report_id:
                        await db.commit()
                        r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                        r = r_res.scalar_one_or_none()
                        tracking_id = _get_tracking_id(r)
                        await _send_whatsapp_message(
                            from_number,
                            f"We couldn't find that as a location for your previous report (Tracking ID: {tracking_id}) -- "
                            "it's saved without one. Treating this message as a new report...",
                            access_token, phone_number_id
                        )
            else:
                # Case C: awaiting = "location"
                region = await resolve_location(
                    text,
                    pack_loader.load_active_pack().country_code,
                    db
                ) if text else None

                # We always delete the pending state after one try
                await db.delete(pending)

                if region and report_id:
                    await db.execute(
                        sa_update(CitizenReport)
                        .where(CitizenReport.id == report_id)
                        .values(region_id=region.id)
                    )
                    await db.commit()

                    r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                    r = r_res.scalar_one_or_none()
                    tracking_id = _get_tracking_id(r)

                    await _send_whatsapp_message(from_number, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", access_token, phone_number_id)
                    return
                elif report_id:
                    await db.commit()
                    r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                    r = r_res.scalar_one_or_none()
                    tracking_id = _get_tracking_id(r)

                    await _send_whatsapp_message(
                        from_number,
                        f"We couldn't find that as a location for your previous report (Tracking ID: {tracking_id}) -- "
                        "it's saved without one. Treating this message as a new report...",
                        access_token, phone_number_id
                    )
        except Exception as e:
            logger.error(f"Error resolving pending location intake: {e}")
            await db.rollback()
            await _send_whatsapp_message(from_number, "Sorry, there was an error processing your report. Please try again later.", access_token, phone_number_id)
            return

    if not text and not audio_bytes and latitude is None:
        await _send_whatsapp_message(from_number, "Please send a text message, a voice note, a photo, or share your location describing the infrastructure issue.", access_token, phone_number_id)
        return

    # A bare location share with no accompanying text/voice/photo and no
    # pending report to attach it to (handled above and already returned)
    # has nothing for Gemini to analyze -- sending it through anyway wastes
    # a real, rate-limited Gemini call and creates a low-quality report
    # with no actual complaint content.
    if latitude is not None and not text and not audio_bytes:
        await _send_whatsapp_message(
            from_number,
            "Thanks for sharing your location. Please also send a text message, voice note, or photo describing the infrastructure issue.",
            access_token, phone_number_id
        )
        return

    try:
        # Ingest
        ingest_kwargs = {
            "db": db,
            "text": text if text else None,
            "audio_bytes": audio_bytes,
            "mime_type": mime_type,
            "channel": "whatsapp",
            "channel_user_id": from_number
        }
        if latitude is not None and longitude is not None:
            ingest_kwargs["latitude"] = latitude
            ingest_kwargs["longitude"] = longitude

        result = await ingest_citizen_message(**ingest_kwargs)

        if result.get("status") in ("rejected", "rate_limited"):
            reply_text = result.get("message") or "Maximum reports for today reached. Please try again tomorrow."
            await _send_whatsapp_message(from_number, reply_text, access_token, phone_number_id)
            return

        tracking_id = result["tracking_id"]
        if result.get("needs_location_confirmation"):
            candidate = result.get("candidate_region_name") or "detected area"
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}). We detected your location as {candidate}. Reply 'yes' to confirm, or reply with your ward, block, or district name (or share your GPS location)."
        elif result.get("needs_location_followup"):
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}), but we couldn't detect a specific location. Could you please reply with the name of the ward, block, or district this relates to (or share your GPS location)?"
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
