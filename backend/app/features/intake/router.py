"""
Intake endpoints. Webhooks answer immediately (200) and do the work in the
background, so Telegram and Meta never time out and retry.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import AIClient, get_ai
from app.core.config import get_settings
from app.core.db import get_db, new_session
from app.core.limiter import limiter
from app.core.pack import Pack, get_pack
from app.core.runs import latest_complete_run
from app.core.security import require_admin, secrets_match
from app.features.intake import telegram, whatsapp
from app.features.intake.service import Inbound, handle_message, reprocess_pending
from app.models import Priority, Region, Report

log = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

telegram_router = APIRouter(prefix="/api/v1/webhooks", tags=["intake"])
whatsapp_router = APIRouter(prefix="/api/v1/webhooks", tags=["intake"])
web_router = APIRouter(prefix="/api/v1", tags=["intake"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── Telegram ─────────────────────────────────────────────────────────────────


def _process_telegram(update: dict, ai: AIClient, pack: Pack) -> None:
    parsed = telegram.parse_update(update)
    if not parsed:
        return
    chat_id, inbound = parsed
    if (inbound.text or "").strip().lower() in {"/start", "/help"}:
        telegram.send(chat_id, telegram.WELCOME)
        return
    with new_session() as db:
        try:
            outcome = handle_message(db, ai, pack, inbound)
        except Exception:
            log.exception("Telegram message failed")
            db.rollback()
            outcome = None
    telegram.send(chat_id, outcome.reply if outcome else "Sorry, something went wrong. Please try again.")


@telegram_router.post("/telegram")
async def telegram_webhook(request: Request, background: BackgroundTasks,
                           ai: AIClient = Depends(get_ai), pack: Pack = Depends(get_pack)):
    # Telegram includes the secret we registered with setWebhook; anything else is not Telegram.
    if not secrets_match(request.headers.get("X-Telegram-Bot-Api-Secret-Token"),
                         get_settings().TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    background.add_task(_process_telegram, await request.json(), ai, pack)
    return {"ok": True}


# ── WhatsApp ─────────────────────────────────────────────────────────────────


@whatsapp_router.get("/whatsapp")
def whatsapp_verify(request: Request):
    """Meta's one-time handshake when the webhook URL is configured."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and secrets_match(params.get("hub.verify_token"),
                                                               get_settings().WHATSAPP_VERIFY_TOKEN):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


def _process_whatsapp(payload: dict, ai: AIClient, pack: Pack) -> None:
    for sender, inbound in whatsapp.parse_payload(payload):
        with new_session() as db:
            try:
                reply = handle_message(db, ai, pack, inbound).reply
            except Exception:
                log.exception("WhatsApp message failed")
                db.rollback()
                reply = "Sorry, something went wrong. Please try again."
        whatsapp.send(sender, reply)


@whatsapp_router.post("/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks,
                           ai: AIClient = Depends(get_ai), pack: Pack = Depends(get_pack)):
    raw = await request.body()
    if not whatsapp.signature_valid(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Invalid signature")
    background.add_task(_process_whatsapp, await request.json(), ai, pack)
    return {"ok": True}


# ── Web form ─────────────────────────────────────────────────────────────────


class ReportReceipt(BaseModel):
    tracking_id: str | None
    status: str | None
    sector: str | None
    region_name: str | None
    message: str


@web_router.post("/reports", response_model=ReportReceipt)
@limiter.limit("10/minute")
async def submit_web_report(
    request: Request,
    client_id: str = Form(..., min_length=8, max_length=64, description="Random ID the browser keeps; hashed"),
    text: str | None = Form(None, max_length=4000),
    region_id: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db), ai: AIClient = Depends(get_ai), pack: Pack = Depends(get_pack),
):
    media = mime = None
    if file is not None and file.filename:
        if not (file.content_type or "").startswith(("audio/", "image/")):
            raise HTTPException(status_code=422, detail="Only audio or image files are accepted")
        media = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(media) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File is larger than 10 MB")
        mime = file.content_type
    if not (text and text.strip()) and not media:
        raise HTTPException(status_code=422, detail="Describe the problem in text, or attach a voice note or photo")
    if not region_id and (lat is None or lon is None):
        raise HTTPException(status_code=422, detail="Choose your area, or share your location")
    if region_id and not db.get(Region, region_id):
        raise HTTPException(status_code=422, detail="Unknown area")

    outcome = handle_message(db, ai, pack, Inbound(channel="web", sender_id=client_id, text=text, media=media,
                                                   mime_type=mime, lat=lat, lon=lon, region_id=region_id))
    return ReportReceipt(tracking_id=outcome.tracking_id, status=outcome.status, sector=outcome.sector,
                         region_name=outcome.region_name, message=outcome.reply)


class TrackStatus(BaseModel):
    tracking_id: str
    received_at: str
    stage: str  # received | understood | located | prioritised | unlocated
    sector: str | None
    region_name: str | None
    verdict: str | None = None
    rank: int | None = None


@web_router.get("/track/{tracking_id}", response_model=TrackStatus)
def track(tracking_id: str, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    report = db.scalar(select(Report).where(Report.tracking_id == tracking_id.strip().upper()))
    if not report:
        raise HTTPException(status_code=404, detail="No report with that tracking ID")
    region = db.get(Region, report.region_id) if report.region_id else None
    stage = {"received": "received", "understood": "understood", "needs_location": "understood",
             "needs_confirmation": "understood", "located": "located", "unlocated": "unlocated"}[report.status]
    status = TrackStatus(tracking_id=report.tracking_id, received_at=report.created_at.isoformat(), stage=stage,
                         sector=report.sector, region_name=region.name if region else None)
    run = latest_complete_run(db, pack.country_code)
    if run and report.region_id:
        priority = db.scalar(select(Priority).where(
            Priority.run_id == run.id, Priority.region_id == report.region_id,
            Priority.sector == report.sector, Priority.displayable.is_(True)))
        if priority:
            status.stage, status.verdict, status.rank = "prioritised", priority.verdict, priority.rank
    return status


# ── Admin ────────────────────────────────────────────────────────────────────


@admin_router.post("/reprocess")
def reprocess(db: Session = Depends(get_db), ai: AIClient = Depends(get_ai), pack: Pack = Depends(get_pack)):
    """Finish reports that arrived while Gemini was unavailable."""
    return reprocess_pending(db, ai, pack)


@admin_router.get("/flagged")
def flagged(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """Reports held out of scoring as possibly coordinated. Never exposes reporter identity."""
    rows = db.scalars(select(Report).where(Report.country_code == pack.country_code,
                                           Report.flagged_coordinated.is_(True)).order_by(Report.id.desc()).limit(200))
    return [{"tracking_id": r.tracking_id, "region_id": r.region_id, "sector": r.sector, "text_en": r.text_en,
             "created_at": r.created_at.isoformat()} for r in rows]
