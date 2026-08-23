"""
Load real Karnataka data from packs/india/*.csv into AdminRegion and
Indicator -- the tables the running backend actually reads.

This resolves the pack-format fork: packs/india/ has real government data
(Jal Jeevan Mission tap-water coverage, Local Government Directory codes)
sourced across two earlier sessions, but the backend was wired to read
packs/india_karnataka/pack.yaml for config, which has no data files. Rather
than reconcile two YAML shapes, packs/india_karnataka/pack.yaml stays the
schema of record for CONFIG (languages, sectors, scoring weights -- unchanged
by this script) and this script imports packs/india's real numbers into the
database tables that config already points at.

Idempotent: re-running this after fetch_jjm_coverage.py or enrich_from_lgd.py
produce updated CSVs updates existing rows (matched by external_id) rather
than duplicating them.

Usage:
    python -m app.utils.load_real_data
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.models import AdminRegion, Indicator
from app.utils.real_data_mapping import (
    RowMappingError,
    households_to_population_estimate,
    map_admin_unit_row,
    map_indicator_row,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_DIR = REPO_ROOT / "packs" / "india"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"expected real data at {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_admin_regions(db: Session, rows: list[dict[str, str]], centroid_rows: list[dict[str, str]]) -> dict[str, int]:
    """
    Insert or update AdminRegion rows. Returns unit_id -> AdminRegion.id.

    admin_units.csv lists parents before children (state, then each
    district, then that district's blocks), so a single top-to-bottom pass
    can resolve parent_id from the map built so far without a second pass.
    """
    centroids = {r["external_code"]: (float(r["centroid_lat"]), float(r["centroid_lon"])) for r in centroid_rows}
    
    existing = {r.external_id: r for r in db.query(AdminRegion).filter(
        AdminRegion.external_id.isnot(None)).all()}
    id_by_external: dict[str, int] = {ext: r.id for ext, r in existing.items()}

    created = updated = skipped = 0
    for row in rows:
        try:
            mapped = map_admin_unit_row(row)
        except RowMappingError as exc:
            logger.warning("admin_units row skipped: %s", exc)
            skipped += 1
            continue

        parent_ext = mapped.pop("parent_external_id")
        parent_id = id_by_external.get(parent_ext) if parent_ext else None
        if parent_ext and parent_id is None:
            logger.warning(
                "%s: parent %s not yet imported -- inserting with no parent. "
                "Check admin_units.csv ordering.", mapped["external_id"], parent_ext,
            )

        ext_id = mapped["external_id"]

        # Note: admin_centroids.csv is keyed by external_code (the pack's
        # numeric LGD code, e.g. "5811"), not external_id (the hierarchical
        # unit_id, e.g. "IN-KA-CHITRADURGA-HIRIYUR") -- these are two
        # different identifiers and must not be conflated.
        ext_code = (row.get("external_code") or "").strip()
        if ext_code and ext_code in centroids:
            lat, lon = centroids[ext_code]
            mapped["centroid"] = f"SRID=4326;POINT({lon} {lat})"

        region = existing.get(ext_id)
        if region is None:
            region = AdminRegion(**mapped, parent_id=parent_id)
            db.add(region)
            db.flush()  # need region.id before children can reference it
            created += 1
        else:
            for k, v in mapped.items():
                setattr(region, k, v)
            region.parent_id = parent_id
            updated += 1

        id_by_external[ext_id] = region.id
        existing[ext_id] = region

    db.commit()
    logger.info("admin_regions: %d created, %d updated, %d skipped", created, updated, skipped)
    return id_by_external


def load_indicators(db: Session, rows: list[dict[str, str]], region_ids: dict[str, int]) -> None:
    """
    Insert or update Indicator rows, matched on (region_id, indicator_key).
    Also back-fills AdminRegion.population from demography.rural_households --
    see households_to_population_estimate for why this proxy is used and what
    it does and does not claim.
    """
    existing_keys = {
        (i.region_id, i.indicator_key)
        for i in db.query(Indicator.region_id, Indicator.indicator_key).all()
    }

    created = updated = skipped = 0
    population_updates: dict[int, float] = {}

    for row in rows:
        try:
            mapped = map_indicator_row(row)
        except RowMappingError as exc:
            logger.warning("indicators row skipped: %s", exc)
            skipped += 1
            continue

        region_id = region_ids.get(mapped.pop("region_external_id"))
        if region_id is None:
            logger.warning(
                "indicator %s references unimported region -- skipped",
                mapped["indicator_key"],
            )
            skipped += 1
            continue

        key = (region_id, mapped["indicator_key"])
        if key in existing_keys:
            db.query(Indicator).filter(
                Indicator.region_id == region_id,
                Indicator.indicator_key == mapped["indicator_key"],
            ).update(mapped)
            updated += 1
        else:
            db.add(Indicator(region_id=region_id, **mapped))
            existing_keys.add(key)
            created += 1

        if mapped["indicator_key"] == "demography.rural_households":
            population_updates[region_id] = mapped["numeric_value"]

    db.commit()

    for region_id, households in population_updates.items():
        db.query(AdminRegion).filter(AdminRegion.id == region_id).update(
            {"population": households_to_population_estimate(households)}
        )
    db.commit()

    logger.info(
        "indicators: %d created, %d updated, %d skipped; population back-filled for %d regions",
        created, updated, skipped, len(population_updates),
    )


def load_real_data() -> None:
    admin_rows = _read_csv(PACK_DIR / "admin_units.csv")
    try:
        centroid_rows = _read_csv(PACK_DIR / "admin_centroids.csv")
    except FileNotFoundError:
        logger.warning("admin_centroids.csv not found, centroids will be left NULL")
        centroid_rows = []
        
    indicator_rows = _read_csv(PACK_DIR / "indicators.csv")
    logger.info(
        "read %d admin_units rows, %d indicator rows from %s",
        len(admin_rows), len(indicator_rows), PACK_DIR,
    )

    db = SessionLocal()
    try:
        region_ids = load_admin_regions(db, admin_rows, centroid_rows)
        load_indicators(db, indicator_rows, region_ids)
        logger.info("Real Karnataka data loaded successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    load_real_data()
