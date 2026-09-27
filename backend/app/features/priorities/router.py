"""
Ranked recommendations with their full evidence chain, and the anonymised
citizen reports behind each one. Only groups at or above the privacy floor
are ever returned.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.regions import country_regions, subtree_ids
from app.core.runs import latest_complete_run
from app.models import Cluster, Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["priorities"])


def _region_view(region: Region, regions: dict[str, Region], pack: Pack) -> dict:
    parent = regions.get(region.parent_id or "")
    return {"id": region.id, "name": region.name,
            "level_name": pack.admin_levels[region.level] if region.level < len(pack.admin_levels) else None,
            "parent_name": parent.name if parent and parent.level > 0 else None}


def _row(priority: Priority, cluster: Cluster, regions: dict[str, Region], pack: Pack) -> dict:
    need = pack.need(priority.sector)
    return {
        "id": priority.id, "rank": priority.rank, "verdict": priority.verdict, "score": priority.score,
        "region": _region_view(regions[priority.region_id], regions, pack),
        "sector": priority.sector, "sector_label": need.label_en if need else priority.sector,
        "distinct_reporters": cluster.distinct_reporters, "report_count": cluster.report_count,
        "per_1000": cluster.per_1000, "baseline_ratio": cluster.baseline_ratio,
        "is_emerging": cluster.is_emerging, "avg_urgency": cluster.avg_urgency,
        "estimated_cost": priority.estimated_cost, "beneficiaries": priority.beneficiaries,
        "summary": priority.summary, "summary_source": priority.summary_source,
    }


@router.get("/priorities")
def list_priorities(verdict: str | None = None, sector: str | None = None, q: str | None = None,
                    region: str | None = None, limit: int = Query(100, le=500),
                    db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    regions = country_regions(db, pack.country_code)
    if region and region not in regions:
        raise HTTPException(status_code=404, detail="Region not found")
    run = latest_complete_run(db, pack.country_code)
    if not run:
        return {"run": None, "items": []}
    query = (select(Priority, Cluster).join(Cluster, Priority.cluster_id == Cluster.id)
             .where(Priority.run_id == run.id, Priority.displayable.is_(True)).order_by(Priority.rank))
    if verdict:
        query = query.where(Priority.verdict == verdict)
    if sector:
        query = query.where(Priority.sector == sector)
    if region:
        query = query.where(Priority.region_id.in_(subtree_ids(regions, region)))
    items = [_row(p, c, regions, pack) for p, c in db.execute(query).all()]
    if q:
        needle = q.casefold()
        items = [i for i in items if needle in i["region"]["name"].casefold()
                 or needle in (i["region"]["parent_name"] or "").casefold()]
    return {"run": {"id": run.id, "completed_at": run.completed_at.isoformat()}, "items": items[:limit]}


def _get_displayable(db: Session, priority_id: int) -> tuple[Priority, Cluster]:
    row = db.execute(select(Priority, Cluster).join(Cluster, Priority.cluster_id == Cluster.id)
                     .where(Priority.id == priority_id, Priority.displayable.is_(True))).first()
    if not row:
        raise HTTPException(status_code=404, detail="Priority not found")
    return row[0], row[1]


@router.get("/priorities/{priority_id}")
def get_priority(priority_id: int, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    priority, cluster = _get_displayable(db, priority_id)
    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    return {**_row(priority, cluster, regions, pack), "components": priority.components,
            "evidence": priority.evidence, "run_id": priority.run_id,
            "first_seen": cluster.first_seen.isoformat(), "last_seen": cluster.last_seen.isoformat(),
            "weights": pack.weights.model_dump()}


@router.get("/priorities/{priority_id}/reports")
def priority_reports(priority_id: int, limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    """The citizen reports behind a recommendation — redacted text only, never who sent them."""
    priority, _ = _get_displayable(db, priority_id)
    reports = db.scalars(select(Report).where(
        Report.region_id == priority.region_id, Report.sector == priority.sector, Report.status == "located",
        Report.flagged_coordinated.is_(False)).order_by(Report.created_at.desc()).limit(limit))
    return [{"created_at": r.created_at.isoformat(), "channel": r.channel, "language": r.language,
             "text_original": r.text_original, "text_en": r.text_en, "urgency": r.urgency,
             "is_synthetic": r.is_synthetic} for r in reports]
