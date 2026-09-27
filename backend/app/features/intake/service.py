"""
Intake: one function every channel calls. It turns an inbound message into a
stored, redacted, understood and located report — and decides the reply.

Rules it enforces:
  • Only redacted text is stored; the sender's ID is stored only as an HMAC.
  • At most one follow-up question per report (a location, or "did you mean…?"),
    with a second try allowed before giving up.
  • If Gemini is down, the report is still stored and still gets a tracking ID;
    reprocess_pending() finishes it later. Embeddings are NULL until real.
  • More than N reports per reporter per day are politely refused.
  • Near-identical reports from different people in a short window are flagged
    as coordinated and left out of scoring until an operator reviews them.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ai import AIClient, AIUnavailable, Understanding
from app.core.crypto import contacts_enabled, encrypt
from app.core.pack import Pack
from app.core.security import reporter_hash
from app.core.text import redact
from app.features.intake.location import Gazetteer, Match
from app.models import Contact, Conversation, Region, Report, ReportMedia

log = logging.getLogger(__name__)

TRACKING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CONVERSATION_TTL = timedelta(hours=1)
MAX_LOCATION_ATTEMPTS = 2
COORDINATED_WINDOW = timedelta(hours=24)
YES_WORDS = {"yes", "y", "yeah", "yep", "ok", "correct", "haan", "ha", "han", "ji", "houdu", "howdu", "sari",
             "avunu", "aam", "sim", "да", "हाँ", "हां", "ಹೌದು", "అవును", "ஆம்"}


@dataclass
class Inbound:
    channel: str  # telegram | whatsapp | web
    sender_id: str  # raw channel ID; hashed immediately, never stored
    text: str | None = None
    media: bytes | None = None
    mime_type: str | None = None
    lat: float | None = None
    lon: float | None = None
    region_id: str | None = None  # web form place picker
    reply_to: str | None = None  # chat ID / phone to send a later status update to; stored only encrypted


@dataclass
class Outcome:
    reply: str
    tracking_id: str | None = None
    status: str | None = None
    sector: str | None = None
    region_name: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_tracking_id() -> str:
    return "SG-" + "".join(secrets.choice(TRACKING_ALPHABET) for _ in range(6))


def _need_label(pack: Pack, sector: str | None, language: str | None) -> str:
    need = pack.need(sector or "")
    if not need:
        return "Other"
    local = need.labels.get(language or "")
    return f"{need.label_en} / {local}" if local and language != "en" else need.label_en


# ── Entry point ──────────────────────────────────────────────────────────────


def handle_message(db: Session, ai: AIClient, pack: Pack, msg: Inbound) -> Outcome:
    who = reporter_hash(msg.channel, msg.sender_id)

    pending = db.get(Conversation, who)
    if pending and pending.expires_at < _now():
        db.delete(pending)
        db.commit()
        pending = None
    if pending:
        return _answer_follow_up(db, pack, pending, msg)

    if not (msg.text or msg.media):
        return Outcome("Please describe the problem — send a voice note, a photo, or a short message.")

    since = _now() - timedelta(days=1)
    today = db.scalar(select(func.count()).select_from(Report).where(
        Report.reporter_hash == who, Report.created_at >= since))
    if today >= pack.thresholds.daily_reports_per_reporter:
        return Outcome("You have sent many reports today. Thank you — please try again tomorrow.")

    report = Report(tracking_id=new_tracking_id(), country_code=pack.country_code, channel=msg.channel,
                    reporter_hash=who, status="received", text_original=redact(msg.text),
                    has_media=msg.media is not None, lat=msg.lat, lon=msg.lon)

    try:
        understanding = ai.understand(pack, msg.text, msg.media, msg.mime_type)
    except AIUnavailable:
        db.add(report)
        db.flush()
        _remember_contact(db, pack, report, msg)
        if msg.media:
            db.add(ReportMedia(report_id=report.id, mime_type=msg.mime_type or "application/octet-stream",
                               data=msg.media))
        if msg.region_id:
            report.region_id, report.location_method, report.location_confidence = msg.region_id, "picker", 100.0
        db.commit()
        return Outcome(f"Received. Your tracking ID is {report.tracking_id}. "
                       "We will process your report shortly.", report.tracking_id, report.status)

    if not understanding.is_actionable:
        return Outcome("Sangam records problems with local services such as water, roads, electricity, "
                       "health, schools and sanitation. Please describe the problem and where it is.")

    _apply_understanding(report, understanding)
    db.add(report)
    db.flush()
    _remember_contact(db, pack, report, msg)
    _embed(ai, report)

    gazetteer = Gazetteer.for_pack(db, pack)
    if msg.region_id and msg.region_id in gazetteer.regions:
        match = Match(msg.region_id, gazetteer.regions[msg.region_id].name, 100.0)
        _locate(report, match, "picker")
    elif msg.lat is not None and msg.lon is not None:
        match = gazetteer.nearest(msg.lat, msg.lon)
        if match:
            _locate(report, match, "gps")
    else:
        match = gazetteer.resolve(understanding.place_names + [msg.text or ""])
        return _decide_on_place(db, pack, report, match, first_time=True)

    flag_coordinated(db, pack, report)
    db.commit()
    return _received(db, pack, report)


# ── Steps ────────────────────────────────────────────────────────────────────


def _remember_contact(db: Session, pack: Pack, report: Report, msg: Inbound) -> None:
    """Keep the reply address, encrypted, so the citizen can be told when the report is prioritised."""
    if not (msg.reply_to and contacts_enabled()):
        return
    db.add(Contact(report_id=report.id, channel=msg.channel, address_encrypted=encrypt(msg.reply_to),
                   expires_at=_now() + timedelta(days=pack.privacy.contact_retention_days)))


def _apply_understanding(report: Report, u: Understanding) -> None:
    report.language = u.language[:10]
    report.text_original = redact(u.transcript)
    report.text_en = redact(u.text_en)
    report.sector = u.sector
    report.urgency = u.urgency
    report.location_text = redact(", ".join(u.place_names)) or None
    report.status = "understood"
    report.processed_at = _now()


def _embed(ai: AIClient, report: Report) -> None:
    if not report.text_en:
        return
    try:
        report.embedding = ai.embed(report.text_en)
    except AIUnavailable:
        return  # stays NULL; reprocess fills it later


def flag_coordinated(db: Session, pack: Pack, report: Report) -> None:
    """Near-identical wording from several different people in 24h looks organised, not organic."""
    if report.embedding is None or report.region_id is None:
        return
    max_distance = 1 - pack.thresholds.coordinated_similarity
    twins = list(db.scalars(select(Report).where(
        Report.id != report.id,
        Report.region_id == report.region_id,
        Report.sector == report.sector,
        Report.reporter_hash != report.reporter_hash,
        Report.created_at >= _now() - COORDINATED_WINDOW,
        Report.embedding.is_not(None),
        Report.embedding.cosine_distance(report.embedding) < max_distance,
    )))
    if len({t.reporter_hash for t in twins}) >= 2:
        report.flagged_coordinated = True
        for twin in twins:
            twin.flagged_coordinated = True


def _locate(report: Report, match: Match, method: str) -> None:
    report.region_id = match.region_id
    report.location_method = method
    report.location_confidence = match.score
    report.status = "located"


def _decide_on_place(db: Session, pack: Pack, report: Report, match: Match | None, first_time: bool) -> Outcome:
    t = pack.thresholds
    if match and match.score >= t.location_accept:
        _locate(report, match, "text")
        flag_coordinated(db, pack, report)
        _close_conversation(db, report.reporter_hash)
        db.commit()
        return _received(db, pack, report)
    if match and match.score >= t.location_confirm:
        report.status = "needs_confirmation"
        _open_conversation(db, report, "confirm", match.region_id)
        db.commit()
        return Outcome(f"Received ({report.tracking_id}). Did you mean {match.name}? Reply YES, "
                       "or send the correct place name, or share your location.",
                       report.tracking_id, report.status, report.sector)
    report.status = "needs_location"
    _open_conversation(db, report, "location", None)
    db.commit()
    prefix = f"Received ({report.tracking_id}). " if first_time else ""
    return Outcome(prefix + f"{pack.places.ask} You can also share your location.",
                   report.tracking_id, report.status, report.sector)


def _answer_follow_up(db: Session, pack: Pack, pending: Conversation, msg: Inbound) -> Outcome:
    report = db.get(Report, pending.report_id)
    gazetteer = Gazetteer.for_pack(db, pack)

    if msg.lat is not None and msg.lon is not None:
        match = gazetteer.nearest(msg.lat, msg.lon)
        if match:
            _locate(report, match, "gps")
            flag_coordinated(db, pack, report)
            _close_conversation(db, report.reporter_hash)
            db.commit()
            return _received(db, pack, report)

    answer = (msg.text or "").strip()
    if pending.awaiting == "confirm" and answer.casefold().strip(".! ") in YES_WORDS:
        region = db.get(Region, pending.candidate_region_id)
        _locate(report, Match(region.id, region.name, 100.0), "text")  # confirmed by the citizen
        flag_coordinated(db, pack, report)
        _close_conversation(db, report.reporter_hash)
        db.commit()
        return _received(db, pack, report)

    pending.attempts += 1
    if pending.attempts > MAX_LOCATION_ATTEMPTS:
        report.status, report.location_failure = "unlocated", "gave_up_after_questions"
        _close_conversation(db, report.reporter_hash)
        db.commit()
        return Outcome(f"Thank you. We could not find that place, but your report {report.tracking_id} "
                       "is saved and counted.", report.tracking_id, report.status, report.sector)
    match = gazetteer.resolve([answer]) if answer else None
    db.commit()
    return _decide_on_place(db, pack, report, match, first_time=False)


def _open_conversation(db: Session, report: Report, awaiting: str, candidate: str | None) -> None:
    existing = db.get(Conversation, report.reporter_hash)
    if existing:
        existing.report_id, existing.awaiting, existing.candidate_region_id = report.id, awaiting, candidate
        existing.expires_at = _now() + CONVERSATION_TTL
    else:
        db.add(Conversation(reporter_hash=report.reporter_hash, report_id=report.id, awaiting=awaiting,
                            candidate_region_id=candidate, attempts=0, expires_at=_now() + CONVERSATION_TTL))


def _close_conversation(db: Session, who: str) -> None:
    existing = db.get(Conversation, who)
    if existing:
        db.delete(existing)


def _received(db: Session, pack: Pack, report: Report) -> Outcome:
    region = db.get(Region, report.region_id) if report.region_id else None
    region_name = region.name if region else None
    need = _need_label(pack, report.sector, report.language)
    reply = (f"Thank you. Your report is recorded.\nTracking ID: {report.tracking_id}\n"
             f"Need: {need}" + (f"\nPlace: {region_name}" if region_name else ""))
    return Outcome(reply, report.tracking_id, report.status, report.sector, region_name)


# ── Batch: finish reports that arrived while Gemini was unavailable ─────────


def reprocess_pending(db: Session, ai: AIClient, pack: Pack, limit: int = 20) -> dict[str, int]:
    done = failed = 0
    gazetteer = Gazetteer.for_pack(db, pack)
    pending = list(db.scalars(select(Report).where(
        Report.country_code == pack.country_code,
        (Report.status == "received") | (Report.embedding.is_(None) & Report.text_en.is_not(None)),
        Report.is_synthetic.is_(False),
    ).order_by(Report.id).limit(limit)))
    for report in pending:
        try:
            if report.status == "received":
                media = db.get(ReportMedia, report.id)
                u = ai.understand(pack, report.text_original, media.data if media else None,
                                  media.mime_type if media else None)
                _apply_understanding(report, u)
                if report.region_id:
                    report.status = "located"
                elif report.lat is not None and report.lon is not None:
                    match = gazetteer.nearest(report.lat, report.lon)
                    if match:
                        _locate(report, match, "gps")
                    else:
                        report.status, report.location_failure = "unlocated", "place_not_recognised"
                else:
                    # The citizen can no longer be asked, so record why the place could not be found.
                    match = gazetteer.resolve(u.place_names) if u.place_names else None
                    if match and match.score >= pack.thresholds.location_accept:
                        _locate(report, match, "text")
                    else:
                        report.status = "unlocated"
                        report.location_failure = (
                            "no_place_named" if not u.place_names else
                            "low_confidence_match" if match and match.score >= pack.thresholds.location_confirm
                            else "place_not_recognised")
                if media:
                    db.delete(media)
            if report.embedding is None and report.text_en:
                report.embedding = ai.embed(report.text_en)
                flag_coordinated(db, pack, report)
            db.commit()
            done += 1
        except AIUnavailable:
            db.rollback()
            failed += 1
            break  # Gemini is still down; try again next run
    return {"processed": done, "failed": failed, "remaining": max(0, len(pending) - done)}
