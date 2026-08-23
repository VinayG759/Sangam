"""
Pure mapping functions from packs/india/*.csv (real Jal Jeevan Mission +
Local Government Directory data) to the shape backend/app/models/models.py
expects.

Kept separate from load_real_data.py deliberately: these functions touch no
database session, so they can be unit-tested without Postgres, PostGIS, or
Docker being available -- exactly the same reasoning that keeps scoring_engine
and verifier as pure functions. If this logic is wrong, a test catches it
before a single row is written to a real database.

Resolves the pack-format fork: packs/india/ has real sourced data (259 admin
units, 1230 indicator rows) but its own schema; packs/india_karnataka/pack.yaml
is what the running backend actually reads for config (languages, sectors,
scoring weights), and has no data files at all. Rather than reconcile two
YAML shapes, this module treats packs/india_karnataka/pack.yaml as the
schema of record for CONFIG (unchanged) and imports packs/india's real
numbers into the database tables config already points at (AdminRegion,
Indicator) -- which is what those CSVs were always meant to become.
"""

from __future__ import annotations

from typing import Any

# admin_units.csv encodes level as an integer (0 country, 1 state, 2 district,
# 3 block). The backend's AdminRegion.level is a free-text string, and
# clustering_engine.py's spatial join is hardcoded to look for level=="ward"
# (that hardcoding predates this import and is left alone here -- changing it
# is a separate decision). Mapping block -> "ward" means real Karnataka data
# flows through that already-fixed spatial query unchanged.
LEVEL_MAP = {
    "0": "country",
    "1": "state",
    "2": "district",
    "3": "ward",
}

# The one genuine naming mismatch between the two packs: packs/india's need
# taxonomy uses singular sector keys, packs/india_karnataka/pack.yaml (which
# the backend's Pydantic CountryPack model validates against) uses "roads".
# Indicator keys are free text with no enum constraint, so this only matters
# where a sector key must match the pack's configured sector list.
SECTOR_KEY_MAP = {
    "road": "roads",
}

# packs/india/admin_units.csv encodes country_code as ISO 3166-1 alpha-2
# ("IN"), but pack.yaml, db_seed.py, and every route's default filter use
# alpha-3 ("IND"). Left unmapped, every real AdminRegion imports as "IN" and
# location_resolver.py's country_code filter -- which is always given "IND"
# by the pack config -- matches zero of them, silently breaking location
# resolution for all real data.
COUNTRY_CODE_MAP = {
    "IN": "IND",
}


class RowMappingError(ValueError):
    """A CSV row could not be mapped -- malformed, not a defect to silently drop."""


def map_admin_unit_row(row: dict[str, str]) -> dict[str, Any]:
    """
    One packs/india/admin_units.csv row -> kwargs for AdminRegion(**kwargs),
    minus parent_id (resolved by the caller, which knows the unit_id -> id map
    built so far -- this function has no database access).
    """
    unit_id = (row.get("unit_id") or "").strip()
    level_raw = (row.get("level") or "").strip()
    name = (row.get("name") or "").strip()

    if not unit_id:
        raise RowMappingError("admin_units row has no unit_id")
    if not name:
        raise RowMappingError(f"{unit_id}: no name")
    if level_raw not in LEVEL_MAP:
        raise RowMappingError(f"{unit_id}: unknown level {level_raw!r}")

    return {
        "external_id": unit_id,
        "country_code": normalize_country_code((row.get("country_code") or "").strip()),
        "name": name,
        "name_variants": (row.get("name_variants") or "").strip() or None,
        "level": LEVEL_MAP[level_raw],
        "parent_external_id": (row.get("parent_unit_id") or "").strip() or None,
        # geom intentionally omitted: no boundary polygons exist yet for
        # Karnataka blocks (packs/india/admin_units.csv never had a
        # boundaries.geojson pass run against it). Regions import with
        # geom=NULL. clustering_engine.py's nearest-ward query already
        # degrades safely when no polygon matches -- it logs a warning and
        # falls back rather than crashing -- but real citizen reports cannot
        # be spatially attributed to a real ward until boundaries exist. This
        # is a known gap, not a silent one.
    }


def map_indicator_row(row: dict[str, str]) -> dict[str, Any]:
    """
    One packs/india/indicators.csv row -> kwargs for Indicator(**kwargs),
    minus region_id (resolved by the caller via unit_id -> AdminRegion.id).
    """
    unit_id = (row.get("unit_id") or "").strip()
    indicator_key = (row.get("indicator_key") or "").strip()
    value_raw = (row.get("value") or "").strip()

    if not unit_id:
        raise RowMappingError("indicators row has no unit_id")
    if not indicator_key:
        raise RowMappingError(f"{unit_id}: no indicator_key")

    try:
        numeric_value = float(value_raw)
    except ValueError as exc:
        raise RowMappingError(f"{unit_id}/{indicator_key}: bad value {value_raw!r}") from exc

    period = (row.get("period") or "").strip()
    try:
        source_year = int(period)
    except ValueError:
        # Some periods may not be a clean year (e.g. blank). A missing year
        # is a data-quality fact worth keeping visible, not a reason to
        # invent one -- fall back to 0 rather than guessing.
        source_year = 0

    return {
        "region_external_id": unit_id,
        "indicator_key": indicator_key,
        "numeric_value": numeric_value,
        "source_year": source_year,
        "source_name": (row.get("source_name") or "").strip() or None,
        "source_url": (row.get("source_url") or "").strip() or None,
    }


def normalize_sector_key(key: str) -> str:
    """Apply the one known sector-key translation between the two packs."""
    key = key.strip()
    return SECTOR_KEY_MAP.get(key, key)


def normalize_country_code(code: str) -> str:
    """Map admin_units.csv's alpha-2 country_code to the app-wide alpha-3 convention."""
    code = code.strip()
    if not code:
        return "IND"
    return COUNTRY_CODE_MAP.get(code, code)


def households_to_population_estimate(rural_households: float) -> int:
    """
    packs/india/admin_units.csv has no population column -- the JJM fetcher
    only ever had household counts, never headcounts, and LGD enrichment
    never touched population either. Per-capita scoring needs *some*
    denominator, so this uses the household count directly rather than
    multiplying by an assumed household size.

    This is a deliberate choice, not an oversight: multiplying by a national
    average household size would manufacture a headcount that looks precise
    but is not sourced. The household count itself is real and sourced. Using
    it directly changes the absolute per-capita number's meaning slightly
    (per 1,000 households rather than per 1,000 people) but preserves the
    property that actually matters -- relative ranking across regions of
    different size stays correct, which is what the Bengaluru-vs-Kolar
    demonstration depends on.
    """
    return int(round(rural_households))
