"""
Issue Clusters API routes.

Provides endpoints for:
- Listing clusters with sector and region filters
- Getting a single cluster with linked reports and priority info
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from app.db import get_db
from app.models.models import IssueCluster, CitizenReport, AdminRegion, Priority

router = APIRouter(prefix="/api/v1", tags=["Clusters"])


@router.get("/clusters")
async def list_clusters(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    region_id: Optional[int] = Query(None, description="Filter by region ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    List issue clusters. Each cluster represents a geographic concentration
    of citizen reports about the same infrastructure sector.
    """
    try:
        stmt = select(IssueCluster)

        if sector:
            stmt = stmt.where(IssueCluster.sector == sector)
        if region_id is not None:
            stmt = stmt.where(IssueCluster.region_id == region_id)

        stmt = stmt.order_by(IssueCluster.report_count.desc())
        result = await db.execute(stmt)
        clusters = result.scalars().all()

        items = []
        for c in clusters:
            # Fetch region name
            region_result = await db.execute(
                select(AdminRegion.name).where(AdminRegion.id == c.region_id)
            )
            region_name = region_result.scalar() or "Unknown"

            # Check if a priority exists for this cluster
            priority_result = await db.execute(
                select(Priority.id, Priority.score, Priority.verdict)
                .where(Priority.cluster_id == c.id)
            )
            priority_row = priority_result.first()

            items.append({
                "id": c.id,
                "title": c.title,
                "sector": c.sector,
                "region_id": c.region_id,
                "region_name": region_name,
                "report_count": c.report_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "priority": {
                    "id": priority_row[0],
                    "score": priority_row[1],
                    "verdict": priority_row[2],
                } if priority_row else None,
            })

        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list clusters: {e}")


@router.get("/clusters/{cluster_id}")
async def get_cluster_detail(cluster_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a single cluster with its linked citizen reports and priority details.
    """
    result = await db.execute(
        select(IssueCluster).where(IssueCluster.id == cluster_id)
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Fetch region
    region_result = await db.execute(
        select(AdminRegion).where(AdminRegion.id == cluster.region_id)
    )
    region = region_result.scalar_one_or_none()

    # Fetch linked reports
    reports_result = await db.execute(
        select(CitizenReport)
        .where(CitizenReport.cluster_id == cluster_id)
        .order_by(CitizenReport.urgency_score.desc())
    )
    reports = reports_result.scalars().all()

    # Fetch priority
    priority_result = await db.execute(
        select(Priority)
        .where(Priority.cluster_id == cluster_id)
        .options(
            selectinload(Priority.evidence_bundle),
            selectinload(Priority.narrative_brief)
        )
    )
    priority = priority_result.scalar_one_or_none()

    priority_data = None
    if priority:
        priority_data = {
            "id": priority.id,
            "score": priority.score,
            "verdict": priority.verdict,
            "details": priority.details,
            "evidence_bundle": priority.evidence_bundle.data if priority.evidence_bundle else None,
            "narrative_brief": {
                "summary": priority.narrative_brief.summary,
                "why_prioritized": priority.narrative_brief.why_prioritized,
                "fiscal_gap_analysis": priority.narrative_brief.fiscal_gap_analysis,
                "recommended_action": priority.narrative_brief.recommended_action,
            } if priority.narrative_brief else None,
        }

    return {
        "id": cluster.id,
        "title": cluster.title,
        "sector": cluster.sector,
        "report_count": cluster.report_count,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else None,
        "region": {
            "id": region.id,
            "name": region.name,
            "level": region.level,
        } if region else None,
        "reports": [
            {
                "id": r.id,
                "english_translation": r.english_translation,
                "sector": r.sector,
                "urgency_score": r.urgency_score,
                "sentiment": r.sentiment,
                "reported_at": r.reported_at.isoformat() if r.reported_at else None,
            }
            for r in reports
        ],
        "priority": priority_data,
    }
