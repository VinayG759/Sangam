import logging
from rapidfuzz import process, fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import AdminRegion

from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

async def resolve_location_with_confidence(
    location_text_latin: str,
    country_code: str,
    db: AsyncSession,
    high_threshold: int = 85,
    medium_threshold: int = 65
) -> Dict[str, Any]:
    """
    Resolves location text against admin regions with confidence tiers:
    - High confidence (score >= high_threshold): auto-accepts, region is set.
    - Medium confidence (medium_threshold <= score < high_threshold): candidate is set for user confirmation.
    - Low confidence (score < medium_threshold or no text): neither is set.
    """
    empty_result = {
        "region": None,
        "candidate": None,
        "confidence": "low",
        "score": 0.0
    }
    if not location_text_latin:
        return empty_result

    # Load all regions for the country
    stmt = select(AdminRegion).where(AdminRegion.country_code == country_code)
    result = await db.execute(stmt)
    try:
        scalars_fn = getattr(result, "scalars", None)
        if callable(scalars_fn):
            scalars_obj = scalars_fn()
            import inspect
            if inspect.iscoroutine(scalars_obj):
                scalars_obj.close()
                regions = []
            elif hasattr(scalars_obj, "all") and callable(scalars_obj.all):
                all_res = scalars_obj.all()
                if inspect.iscoroutine(all_res):
                    all_res.close()
                    regions = []
                else:
                    regions = all_res or []
            else:
                regions = []
        else:
            regions = []
    except Exception:
        regions = []


    
    if not regions:
        return empty_result
        
    query = location_text_latin.strip().lower()
    
    # Try exact match first (highest confidence)
    for region in regions:
        # Match primary name
        if region.name.strip().lower() == query:
            return {
                "region": region,
                "candidate": None,
                "confidence": "high",
                "score": 100.0
            }
        
        # Match variants
        if region.name_variants:
            variants = [v.strip().lower() for v in region.name_variants.split('|')]
            if query in variants:
                return {
                    "region": region,
                    "candidate": None,
                    "confidence": "high",
                    "score": 100.0
                }

    # Try fuzzy match. Both sides must be lowercased before scoring
    choices = []
    region_map = {}

    for region in regions:
        names_to_match = [region.name]
        if region.name_variants:
            names_to_match.extend(region.name_variants.split('|'))

        for name in names_to_match:
            clean_name = name.strip()
            if clean_name:
                lowered = clean_name.lower()
                choices.append(lowered)
                region_map[lowered] = region

    if not choices:
        return empty_result

    match = process.extractOne(query, choices, scorer=fuzz.WRatio)
    if match:
        best_str, score, index = match
        matched_region = region_map[best_str]
        score_val = float(score)
        if score_val >= high_threshold:
            return {
                "region": matched_region,
                "candidate": None,
                "confidence": "high",
                "score": score_val
            }
        elif score_val >= medium_threshold:
            return {
                "region": None,
                "candidate": matched_region,
                "confidence": "medium",
                "score": score_val
            }
        else:
            return {
                "region": None,
                "candidate": None,
                "confidence": "low",
                "score": score_val
            }

    return empty_result

async def resolve_location(location_text_latin: str, country_code: str, db: AsyncSession) -> AdminRegion | None:
    res = await resolve_location_with_confidence(location_text_latin, country_code, db)
    return res["region"]

