"""
Admin Regions API routes.

Provides endpoints for:
- Listing regions with optional level/parent filtering
- Getting a single region with its children
- Fetching region hierarchy (state → district → ward tree)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from app.db import get_db
from app.models.models import AdminRegion, Indicator

router = APIRouter(prefix="/api/v1", tags=["Regions"])


@router.get("/regions")
async def list_regions(
    level: Optional[str] = Query(None, description="Filter by level: state, district, ward"),
    parent_id: Optional[int] = Query(None, description="Filter by parent region ID"),
    country_code: Optional[str] = Query(None, description="Filter by country code (e.g. IND)"),
    db: AsyncSession = Depends(get_db)
):
    """
    List admin regions with optional filtering by level, parent, or country.
    Returns flat list — use parent_id to navigate the hierarchy.
    """
    try:
        stmt = select(AdminRegion)

        if level:
            stmt = stmt.where(AdminRegion.level == level)
        if parent_id is not None:
            stmt = stmt.where(AdminRegion.parent_id == parent_id)
        if country_code:
            stmt = stmt.where(AdminRegion.country_code == country_code)

        stmt = stmt.order_by(AdminRegion.level, AdminRegion.name)
        result = await db.execute(stmt)
        regions = result.scalars().all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "level": r.level,
                "country_code": r.country_code,
                "parent_id": r.parent_id,
            }
            for r in regions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list regions: {e}")


@router.get("/regions/{region_id}")
async def get_region_detail(region_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a single region's details, its children, and associated indicators.
    """
    # Fetch the region
    result = await db.execute(
        select(AdminRegion).where(AdminRegion.id == region_id)
    )
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    # Fetch children
    children_result = await db.execute(
        select(AdminRegion)
        .where(AdminRegion.parent_id == region_id)
        .order_by(AdminRegion.name)
    )
    children = children_result.scalars().all()

    # Fetch indicators
    indicators_result = await db.execute(
        select(Indicator).where(Indicator.region_id == region_id)
    )
    indicators = indicators_result.scalars().all()

    return {
        "id": region.id,
        "name": region.name,
        "level": region.level,
        "country_code": region.country_code,
        "parent_id": region.parent_id,
        "children": [
            {
                "id": c.id,
                "name": c.name,
                "level": c.level,
            }
            for c in children
        ],
        "indicators": [
            {
                "key": ind.indicator_key,
                "value": ind.numeric_value,
                "source_year": ind.source_year,
            }
            for ind in indicators
        ],
    }


@router.get("/regions/hierarchy/tree")
async def get_region_hierarchy(
    country_code: Optional[str] = Query("IND", description="Country code to build hierarchy for"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the full region hierarchy as a nested tree structure.
    Useful for populating cascading dropdowns in the frontend.
    """
    try:
        result = await db.execute(
            select(AdminRegion)
            .where(AdminRegion.country_code == country_code)
            .order_by(AdminRegion.level, AdminRegion.name)
        )
        all_regions = result.scalars().all()

        # Build a lookup and nest children
        region_map = {}
        for r in all_regions:
            region_map[r.id] = {
                "id": r.id,
                "name": r.name,
                "level": r.level,
                "children": [],
            }

        roots = []
        for r in all_regions:
            node = region_map[r.id]
            if r.parent_id and r.parent_id in region_map:
                region_map[r.parent_id]["children"].append(node)
            else:
                roots.append(node)

        return roots
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build hierarchy: {e}")
