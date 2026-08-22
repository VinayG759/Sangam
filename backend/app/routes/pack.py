"""
Pack configuration API routes.

Provides endpoints for:
- Getting the active country pack info (languages, sectors, weights)
"""

from fastapi import APIRouter, HTTPException
from app.services.pack_loader import pack_loader

router = APIRouter(prefix="/api/v1", tags=["Configuration"])


@router.get("/pack")
async def get_active_pack():
    """
    Returns the active country pack configuration.
    Includes supported languages, tracked sectors, and priority scoring weights.
    Used by the frontend for populating dropdowns, sector filters, and weight sliders.
    """
    try:
        pack = pack_loader.load_active_pack()
        return {
            "country_code": pack.country_code,
            "region_name": pack.region_name,
            "languages": [
                {
                    "code": lang.code,
                    "name": lang.name,
                    "is_default": lang.is_default,
                }
                for lang in pack.languages
            ],
            "sectors": [
                {
                    "key": sector.key,
                    "name": sector.name,
                }
                for sector in pack.sectors
            ],
            "weights": {
                "demand_density": pack.weights.demand_density,
                "vulnerability_index": pack.weights.vulnerability_index,
                "expenditure_gap": pack.weights.expenditure_gap,
                "urgency": pack.weights.urgency,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load pack: {e}")
