"""
Expenditures API routes.

Provides endpoints for:
- Listing expenditure records with sector, region, status, and year filters
- Getting a single expenditure's full detail
- Summary statistics by sector
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from app.db import get_db
from app.models.models import Expenditure, AdminRegion

router = APIRouter(prefix="/api/v1", tags=["Expenditures"])


@router.get("/expenditures")
async def list_expenditures(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    region_id: Optional[int] = Query(None, description="Filter by region ID"),
    status: Optional[str] = Query(None, description="Filter by status: sanctioned, completed, in_progress, stalled"),
    year: Optional[int] = Query(None, description="Filter by allocated year"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db)
):
    """
    List expenditure records with optional filters and pagination.
    """
    try:
        stmt = select(Expenditure)

        if sector:
            stmt = stmt.where(Expenditure.sector == sector)
        if region_id is not None:
            stmt = stmt.where(Expenditure.region_id == region_id)
        if status:
            stmt = stmt.where(Expenditure.status == status)
        if year is not None:
            stmt = stmt.where(Expenditure.allocated_year == year)

        # Total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        # Apply pagination
        stmt = stmt.order_by(Expenditure.allocated_year.desc(), Expenditure.amount.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        expenditures = result.scalars().all()

        items = []
        for e in expenditures:
            # Fetch region name
            region_result = await db.execute(
                select(AdminRegion.name).where(AdminRegion.id == e.region_id)
            )
            region_name = region_result.scalar() or "Unknown"

            items.append({
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "sector": e.sector,
                "amount": e.amount,
                "allocated_year": e.allocated_year,
                "status": e.status,
                "region_id": e.region_id,
                "region_name": region_name,
            })

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "expenditures": items,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list expenditures: {e}")


@router.get("/expenditures/summary")
async def expenditures_summary(
    region_id: Optional[int] = Query(None, description="Scope summary to a specific region"),
    db: AsyncSession = Depends(get_db)
):
    """
    Aggregate expenditure statistics grouped by sector.
    Shows total amount, count, and status breakdown per sector.
    """
    try:
        # Total by sector
        stmt = select(
            Expenditure.sector,
            func.count(Expenditure.id).label("count"),
            func.sum(Expenditure.amount).label("total_amount"),
        ).group_by(Expenditure.sector)

        if region_id is not None:
            stmt = stmt.where(Expenditure.region_id == region_id)

        result = await db.execute(stmt)
        sector_totals = result.all()

        # Status breakdown per sector
        status_stmt = select(
            Expenditure.sector,
            Expenditure.status,
            func.count(Expenditure.id).label("count"),
            func.sum(Expenditure.amount).label("amount"),
        ).group_by(Expenditure.sector, Expenditure.status)

        if region_id is not None:
            status_stmt = status_stmt.where(Expenditure.region_id == region_id)

        status_result = await db.execute(status_stmt)
        status_rows = status_result.all()

        # Build response
        summary = {}
        for sector, count, total_amount in sector_totals:
            summary[sector] = {
                "count": count,
                "total_amount": float(total_amount or 0),
                "by_status": {},
            }

        for sector, status, count, amount in status_rows:
            if sector in summary:
                summary[sector]["by_status"][status] = {
                    "count": count,
                    "amount": float(amount or 0),
                }

        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {e}")


@router.get("/expenditures/{expenditure_id}")
async def get_expenditure_detail(expenditure_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a single expenditure record's full detail.
    """
    result = await db.execute(
        select(Expenditure).where(Expenditure.id == expenditure_id)
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expenditure not found")

    # Fetch region name
    region_result = await db.execute(
        select(AdminRegion.name).where(AdminRegion.id == exp.region_id)
    )
    region_name = region_result.scalar() or "Unknown"

    return {
        "id": exp.id,
        "title": exp.title,
        "description": exp.description,
        "sector": exp.sector,
        "amount": exp.amount,
        "allocated_year": exp.allocated_year,
        "status": exp.status,
        "region_id": exp.region_id,
        "region_name": region_name,
    }
