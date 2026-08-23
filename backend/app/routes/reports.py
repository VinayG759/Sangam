"""
Citizen Reports API routes.

Provides endpoints for:
- Listing citizen reports with sector, region, and pagination filters
- Getting a single report's full detail
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from app.db import get_db
from app.limiter import limiter
from app.models.models import CitizenReport

router = APIRouter(prefix="/api/v1", tags=["Citizen Reports"])


@router.get("/reports")
async def list_reports(
    sector: Optional[str] = Query(None, description="Filter by sector (water, roads, etc.)"),
    language: Optional[str] = Query(None, description="Filter by detected language code"),
    cluster_id: Optional[int] = Query(None, description="Filter by assigned cluster ID"),
    min_urgency: Optional[float] = Query(None, ge=1.0, le=5.0, description="Minimum urgency score"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db)
):
    """
    List citizen reports with optional filtering and pagination.
    Reports are ordered by most recent first.
    """
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    try:
        stmt = select(CitizenReport)

        if sector:
            stmt = stmt.where(CitizenReport.sector == sector)
        if language:
            stmt = stmt.where(CitizenReport.detected_language == language)
        if cluster_id is not None:
            stmt = stmt.where(CitizenReport.cluster_id == cluster_id)
        if min_urgency is not None:
            stmt = stmt.where(CitizenReport.urgency_score >= min_urgency)

        # Get total count for pagination metadata
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        # Apply pagination and ordering
        stmt = stmt.order_by(CitizenReport.reported_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        reports = result.scalars().all()

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "reports": [
                {
                    "id": r.id,
                    "raw_text": r.raw_text,
                    "detected_language": r.detected_language,
                    "english_translation": r.english_translation,
                    "sector": r.sector,
                    "specific_issue": r.specific_issue,
                    "urgency_score": r.urgency_score,
                    "sentiment": r.sentiment,
                    "pii_redacted_text": r.pii_redacted_text,
                    "cluster_id": r.cluster_id,
                    "reported_at": r.reported_at.isoformat() if r.reported_at else None,
                }
                for r in reports
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list reports: {e}")


@router.get("/reports/{report_id}")
async def get_report_detail(report_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a single citizen report's full detail.
    """
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    result = await db.execute(
        select(CitizenReport).where(CitizenReport.id == report_id)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Citizen report not found")

    cluster_id = r.cluster_id
    verdict = None
    if cluster_id:
        p_result = await db.execute(
            select(Priority).where(Priority.cluster_id == cluster_id)
        )
        p = p_result.scalar_one_or_none()
        if p:
            verdict = p.verdict

    return {
        "id": r.id,
        "raw_text": r.raw_text,
        "translated_text": r.english_translation,
        "sector": r.sector,
        "specific_issue": r.specific_issue,
        "urgency_score": r.urgency_score,
        "cluster_id": cluster_id,
        "verdict": verdict,
        "reported_at": r.reported_at.isoformat() if r.reported_at else None
    }


@router.get("/citizens/{tracking_id}")
@limiter.limit("20/minute")
async def get_citizen_report_by_tracking_id(request: Request, tracking_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a citizen report status by tracking ID.
    Used for the citizen trust loop.

    Rate-limited per IP: this route is intentionally unauthenticated (a
    citizen looking up their own report has no other credential), so the
    tracking-id length and this limit are what stand between it and
    enumeration -- see app/utils/tracking_id.py.
    """
    result = await db.execute(
        select(CitizenReport).where(CitizenReport.tracking_id == tracking_id)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")

    # Optionally fetch cluster and priority status to show progress
    status = "received"
    if r.cluster_id:
        status = "clustered"
        p_result = await db.execute(select(Priority).where(Priority.cluster_id == r.cluster_id))
        p = p_result.scalar_one_or_none()
        if p:
            status = p.verdict.lower()

    # specific_issue is deliberately withheld here: this route is unauthenticated
    # and the tracking ID is short enough that a determined scraper could still
    # walk part of the space even after lengthening it. Free-text issue content
    # is more identifying than a sector code, so it's kept out of the one
    # response an anonymous caller can get from a guessed ID.
    return {
        "tracking_id": r.tracking_id,
        "sector": r.sector,
        "reported_at": r.reported_at.isoformat() if r.reported_at else None,
        "status": status,
        "channel": r.channel
    }
