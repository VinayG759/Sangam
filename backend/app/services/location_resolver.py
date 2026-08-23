import logging
from rapidfuzz import process, fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import AdminRegion

logger = logging.getLogger(__name__)

async def resolve_location(location_text_latin: str, country_code: str, db: AsyncSession) -> AdminRegion | None:
    if not location_text_latin:
        return None

    # Load all regions for the country
    stmt = select(AdminRegion).where(AdminRegion.country_code == country_code)
    result = await db.execute(stmt)
    regions = result.scalars().all()
    
    if not regions:
        return None
        
    query = location_text_latin.strip().lower()
    
    # Try exact match first
    for region in regions:
        # Match primary name
        if region.name.strip().lower() == query:
            return region
        
        # Match variants
        if region.name_variants:
            variants = [v.strip().lower() for v in region.name_variants.split('|')]
            if query in variants:
                return region

    # Try fuzzy match. Both sides must be lowercased before scoring --
    # WRatio is not case-insensitive on its own, and a real mismatch like
    # "hiriyur market" vs "Hiriyur" scores 77 (mixed case) vs 90 (matched
    # case), which silently falls under the threshold below and drops a
    # resolvable location. Found by re-running the real retry pipeline
    # against real Gemini output, not by unit tests -- the existing test
    # fixtures happened to use case that already matched.
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
                # Keep mapping to region object
                region_map[lowered] = region

    if not choices:
        return None

    match = process.extractOne(query, choices, scorer=fuzz.WRatio)
    if match:
        best_str, score, index = match
        if score >= 85: # Threshold for a good fuzzy match
            return region_map[best_str]

    return None
