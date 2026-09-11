import logging
from rapidfuzz import process, fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
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
    regions = result.scalars().all()

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


async def resolve_gps_location(
    latitude: float, longitude: float, country_code: str, db: AsyncSession
) -> AdminRegion | None:
    """
    Resolves a raw GPS point to the nearest administrative region with a
    known centroid -- used when a citizen shares their device location
    natively instead of typing a place name.

    Deliberately does NOT rely on clustering_engine.py's own spatial
    fallback (ST_Contains/ST_Distance against AdminRegion.geom): real
    boundary polygons are not populated for Karnataka data, only
    .centroid is, so that fallback silently degrades to "the first ward
    in the table" for every GPS-only report -- arbitrary, not nearest.
    This matches on centroid distance instead, which IS populated.
    """
    stmt = text("""
        SELECT id FROM admin_regions
        WHERE country_code = :country_code AND centroid IS NOT NULL
        ORDER BY ST_Distance(centroid, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) ASC
        LIMIT 1;
    """)
    result = await db.execute(stmt, {"country_code": country_code, "lon": longitude, "lat": latitude})
    row = result.first()
    if not row:
        return None

    region_result = await db.execute(select(AdminRegion).where(AdminRegion.id == row[0]))
    return region_result.scalar_one_or_none()

