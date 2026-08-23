from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.telegram_adapter import handle_telegram_update
from app.services.whatsapp_adapter import handle_whatsapp_update, verify_meta_signature
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

@router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook endpoint for Telegram bot updates.
    Returns 200 immediately to prevent Telegram retries.
    """
    try:
        update = await request.json()
        await handle_telegram_update(update, db)
    except Exception as e:
        logger.error(f"Error handling Telegram webhook: {e}")
    # Always return 200 ok to telegram
    return {"status": "ok"}

@router.get("/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    Meta calls this once, as a GET, when you configure the webhook URL in
    the App dashboard -- it must echo back hub.challenge if hub.verify_token
    matches what you configured there, proving you control this endpoint
    before Meta will ever POST real message traffic to it.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")

    expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected_token and token == expected_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook endpoint for Meta WhatsApp Cloud API updates. Verifies
    X-Hub-Signature-256 (HMAC-SHA256 of the raw body, keyed with the app
    secret -- no reverse-proxy URL reconstruction needed, unlike Twilio's
    URL-based signature) and returns 200 immediately to prevent retries.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    app_secret = os.environ.get("WHATSAPP_APP_SECRET", "")

    if not verify_meta_signature(raw_body, signature, app_secret):
        logger.warning("Invalid WhatsApp webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = await request.json()
        await handle_whatsapp_update(payload, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}")

    return Response(status_code=200)
