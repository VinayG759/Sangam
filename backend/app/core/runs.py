"""Which analysis run the dashboard should read: always the latest *complete* one."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRun


def latest_complete_run(db: Session, country_code: str) -> AnalysisRun | None:
    return db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.country_code == country_code, AnalysisRun.status == "complete")
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    ).first()
