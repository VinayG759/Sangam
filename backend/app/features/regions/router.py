"""The active country pack's public settings, and its places (for the report form's picker)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.models import Region

router = APIRouter(prefix="/api/v1", tags=["regions"])


@router.get("/pack")
def pack_info(pack: Pack = Depends(get_pack)):
    settings = get_settings()
    return {
        "country_code": pack.country_code, "country_name": pack.country_name, "currency": pack.currency,
        "currency_symbol": pack.currency_symbol, "languages": pack.languages, "admin_levels": pack.admin_levels,
        "population_label": pack.population.label, "min_distinct_reporters": pack.privacy.min_distinct_reporters,
        "weights": pack.weights.model_dump(),
        "needs": [{"key": n.key, "label": n.label_en, "labels": n.labels} for n in pack.needs],
        "features": {"simulator": settings.FEATURE_SIMULATOR, "export": settings.FEATURE_EXPORT,
                     "web_intake": settings.FEATURE_WEB_INTAKE, "impact": settings.FEATURE_IMPACT},
    }


@router.get("/regions")
def list_regions(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    """Every place below country level, with its parent, for pickers and lookups."""
    regions = db.scalars(select(Region).where(Region.country_code == pack.country_code, Region.level > 0)
                         .order_by(Region.level, Region.name))
    return [{"id": r.id, "name": r.name, "level": r.level, "parent_id": r.parent_id} for r in regions]
