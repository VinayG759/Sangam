"""Headline numbers and the map. Read-only; no model calls."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.regions import country_regions, subtree_ids
from app.core.runs import latest_complete_run
from app.models import Cluster, Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["overview"])

# Verdicts that call for a decision (fund or audit), as opposed to verify or monitor.
ACTION_VERDICTS = ("UNSERVED_GAP", "DELIVERY_GAP", "STALLED_ALLOCATION", "PLANNED_NOT_STARTED")
UNLOCATED_STATUSES = ("unlocated", "needs_location", "needs_confirmation")


def _scope(regions: dict[str, Region], region: str | None) -> set[str] | None:
    """The region ids under `region`, or None for the whole country."""
    if not region:
        return None
    if region not in regions:
        raise HTTPException(status_code=404, detail="Region not found")
    return subtree_ids(regions, region)


@router.get("/overview")
def overview(region: str | None = None, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    regions = country_regions(db, pack.country_code)
    scope = _scope(regions, region)
    in_country = Report.country_code == pack.country_code
    if scope is not None:
        in_country = in_country & Report.region_id.in_(scope)

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
        shown = [Priority.run_id == run.id, Priority.displayable.is_(True)]
        if scope is not None:
            shown.append(Priority.region_id.in_(scope))
        verdicts = dict(db.execute(select(Priority.verdict, func.count()).where(*shown)
                                   .group_by(Priority.verdict)).all())
        emerging = db.scalar(select(func.count()).select_from(Priority).join(Cluster).where(
            *shown, Cluster.is_emerging.is_(True))) or 0

    return {
        "country_code": pack.country_code,
        "region": {"id": region, "name": regions[region].name} if region else None,
        "run": {"id": run.id, "completed_at": run.completed_at.isoformat()} if run else None,
        "reports": {
            "total": total,
            "located": count(Report.status == "located"),
            # Unlocated reports belong to no place, so they exist only at whole-country scope.
            "unlocated": count(Report.status.in_(UNLOCATED_STATUSES)) if scope is None else None,
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


@router.get("/rollup")
def rollup(region: str | None = None, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """
    The places one level below `region` (default: the country), each with how many places under it
    need action. With no region, a chain of single children is skipped, so a country with only one
    top-level place loaded opens on the places inside it.
    """
    regions = country_regions(db, pack.country_code)
    children: dict[str, list[Region]] = {}
    for r in regions.values():
        if r.parent_id:
            children.setdefault(r.parent_id, []).append(r)
    if region:
        if region not in regions:
            raise HTTPException(status_code=404, detail="Region not found")
        parent = regions[region]
    else:
        parent = next((r for r in regions.values() if r.level == 0), None)
        if parent is None:
            return {"parent": None, "path": [], "level_name": None, "items": []}
        while len(children.get(parent.id, [])) == 1:
            parent = children[parent.id][0]

    run = latest_complete_run(db, pack.country_code)
    rows = []
    if run:
        rows = db.execute(select(Priority.region_id, Priority.verdict).where(
            Priority.run_id == run.id, Priority.displayable.is_(True))).all()

    items = []
    for child in children.get(parent.id, []):
        inside = subtree_ids(regions, child.id)
        verdicts: dict[str, int] = {}
        needing_action = set()
        for region_id, verdict in rows:
            if region_id in inside:
                verdicts[verdict] = verdicts.get(verdict, 0) + 1
                if verdict in ACTION_VERDICTS:
                    needing_action.add(region_id)
        items.append({"id": child.id, "name": child.name, "has_children": bool(children.get(child.id)),
                      "places_needing_action": len(needing_action), "verdicts": verdicts})
    items.sort(key=lambda i: (-i["places_needing_action"], -sum(i["verdicts"].values()), i["name"]))

    path, cursor = [], parent
    while cursor is not None and cursor.level > 0:
        path.insert(0, {"id": cursor.id, "name": cursor.name})
        cursor = regions.get(cursor.parent_id or "")
    child_level = parent.level + 1
    return {"parent": {"id": parent.id, "name": parent.name}, "path": path,
            "level_name": pack.admin_levels[child_level] if child_level < len(pack.admin_levels) else None,
            "items": items}


@router.get("/unlocated")
def unlocated(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """
    Reports that could not be placed, counted by reason. Counts only - never text, IDs or dates:
    report text is shown only for a place and need with enough distinct reporters, and these have no place.
    """
    rows = db.execute(select(Report.status, Report.location_failure, func.count()).where(
        Report.country_code == pack.country_code, Report.status.in_(UNLOCATED_STATUSES))
        .group_by(Report.status, Report.location_failure)).all()
    reasons: dict[str, int] = {}
    for status, failure, n in rows:
        reason = ("awaiting_place" if status == "needs_location" else
                  "awaiting_confirmation" if status == "needs_confirmation" else failure or "not_recorded")
        reasons[reason] = reasons.get(reason, 0) + n
    return {"total": sum(reasons.values()),
            "reasons": [{"reason": k, "count": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]}


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
