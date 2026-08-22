"""
Citizen Reports API routes.

Provides endpoints for:
- Listing citizen reports with sector, region, and pagination filters
- Getting a single report's full detail
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from app.db import get_db
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
    result = await db.execute(
        select(CitizenReport).where(CitizenReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Citizen report not found")

    return {
        "id": report.id,
        "raw_text": report.raw_text,
        "detected_language": report.detected_language,
        "english_translation": report.english_translation,
        "sector": report.sector,
        "specific_issue": report.specific_issue,
        "urgency_score": report.urgency_score,
        "sentiment": report.sentiment,
        "pii_redacted_text": report.pii_redacted_text,
        "cluster_id": report.cluster_id,
        "reported_at": report.reported_at.isoformat() if report.reported_at else None,
    }
