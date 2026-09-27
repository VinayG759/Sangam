"""
Anonymised citizen reports. Only reports belonging to a place × need that is
at or above the privacy floor in the latest run are shown, so no small group
of complainants can be singled out.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.runs import latest_complete_run
from app.models import Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/reports")
def list_reports(sector: str | None = None, language: str | None = None, page: int = Query(1, ge=1),
                 page_size: int = Query(50, le=100), db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    run = latest_complete_run(db, pack.country_code)
    if not run:
        return {"total": 0, "items": []}
    visible = and_(Priority.run_id == run.id, Priority.displayable.is_(True),
                   Priority.region_id == Report.region_id, Priority.sector == Report.sector)
    query = select(Report, Region.name).join(Priority, visible).join(Region, Region.id == Report.region_id).where(
        Report.country_code == pack.country_code, Report.status == "located",
        Report.flagged_coordinated.is_(False))
    if sector:
        query = query.where(Report.sector == sector)
    if language:
        query = query.where(Report.language == language)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"created_at": r.created_at.isoformat(), "channel": r.channel, "language": r.language, "sector": r.sector,
         "region_name": name, "text_en": r.text_en, "text_original": r.text_original, "urgency": r.urgency,
         "is_synthetic": r.is_synthetic} for r, name in rows]}
