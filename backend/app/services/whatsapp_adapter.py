import logging
import os
import aiohttp
import hmac
import hashlib
import base64
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.services.ingestion_service import ingest_citizen_message
from app.models.models import PendingIntake, CitizenReport
from app.utils.hashing import hash_channel_user
from app.services.location_resolver import resolve_location
from app.services.pack_loader import pack_loader

logger = logging.getLogger(__name__)

def verify_twilio_signature(url: str, params: Dict[str, str], auth_token: str, signature: str) -> bool:
    """Verifies a Twilio webhook signature."""
    if not auth_token or not signature:
        return False
    
    # Sort params by key
    sorted_params = sorted(params.items())
    
    # Append to URL
    data = url
    for k, v in sorted_params:
        data += f"{k}{v}"
    
    # Compute HMAC-SHA1
    mac = hmac.new(auth_token.encode('utf-8'), data.encode('utf-8'), hashlib.sha1)
    computed = base64.b64encode(mac.digest()).decode('utf-8')
    
    return hmac.compare_digest(computed, signature)

async def handle_whatsapp_update(form_data: Dict[str, str], db: AsyncSession) -> None:
    """
    Extracts From + text or MediaUrl0, downloads media via Twilio REST API,
    calls ingestion_service, and replies via Messages.json.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_from = os.environ.get("TWILIO_WHATSAPP_FROM")
    
    if not account_sid or not auth_token or not twilio_from:
        logger.error("Twilio credentials not set, cannot handle WhatsApp message")
        return

    from_number = form_data.get("From")
    if not from_number:
        return

    text = form_data.get("Body", "")
    num_media = int(form_data.get("NumMedia", "0"))
    
    audio_bytes = None
    mime_type = None
    
    if num_media > 0:
        media_url = form_data.get("MediaUrl0")
        mime_type = form_data.get("MediaContentType0", "audio/ogg")
        
        if media_url:
            if not mime_type.startswith("audio/") and not mime_type.startswith("image/"):
                await _send_whatsapp_message(from_number, "Please send a text message, a voice note, or a photo.", account_sid, auth_token, twilio_from)
                return
                
            try:
                auth = aiohttp.BasicAuth(account_sid, auth_token)
                async with aiohttp.ClientSession(auth=auth) as session:
                    async with session.get(media_url) as resp:
                        if resp.status == 200:
                            audio_bytes = await resp.read()
                        else:
                            logger.error(f"Failed to download Twilio media. Status: {resp.status}")
            except Exception as e:
                logger.error(f"Failed to download Twilio media: {e}")
                await _send_whatsapp_message(from_number, "Sorry, I couldn't download your media. Please try again or send a text message.", account_sid, auth_token, twilio_from)
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
        # Resolve location
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
            
            await _send_whatsapp_message(from_number, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", account_sid, auth_token, twilio_from)
            return
        elif report_id:
            await db.commit()
            r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
            r = r_res.scalar_one_or_none()
            tracking_id = r.tracking_id if r else "Unknown"
            
            await _send_whatsapp_message(from_number, f"We couldn't precisely locate that place, but your report is saved. Tracking ID: {tracking_id}", account_sid, auth_token, twilio_from)
            return

    if not text and not audio_bytes:
        await _send_whatsapp_message(from_number, "Please send a text message, a voice note, or a photo describing the infrastructure issue.", account_sid, auth_token, twilio_from)
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
            
        await _send_whatsapp_message(from_number, reply_text, account_sid, auth_token, twilio_from)
    except Exception as e:
        logger.error(f"Error processing WhatsApp report: {e}")
        await _send_whatsapp_message(from_number, "Sorry, there was an error processing your report. Please try again later.", account_sid, auth_token, twilio_from)

async def _send_whatsapp_message(to_number: str, text: str, account_sid: str, auth_token: str, from_number: str) -> None:
    try:
        auth = aiohttp.BasicAuth(account_sid, auth_token)
        async with aiohttp.ClientSession(auth=auth) as session:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            payload = {
                "From": from_number,
                "To": to_number,
                "Body": text
            }
            async with session.post(url, data=payload) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Failed to send WhatsApp reply. Status: {resp.status}")
    except Exception as e:
        logger.error(f"Exception sending WhatsApp reply: {e}")
