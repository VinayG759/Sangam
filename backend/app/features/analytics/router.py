"""
Aggregates for the Analytics page, in one read-only call. No model calls.

Everything here respects the same privacy floor as the rest of the dashboard:
verdict counts come only from displayable priorities, and report counts are
totals, never individual reports.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.regions import children_map, country_regions, starting_place, subtree_ids
from app.core.runs import latest_complete_run
from app.models import Indicator, Priority, Project, Region, Report

router = APIRouter(prefix="/api/v1", tags=["analytics"])

WEEKS = 12
# Verdicts where money is the question: committed but stuck, or planned but not started.
MONEY_VERDICTS = ("STALLED_ALLOCATION", "PLANNED_NOT_STARTED")
ACTION_VERDICTS = ("UNSERVED_GAP", "DELIVERY_GAP", "STALLED_ALLOCATION", "PLANNED_NOT_STARTED")


@router.get("/analytics")
def analytics(region: str | None = None, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    regions = country_regions(db, pack.country_code)
    children = children_map(regions)
    if region and region not in regions:
        raise HTTPException(status_code=404, detail="Region not found")
    scope = subtree_ids(regions, region) if region else None
    root = regions[region] if region else starting_place(regions, children)

    def inside(column):
        return column.in_(scope) if scope is not None else True

    in_country = Report.country_code == pack.country_code
    now = datetime.now(timezone.utc)

    # Reports per week, oldest first, with empty weeks kept so the line does not skip.
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    first_monday = today - timedelta(days=today.weekday(), weeks=WEEKS)  # whole weeks only
    week = func.date_trunc("week", Report.created_at)
    counts = dict(db.execute(select(week, func.count()).where(in_country, inside(Report.region_id),
                                                              Report.created_at >= first_monday)
                             .group_by(week)).all())
    timeline = []
    for i in range(WEEKS):  # the current, unfinished week is left out so the line never ends in a false drop
        monday = first_monday + timedelta(weeks=i)
        n = next((v for k, v in counts.items() if k.date() == monday.date()), 0)
        timeline.append({"week": monday.date().isoformat(), "reports": n})

    totals = {
        "reports": db.scalar(select(func.count()).select_from(Report).where(in_country, inside(Report.region_id))) or 0,
        "residents": db.scalar(select(func.count(func.distinct(Report.reporter_hash))).where(
            in_country, inside(Report.region_id))) or 0,
    }

    # Verdicts per need, from the latest run, shown groups only.
    run = latest_complete_run(db, pack.country_code)
    priorities = []
    if run:
        priorities = list(db.scalars(select(Priority).where(Priority.run_id == run.id, Priority.displayable.is_(True),
                                                            inside(Priority.region_id))))
    by_need: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in priorities:
        by_need[p.sector][p.verdict] += 1
    needs = [{"sector": n.key, "label": n.label_en, "verdicts": dict(by_need.get(n.key, {}))} for n in pack.needs
             if n.key in by_need]
    needs.sort(key=lambda n: -sum(v for k, v in n["verdicts"].items() if k in ACTION_VERDICTS))
    totals["places_needing_action"] = len({p.region_id for p in priorities if p.verdict in ACTION_VERDICTS})

    # Public money by project status; and how much sits where residents say it is not arriving.
    projects = list(db.scalars(select(Project).where(Project.region_id.in_(regions), inside(Project.region_id))))
    money: dict[str, dict] = {}
    for project in projects:
        row = money.setdefault(project.status, {"status": project.status, "projects": 0, "amount": 0.0,
                                                "synthetic": False})
        row["projects"] += 1
        row["amount"] += float(project.amount or 0)
        row["synthetic"] = row["synthetic"] or project.is_synthetic
    flagged_places = {(p.region_id, p.sector) for p in priorities if p.verdict in MONEY_VERDICTS}
    flagged = [pr for pr in projects if (pr.region_id, pr.sector) in flagged_places and pr.status != "completed"]
    totals["money_flagged"] = sum(float(pr.amount or 0) for pr in flagged)
    totals["money_flagged_synthetic"] = any(pr.is_synthetic for pr in flagged)

    return {
        "run": {"id": run.id, "completed_at": run.completed_at.isoformat()} if run else None,
        "region": {"id": region, "name": regions[region].name} if region else None,
        "currency": pack.currency, "currency_symbol": pack.currency_symbol,
        "totals": totals, "timeline": timeline, "needs": needs,
        "money": sorted(money.values(), key=lambda m: -m["amount"]),
        "progress": _progress(db, pack, regions, children, root),
    }


def _progress(db: Session, pack: Pack, regions: dict[str, Region], children, root: Region | None) -> list[dict]:
    """
    Official progress per need, for the places one level below `root`: the average of the
    deepest-level places inside each, at the baseline and now (only places with both readings).
    """
    if root is None or not children.get(root.id):
        return []
    deepest = max(r.level for r in regions.values())
    out = []
    for sector, rule in pack.indicators.items():
        if not rule.baseline_key:
            continue
        readings: dict[str, dict[str, Indicator]] = defaultdict(dict)
        for ind in db.scalars(select(Indicator).where(Indicator.key.in_([rule.key, rule.baseline_key]),
                                                      Indicator.region_id.in_(regions)).order_by(Indicator.period)):
            readings[ind.region_id][ind.key] = ind
        rows, synthetic = [], False
        for child in children[root.id]:
            leaves = [rid for rid in subtree_ids(regions, child.id) if regions[rid].level == deepest]
            pairs = [(readings[r][rule.baseline_key], readings[r][rule.key]) for r in leaves
                     if rule.key in readings[r] and rule.baseline_key in readings[r]]
            if not pairs:
                continue
            synthetic = synthetic or any(a.is_synthetic or b.is_synthetic for a, b in pairs)
            rows.append({"id": child.id, "name": child.name, "places": len(pairs),
                         "baseline": round(sum(a.value for a, _ in pairs) / len(pairs), 1),
                         "current": round(sum(b.value for _, b in pairs) / len(pairs), 1)})
        if not rows:
            continue
        first = next(iter(readings.values()))
        need = pack.need(sector)
        out.append({"sector": sector, "label": need.label_en if need else sector, "statistic": rule.label or rule.key,
                    "unit": rule.unit, "served_threshold": rule.served_threshold, "synthetic": synthetic,
                    "baseline_period": first[rule.baseline_key].period if rule.baseline_key in first else None,
                    "current_period": first[rule.key].period if rule.key in first else None,
                    "source_name": first[rule.key].source_name if rule.key in first else None,
                    "rows": sorted(rows, key=lambda r: r["current"])})
    return out
