"""
Load and validate a country pack.

A country is a folder, not a code change. This module is the single seam
between the engine and a country -- everything below it deals in opaque keys
and numbers, and never learns what a "district" or a "municipio" is.

    packs/india/
        pack.yaml               weights, thresholds, privacy, indicator map
        need_taxonomy.yaml      the need types, which constrain Gemini
        admin_units.csv         the geographic spine
        indicators.csv          tall: one row per (place, statistic)
        sanctioned_projects.csv optional; some countries publish it, India does not
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
PACKS_DIR = REPO / "packs"


class PackError(Exception):
    """A pack is missing something the engine needs, or contradicts itself."""


@dataclass(frozen=True)
class AdminUnit:
    unit_id: str
    country_code: str
    level: int
    name: str
    name_variants: tuple[str, ...]
    parent_unit_id: str | None
    external_code: str | None
    population: int | None

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name,) + self.name_variants


@dataclass(frozen=True)
class Indicator:
    unit_id: str
    indicator_key: str
    value: float
    unit: str | None
    period: str | None
    source_name: str | None
    source_url: str | None


@dataclass
class Pack:
    country_code: str
    name: str
    currency: str
    languages: list[str]
    admin_levels: list[str]
    indicator_map: dict[str, str]
    weights: dict[str, float]
    thresholds: dict[str, float]
    privacy: dict[str, Any]
    coverage_applies_to_status: list[str]
    need_types: list[str]
    fallback_need: str
    units: dict[str, AdminUnit] = field(default_factory=dict)
    indicators: list[Indicator] = field(default_factory=list)

    # -- convenience lookups -------------------------------------------------

    def units_at_level(self, level: int) -> list[AdminUnit]:
        return [u for u in self.units.values() if u.level == level]

    def indicator(self, unit_id: str, key: str) -> float | None:
        for ind in self.indicators:
            if ind.unit_id == unit_id and ind.indicator_key == key:
                return ind.value
        return None

    def indicator_index(self) -> dict[tuple[str, str], Indicator]:
        """(unit_id, indicator_key) -> Indicator. Build once, reuse."""
        return {(i.unit_id, i.indicator_key): i for i in self.indicators}

    def deficit_indicator_for(self, need_type: str) -> str | None:
        """Which statistic measures 'how well served is this place already'."""
        return self.indicator_map.get(need_type)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise PackError(f"missing {path.name} in {path.parent}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _int_or_none(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def load(country: str, packs_dir: Path | None = None) -> Pack:
    """Load a pack by folder name, e.g. load("india")."""
    root = (packs_dir or PACKS_DIR) / country
    if not root.is_dir():
        raise PackError(f"no pack at {root}")

    cfg = _read_yaml(root / "pack.yaml")
    tax = _read_yaml(root / "need_taxonomy.yaml")

    need_types = [n["key"] for n in tax.get("needs", [])]
    fallback = tax.get("fallback_key", "other")
    if not need_types:
        raise PackError(f"{country}: need_taxonomy.yaml defines no needs")
    if fallback not in need_types:
        need_types = need_types + [fallback]

    for required in ("country_code", "weights", "thresholds", "indicator_map"):
        if required not in cfg:
            raise PackError(f"{country}: pack.yaml is missing '{required}'")

    pack = Pack(
        country_code=cfg["country_code"],
        name=cfg.get("name", country.title()),
        currency=cfg.get("currency", ""),
        languages=cfg.get("languages", []),
        admin_levels=cfg.get("admin_levels", []),
        indicator_map=cfg["indicator_map"],
        weights=cfg["weights"],
        thresholds=cfg["thresholds"],
        privacy=cfg.get("privacy", {}),
        coverage_applies_to_status=cfg.get("coverage_applies_to_status", ["completed"]),
        need_types=need_types,
        fallback_need=fallback,
    )

    for row in _read_csv(root / "admin_units.csv"):
        variants = tuple(
            v.strip() for v in (row.get("name_variants") or "").split("|") if v.strip()
        )
        unit = AdminUnit(
            unit_id=row["unit_id"].strip(),
            country_code=row["country_code"].strip(),
            level=int(row["level"]),
            name=row["name"].strip(),
            name_variants=variants,
            parent_unit_id=(row.get("parent_unit_id") or "").strip() or None,
            external_code=(row.get("external_code") or "").strip() or None,
            population=_int_or_none(row.get("population")),
        )
        pack.units[unit.unit_id] = unit

    for row in _read_csv(root / "indicators.csv"):
        try:
            value = float(row["value"])
        except (KeyError, ValueError):
            continue
        pack.indicators.append(Indicator(
            unit_id=row["unit_id"].strip(),
            indicator_key=row["indicator_key"].strip(),
            value=value,
            unit=(row.get("unit") or "").strip() or None,
            period=(row.get("period") or "").strip() or None,
            source_name=(row.get("source_name") or "").strip() or None,
            source_url=(row.get("source_url") or "").strip() or None,
        ))

    return pack


def validate(pack: Pack) -> list[str]:
    """
    Check a pack before the engine will use it. Returns a list of problems --
    empty means good. Catches bad data at the door rather than at demo time.
    """
    problems: list[str] = []

    weight_keys = {"demand", "deficit", "reach", "coverage"}
    missing = weight_keys - set(pack.weights)
    if missing:
        problems.append(f"weights missing: {sorted(missing)}")

    if not pack.units:
        problems.append("admin_units.csv is empty")

    # every parent must exist, or the tree is broken
    for unit in pack.units.values():
        if unit.parent_unit_id and unit.parent_unit_id not in pack.units:
            # the country row's parent is allowed to be absent
            if unit.level > 1:
                problems.append(
                    f"{unit.unit_id}: parent {unit.parent_unit_id} not in pack")

    # every indicator must attach to a known unit
    known = set(pack.units)
    orphans = {i.unit_id for i in pack.indicators} - known
    if orphans:
        problems.append(f"{len(orphans)} indicator rows reference unknown units, "
                        f"e.g. {sorted(orphans)[:3]}")

    # every need type must map to an indicator that actually has data
    have_keys = {i.indicator_key for i in pack.indicators}
    for need in pack.need_types:
        if need == pack.fallback_need:
            continue
        key = pack.indicator_map.get(need)
        if not key:
            problems.append(f"need '{need}' has no indicator_map entry")
        elif key not in have_keys:
            problems.append(f"need '{need}' maps to '{key}', which has no rows")

    # provenance is not optional
    unsourced = sum(1 for i in pack.indicators if not i.source_url)
    if unsourced:
        problems.append(f"{unsourced} indicator rows have no source_url")

    return problems


def coverage_report(pack: Pack) -> dict[str, Any]:
    """What we actually have. Goes straight into the pitch, so keep it honest."""
    by_level: dict[int, int] = {}
    for unit in pack.units.values():
        by_level[unit.level] = by_level.get(unit.level, 0) + 1

    keys: dict[str, int] = {}
    for ind in pack.indicators:
        keys[ind.indicator_key] = keys.get(ind.indicator_key, 0) + 1

    return {
        "country": pack.country_code,
        "units_by_level": dict(sorted(by_level.items())),
        "indicator_rows": len(pack.indicators),
        "indicator_keys": dict(sorted(keys.items())),
        "units_with_variants": sum(1 for u in pack.units.values() if u.name_variants),
    }
