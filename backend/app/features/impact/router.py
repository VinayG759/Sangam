"""Impact views. Read-only, computed on request from real statistics and reports; no model calls."""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.runs import latest_complete_run
from app.features.impact.service import TOO_EARLY, change_label, progress_label
from app.models import Cluster, Indicator, Priority, Project, Region, Report

router = APIRouter(prefix="/api/v1/impact", tags=["impact"])


@router.get("/progress")
def programme_progress(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """For every need with a baseline statistic: official progress since the baseline, and what residents say now."""
    run = latest_complete_run(db, pack.country_code)
    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    priorities = {}
    if run:
        for p, c in db.execute(select(Priority, Cluster).join(Cluster, Priority.cluster_id == Cluster.id)
                               .where(Priority.run_id == run.id, Priority.displayable.is_(True))):
            priorities[(p.region_id, p.sector)] = (p, c)

    programmes = []
    for sector, rule in pack.indicators.items():
        if not rule.baseline_key:
            continue
        values: dict[str, dict[str, Indicator]] = {}
        for ind in db.scalars(select(Indicator).where(Indicator.key.in_([rule.key, rule.baseline_key]),
                                                      Indicator.region_id.in_(regions)).order_by(Indicator.period)):
            values.setdefault(ind.region_id, {})[ind.key] = ind  # latest period per key wins
        rows = []
        for region_id, pair in values.items():
            now, then = pair.get(rule.key), pair.get(rule.baseline_key)
            if not (now and then):
                continue
            region = regions[region_id]
            parent = regions.get(region.parent_id or "")
            priority, cluster = priorities.get((region_id, sector), (None, None))
            rows.append({
                "region_id": region_id, "region_name": region.name,
                "parent_name": parent.name if parent and parent.level > 0 else None,
                "level_name": pack.admin_levels[region.level] if region.level < len(pack.admin_levels) else None,
                "baseline": then.value, "baseline_period": then.period, "current": now.value,
                "current_period": now.period, "change": round(now.value - then.value, 2),
                "label": progress_label(priority.verdict if priority else None),
                "verdict": priority.verdict if priority else None,
                "priority_id": priority.id if priority else None,
                "residents_reporting": cluster.distinct_reporters if cluster else None,
            })
        rows.sort(key=lambda r: ({"NOT_REACHING": 0, "STILL_SHORT": 1}.get(r["label"], 2), -r["change"]))
        need = pack.need(sector)
        first = next(iter(values.values()), {})
        source = first.get(rule.key)
        programmes.append({
            "sector": sector, "sector_label": need.label_en if need else sector,
            "statistic": rule.label or rule.key, "unit": rule.unit,
            "served_threshold": rule.served_threshold,
            "source_name": source.source_name if source else None, "source_url": source.source_url if source else None,
            "rows": rows,
        })
    return {"run": {"id": run.id, "completed_at": run.completed_at.isoformat()} if run else None,
            "programmes": programmes}


@router.get("/projects")
def completed_projects(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """Complaints before vs after each completed project, in equal windows either side of completion."""
    t = pack.thresholds
    window, grace = timedelta(days=t.impact_window_days), timedelta(days=t.impact_grace_days)
    floor = pack.privacy.min_distinct_reporters
    today = datetime.now(timezone.utc)
    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    projects = list(db.scalars(select(Project).where(Project.status == "completed", Project.completion_date.is_not(None),
                                                     Project.region_id.in_(regions))))

    def reporters(region_id: str, sector: str, start: datetime, end: datetime) -> int:
        return db.scalar(select(func.count(func.distinct(Report.reporter_hash))).where(
            Report.region_id == region_id, Report.sector == sector, Report.status == "located",
            Report.flagged_coordinated.is_(False), Report.created_at >= start, Report.created_at < end)) or 0

    rows = []
    for project in projects:
        done = datetime.combine(project.completion_date, time.min, tzinfo=timezone.utc)
        after_start, after_end = done + grace, done + grace + window
        if after_end > today:
            label, change, before, after = TOO_EARLY, None, None, None
        else:
            before = reporters(project.region_id, project.sector, done - window, done)
            after = reporters(project.region_id, project.sector, after_start, after_end)
            label, change = change_label(before, after, floor, t.impact_change)
            if before < floor and after < floor:
                before = after = None  # never show counts that could single people out
        need = pack.need(project.sector)
        rows.append({
            "project_id": project.id, "title": project.title, "region_name": regions[project.region_id].name,
            "sector": project.sector, "sector_label": need.label_en if need else project.sector,
            "completion_date": project.completion_date.isoformat(), "amount": float(project.amount) if project.amount else None,
            "currency": project.currency, "source_name": project.source_name, "source_url": project.source_url,
            "reporters_before": before, "reporters_after": after, "change": change, "label": label,
        })
    return {"window_days": t.impact_window_days, "grace_days": t.impact_grace_days,
            "has_project_data": db.scalar(select(func.count()).select_from(Project).where(
                Project.region_id.in_(regions))) > 0,
            "projects": rows}
