"""
Checks a country pack folder is complete and consistent before the engine
will load it. Returns a list of problems; empty means valid.
"""

import csv
from pathlib import Path

from app.core.pack import load_pack

ADMIN_COLUMNS = ["unit_id", "country_code", "level", "name", "name_variants", "parent_unit_id",
                 "external_code", "population", "source_name", "source_url"]
INDICATOR_COLUMNS = ["unit_id", "indicator_key", "value", "unit", "period", "source_name", "source_url"]
PROJECT_COLUMNS = ["project_id", "unit_id", "sector", "title", "amount", "currency", "status",
                   "sanctioned_date", "completion_date", "source_name", "source_url"]
PROJECT_STATUSES = {"planned", "sanctioned", "in_progress", "completed", "stalled"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def validate_pack(name: str, packs_dir: Path | None = None) -> list[str]:
    try:
        pack = load_pack(name, packs_dir)
    except Exception as exc:
        return [f"pack.yaml: {exc}"]

    problems: list[str] = []
    if not pack.needs:
        problems.append("need_taxonomy.yaml: no needs defined")
    for need_key in list(pack.indicators) + list(pack.costs):
        if need_key not in pack.need_keys:
            problems.append(f"pack.yaml: '{need_key}' is not a need in need_taxonomy.yaml")
    weights = pack.weights
    if any(w < 0 for w in (weights.demand, weights.deficit, weights.reach, weights.coverage)):
        problems.append("pack.yaml: weights must not be negative (coverage is subtracted by the engine)")

    files = {"admin_units.csv": ADMIN_COLUMNS, "indicators.csv": INDICATOR_COLUMNS,
             "sanctioned_projects.csv": PROJECT_COLUMNS}
    rows: dict[str, list[dict[str, str]]] = {}
    for filename, expected in files.items():
        path = pack.path / filename
        if not path.exists():
            problems.append(f"{filename}: missing")
            continue
        header, rows[filename] = read_csv(path)
        missing = [c for c in expected if c not in header]
        if missing:
            problems.append(f"{filename}: missing columns {missing}")
    if problems:
        return problems

    unit_ids: set[str] = set()
    for i, row in enumerate(rows["admin_units.csv"], start=2):
        uid = row["unit_id"].strip()
        if not uid or not row["name"].strip():
            problems.append(f"admin_units.csv line {i}: unit_id and name are required")
        if uid in unit_ids:
            problems.append(f"admin_units.csv line {i}: duplicate unit_id {uid}")
        unit_ids.add(uid)
        if row["country_code"].strip() != pack.country_code:
            problems.append(f"admin_units.csv line {i}: country_code {row['country_code']!r} != {pack.country_code}")
        if not row["level"].strip().isdigit() or int(row["level"]) >= len(pack.admin_levels):
            problems.append(f"admin_units.csv line {i}: level must be 0..{len(pack.admin_levels) - 1}")
    for i, row in enumerate(rows["admin_units.csv"], start=2):
        parent = row["parent_unit_id"].strip()
        if parent and parent not in unit_ids and parent != pack.country_code:
            problems.append(f"admin_units.csv line {i}: parent {parent} not found")

    for i, row in enumerate(rows["indicators.csv"], start=2):
        if row["unit_id"] not in unit_ids:
            problems.append(f"indicators.csv line {i}: unknown unit_id {row['unit_id']}")
        try:
            float(row["value"])
        except ValueError:
            problems.append(f"indicators.csv line {i}: value {row['value']!r} is not a number")
        if not row["source_name"].strip():
            problems.append(f"indicators.csv line {i}: every number needs a source_name")

    for i, row in enumerate(rows["sanctioned_projects.csv"], start=2):
        if row["unit_id"] not in unit_ids:
            problems.append(f"sanctioned_projects.csv line {i}: unknown unit_id {row['unit_id']}")
        if row["sector"] not in pack.need_keys:
            problems.append(f"sanctioned_projects.csv line {i}: sector {row['sector']!r} is not a need key")
        if row["status"] not in PROJECT_STATUSES:
            problems.append(f"sanctioned_projects.csv line {i}: status must be one of {sorted(PROJECT_STATUSES)}")
        if not row["source_name"].strip():
            problems.append(f"sanctioned_projects.csv line {i}: every project needs a source_name")

    return problems
