from datetime import datetime, timedelta, timezone

from app.features.intake.service import new_tracking_id
from app.models import Report


QUIET_DISTRICTS = ["TL-A-WEST", "TL-A-CENTRAL", "TL-A-UPPER", "TL-A-LOWER"]


def add_quiet_background(db) -> None:
    """Two reporters in each quiet district: below the privacy floor, but they set the 'typical place'."""
    for region in QUIET_DISTRICTS:
        add_reports(db, region, "water", 2, prefix="quiet")


def add_reports(db, region_id: str, sector: str, reporters: int, per_reporter: int = 1, days_ago: float = 1,
                country: str = "TL", prefix: str = "r") -> None:
    """Located reports from `reporters` distinct people in one place × need."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    for person in range(reporters):
        for _ in range(per_reporter):
            db.add(Report(tracking_id=new_tracking_id(), country_code=country, channel="seed",
                          reporter_hash=f"{prefix}-{region_id}-{sector}-{person}", status="located",
                          language="en", text_original="no water", text_en="no water", sector=sector,
                          urgency=3, region_id=region_id, location_method="picker", location_confidence=100,
                          created_at=when))
    db.commit()
