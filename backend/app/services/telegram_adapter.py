import logging
import os
import aiohttp
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

async def handle_telegram_update(update: Dict[str, Any], db: AsyncSession) -> None:
    """
    Verifies a Telegram update, extracts chat_id + text or voice file_id,
    downloads voice via Telegram's getFile, calls ingestion_service,
    and replies via sendMessage with the tracking id.
    """
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set, cannot handle Telegram message")
        return
        
    text = message.get("text")
    voice = message.get("voice")
    photo = message.get("photo")

    # Telegram auto-sends "/start" (and users can send any other bot
    # command) the moment someone opens the bot -- without this, that text
    # was going straight into ingest_citizen_message as if it were a real
    # citizen report. Reproduced live: report id 91's translated_text is
    # literally "No report provided." because Gemini was handed "/start"
    # and did its best with it.
    if text and text.startswith("/"):
        command = text.split()[0].split("@")[0]
        if command == "/start":
            await _send_telegram_message(
                chat_id,
                "Welcome to Sangam. Send a text message, voice note, or photo describing "
                "an infrastructure issue (potholes, water supply, garbage, power, etc.) "
                "and your local ward or area name, and we'll log it.",
                bot_token,
            )
        else:
            await _send_telegram_message(
                chat_id,
                "Send a text message, voice note, or photo describing the infrastructure "
                "issue you'd like to report.",
                bot_token,
            )
        return

    audio_bytes = None
    mime_type = None
    
    file_id = None
    if voice:
        file_id = voice.get("file_id")
        mime_type = voice.get("mime_type", "audio/ogg")
    elif photo and isinstance(photo, list) and len(photo) > 0:
        file_id = photo[-1].get("file_id")
        mime_type = "image/jpeg"
        
    if file_id:
        # Download media file
        try:
            async with aiohttp.ClientSession() as session:
                # Get file info
                file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
                async with session.get(file_info_url) as resp:
                    if resp.status == 200:
                        file_data = await resp.json()
                        file_path = file_data.get("result", {}).get("file_path")
                        
                        if file_path:
                            # Download actual file
                            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                            async with session.get(download_url) as down_resp:
                                if down_resp.status == 200:
                                    audio_bytes = await down_resp.read()
        except Exception as e:
            logger.error(f"Failed to download Telegram media: {e}")
            await _send_telegram_message(chat_id, "Sorry, I couldn't download your media. Please try again or send a text message.", bot_token)
            return

    # Check for pending intake first
    channel_user_hash = hash_channel_user(str(chat_id))
    stmt = select(PendingIntake).where(
        PendingIntake.channel_user_hash == channel_user_hash,
        PendingIntake.expires_at > datetime.utcnow()
    )
    db_result = await db.execute(stmt)
    pending = db_result.scalar_one_or_none()
    
    if pending and pending.awaiting == "location" and text:
        try:
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

                await _send_telegram_message(chat_id, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", bot_token)
                return
            elif report_id:
                await db.commit()
                r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                r = r_res.scalar_one_or_none()
                tracking_id = r.tracking_id if r else "Unknown"

                # Don't discard this message here. A reply that fails to match
                # a known place name is far more often unrelated new content
                # -- another report, a question, anything -- than a genuine
                # failed location guess (reproduced live: a real new report
                # sent right after a location prompt was being silently
                # thrown away here, attributed to the *previous* report's
                # tracking ID with no trace of its own text ever existing).
                # Tell the citizen what happened to the earlier report, then
                # fall through to the normal ingestion path below so this
                # message gets its own tracking ID instead of vanishing.
                await _send_telegram_message(
                    chat_id,
                    f"We couldn't find that as a location for your previous report (Tracking ID: {tracking_id}) -- "
                    "it's saved without one. Treating this message as a new report...",
                    bot_token
                )
        except Exception as e:
            # This whole block used to be unguarded -- any failure here
            # (a DB error, resolve_location throwing, anything) propagated
            # past webhooks.py's own try/except, which only logs and
            # returns 200 to Telegram, leaving the citizen with *no reply
            # at all*. Reproduced live: a message sent right after this
            # exact flow got total silence, not even the generic error
            # message every other path already had.
            logger.error(f"Error resolving pending location intake: {e}")
            await db.rollback()
            await _send_telegram_message(chat_id, "Sorry, there was an error processing your report. Please try again later.", bot_token)
            return

    if not text and not audio_bytes:
        await _send_telegram_message(chat_id, "Please send a text message, a voice note, or a photo describing the infrastructure issue.", bot_token)
        return

    try:
        # Ingest
        result = await ingest_citizen_message(
            db=db,
            text=text,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            channel="telegram",
            channel_user_id=str(chat_id)
        )
        
        tracking_id = result["tracking_id"]
        if result.get("needs_location_followup"):
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}), but we couldn't detect a specific location. Could you please reply with the name of the ward, block, or district this relates to?"
        else:
            reply_text = f"Thank you. Your report has been securely received.\n\nTracking ID: {tracking_id}\n\nYou can use this tracking ID to check the status of your report."
            
        await _send_telegram_message(chat_id, reply_text, bot_token)
    except Exception as e:
        logger.error(f"Error processing Telegram report: {e}")
        await _send_telegram_message(chat_id, "Sorry, there was an error processing your report. Please try again later.", bot_token)

async def _send_telegram_message(chat_id: int, text: str, bot_token: str) -> None:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text
            }
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to send Telegram reply. Status: {resp.status}")
    except Exception as e:
        logger.error(f"Exception sending Telegram reply: {e}")
