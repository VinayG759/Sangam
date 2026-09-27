"""
Tells citizens when their report has reached the priority list.

Reads the latest complete run's priorities and the encrypted contacts kept by
intake. Each citizen gets at most one update; the contact is deleted as soon
as it is delivered, and any contact past its expiry is deleted unsent.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import messaging
from app.core.config import get_settings
from app.core.crypto import contacts_enabled, decrypt
from app.core.pack import Pack
from app.core.runs import latest_complete_run
from app.models import Contact, Priority, Region, Report

log = logging.getLogger(__name__)

VERDICT_WORDS = {
    "UNSERVED_GAP": "recommended for funding",
    "DELIVERY_GAP": "recommended for a delivery audit",
    "STALLED_ALLOCATION": "recommended for a delivery audit",
    "PLANNED_NOT_STARTED": "recommended for an audit of why planned work has not started",
    "DEMAND_HOTSPOT": "flagged for officials to verify",
    "MONITOR": "being monitored",
}


def update_sentence(need: str, place: str, verdict: str, rank: int) -> str:
    return (f"{need} in {place} is now on the government priority list (rank {rank}) and is "
            f"{VERDICT_WORDS.get(verdict, 'under review')}.")


def send_updates(db: Session, pack: Pack, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    expired = db.execute(delete(Contact).where(Contact.expires_at < now)).rowcount
    db.commit()
    stats = {"sent": 0, "skipped": 0, "failed": 0, "expired_deleted": expired}
    if not contacts_enabled():
        return stats
    run = latest_complete_run(db, pack.country_code)
    if not run:
        return stats

    settings = get_settings()
    rows = db.execute(
        select(Contact, Report, Priority, Region)
        .join(Report, Report.id == Contact.report_id)
        .join(Priority, (Priority.run_id == run.id) & (Priority.region_id == Report.region_id)
              & (Priority.sector == Report.sector) & Priority.displayable.is_(True))
        .join(Region, Region.id == Report.region_id)
    ).all()

    for contact, report, priority, region in rows:
        need = pack.need(report.sector)
        sentence = update_sentence(need.label_en if need else report.sector, region.name, priority.verdict,
                                   priority.rank)
        link = f" Track it: {settings.PUBLIC_APP_URL.rstrip('/')}/track/{report.tracking_id}" if settings.PUBLIC_APP_URL else ""
        address = decrypt(contact.address_encrypted)

        if contact.channel == "telegram":
            delivered = messaging.send_telegram(address, f"Update on your report {report.tracking_id}: {sentence}{link}")
        elif contact.channel == "whatsapp":
            if not settings.WHATSAPP_NOTIFY_TEMPLATE:
                stats["skipped"] += 1  # outside the 24h window only an approved template may be sent
                continue
            delivered = messaging.send_whatsapp_template(address, settings.WHATSAPP_NOTIFY_TEMPLATE,
                                                         settings.WHATSAPP_TEMPLATE_LANGUAGE,
                                                         [report.tracking_id, sentence])
        else:
            stats["skipped"] += 1
            continue

        if delivered:
            db.delete(contact)  # the only reason to keep it is gone
            stats["sent"] += 1
        else:
            stats["failed"] += 1  # kept; retried next time until it expires
    db.commit()
    return stats
