"""Headline numbers and the map. Read-only; no model calls."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.runs import latest_complete_run
from app.models import Cluster, Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    in_country = Report.country_code == pack.country_code

    def count(*conditions) -> int:
        return db.scalar(select(func.count()).select_from(Report).where(in_country, *conditions)) or 0

    total = count()
    languages = db.execute(select(Report.language, func.count()).where(in_country, Report.language.is_not(None))
                           .group_by(Report.language).order_by(func.count().desc())).all()
    channels = db.execute(select(Report.channel, func.count()).where(in_country)
                          .group_by(Report.channel).order_by(func.count().desc())).all()
    regions_covered = db.scalar(select(func.count(func.distinct(Report.region_id))).where(
        in_country, Report.region_id.is_not(None))) or 0

    run = latest_complete_run(db, pack.country_code)
    verdicts, emerging, top = {}, 0, []
    if run:
        verdicts = dict(db.execute(select(Priority.verdict, func.count()).where(
            Priority.run_id == run.id, Priority.displayable.is_(True)).group_by(Priority.verdict)).all())
        emerging = db.scalar(select(func.count()).select_from(Priority).join(Cluster).where(
            Priority.run_id == run.id, Priority.displayable.is_(True), Cluster.is_emerging.is_(True))) or 0

    return {
        "country_code": pack.country_code,
        "run": {"id": run.id, "completed_at": run.completed_at.isoformat()} if run else None,
        "reports": {
            "total": total,
            "located": count(Report.status == "located"),
            "unlocated": count(Report.status.in_(["unlocated", "needs_location", "needs_confirmation"])),
            "awaiting_processing": count(Report.status == "received"),
            "flagged_coordinated": count(Report.flagged_coordinated.is_(True)),
            "synthetic": count(Report.is_synthetic.is_(True)),
        },
        "languages": [{"code": code, "count": n} for code, n in languages],
        "channels": [{"channel": channel, "count": n} for channel, n in channels],
        "regions_covered": regions_covered,
        "verdicts": verdicts,
        "emerging": emerging,
    }


@router.get("/map")
def map_points(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """Every displayable priority with a coordinate (its region's, or its parent's)."""
    run = latest_complete_run(db, pack.country_code)
    if not run:
        return []
    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    rows = db.execute(select(Priority, Cluster).join(Cluster, Priority.cluster_id == Cluster.id).where(
        Priority.run_id == run.id, Priority.displayable.is_(True))).all()
    points = []
    for priority, cluster in rows:
        region = regions[priority.region_id]
        anchor = region if region.lat is not None else regions.get(region.parent_id or "")
        if not anchor or anchor.lat is None:
            continue
        points.append({"priority_id": priority.id, "region_name": region.name, "lat": anchor.lat, "lon": anchor.lon,
                       "approximate": anchor is not region, "sector": priority.sector, "verdict": priority.verdict,
                       "score": priority.score, "rank": priority.rank,
                       "distinct_reporters": cluster.distinct_reporters, "is_emerging": cluster.is_emerging})
    return points
