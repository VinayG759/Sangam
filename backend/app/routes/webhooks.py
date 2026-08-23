from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.telegram_adapter import handle_telegram_update
from app.services.whatsapp_adapter import handle_whatsapp_update, verify_twilio_signature
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

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook endpoint for Twilio WhatsApp updates.
    Verifies signature and returns empty 200 OK to prevent retries.
    """
    try:
        form_data = await request.form()
        form_dict = dict(form_data)
        
        signature = request.headers.get("X-Twilio-Signature", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

        # Twilio signs the external URL it actually called (https://yourdomain/...).
        # Behind any reverse proxy or PaaS that terminates TLS and forwards
        # internally as plain HTTP -- Render, Railway, and most standard
        # deployments -- request.url reports the internal scheme/host, not
        # the external one Twilio hashed, so a naive comparison would reject
        # every legitimate request. Reconstruct the external URL from the
        # X-Forwarded-* headers those proxies set, falling back to
        # request.url only when they're absent (e.g. local testing).
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
        external_url = f"{proto}://{host}{request.url.path}"
        if request.url.query:
            external_url += f"?{request.url.query}"

        is_valid = verify_twilio_signature(external_url, form_dict, auth_token, signature)
        
        if not is_valid:
            logger.warning("Invalid Twilio signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
            
        await handle_whatsapp_update(form_dict, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}")
        
    return Response(status_code=200)
