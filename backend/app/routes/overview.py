from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.models.models import CitizenReport, Expenditure, Priority, IssueCluster

router = APIRouter(prefix="/api/v1", tags=["Overview"])

@router.get("/overview")
async def get_overview(db: Session = Depends(get_db)):
    """
    Returns high-level metric cards for the main dashboard view.
    """
    try:
        total_reports = db.query(func.count(CitizenReport.id)).scalar() or 0
        total_expenditure = db.query(func.sum(Expenditure.amount)).scalar() or 0.0
        
        # Calculate unserved gaps (Priority verdict is UNSERVED_GAP)
        unserved_gaps_count = db.query(func.count(Priority.id)).filter(Priority.verdict == "UNSERVED_GAP").scalar() or 0
        
        # Calculate stalled allocations (Priority verdict is STALLED_ALLOCATION)
        stalled_projects_count = db.query(func.count(Priority.id)).filter(Priority.verdict == "STALLED_ALLOCATION").scalar() or 0
        
        # Stalled capital sum
        stalled_capital = db.query(func.sum(Expenditure.amount)).filter(Expenditure.status == "stalled").scalar() or 0.0

        # Sector breakdown of citizen reports
        sector_counts = db.query(
            CitizenReport.sector, func.count(CitizenReport.id)
        ).group_by(CitizenReport.sector).all()
        
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
