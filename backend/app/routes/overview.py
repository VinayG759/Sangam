from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from app.db import get_db
from app.models.models import CitizenReport, Expenditure, Priority, IssueCluster

router = APIRouter(prefix="/api/v1", tags=["Overview"])

@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    """
    Returns high-level metric cards for the main dashboard view.
    """
    try:
        # Total citizen reports
        result = await db.execute(select(func.count(CitizenReport.id)))
        total_reports = result.scalar() or 0

        # Total sanctioned expenditure
        result = await db.execute(select(func.sum(Expenditure.amount)))
        total_expenditure = result.scalar() or 0.0

        # Unserved gaps count (Priority verdict is UNSERVED_GAP)
        result = await db.execute(
            select(func.count(Priority.id)).where(Priority.verdict == "UNSERVED_GAP")
        )
        unserved_gaps_count = result.scalar() or 0

        # Stalled allocations count (Priority verdict is STALLED_ALLOCATION)
        result = await db.execute(
            select(func.count(Priority.id)).where(Priority.verdict == "STALLED_ALLOCATION")
        )
        stalled_projects_count = result.scalar() or 0

        # Stalled capital sum
        result = await db.execute(
            select(func.sum(Expenditure.amount)).where(Expenditure.status == "stalled")
        )
        stalled_capital = result.scalar() or 0.0

        # Sector breakdown of citizen reports
        result = await db.execute(
            select(CitizenReport.sector, func.count(CitizenReport.id))
            .group_by(CitizenReport.sector)
        )
        sector_counts = result.all()
        sectors_breakdown = {sector: count for sector, count in sector_counts}

        return {
            "total_citizen_reports": total_reports,
            "total_sanctioned_expenditure": total_expenditure,
            "unserved_gaps_count": unserved_gaps_count,
            "stalled_projects_count": stalled_projects_count,
            "stalled_capital_amount": stalled_capital,
            "sectors_breakdown": sectors_breakdown
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
