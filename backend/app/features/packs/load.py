"""
Imports a validated pack's CSVs into regions / indicators / projects.
Idempotent: rows are upserted by their pack IDs, so re-running is safe.
"""

from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.pack import load_pack
from app.features.packs.validate import read_csv, validate_pack
from app.models import Indicator, Project, Region


def _num(value: str) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def _date(value: str) -> date | None:
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


def load_pack_into_db(db: Session, name: str) -> dict[str, int]:
    problems = validate_pack(name)
    if problems:
        raise ValueError("pack is invalid:\n  " + "\n  ".join(problems))
    pack = load_pack(name)

    centroids: dict[str, tuple[float, float]] = {}
    centroid_file = pack.path / "admin_centroids.csv"
    if centroid_file.exists():
        for row in read_csv(centroid_file)[1]:
            centroids[row["external_code"]] = (float(row["centroid_lat"]), float(row["centroid_lon"]))

    _, admin_rows = read_csv(pack.path / "admin_units.csv")
    region_rows = [{
        "id": pack.country_code, "country_code": pack.country_code, "level": 0, "name": pack.country_name,
        "name_variants": [], "parent_id": None, "external_code": None, "population": None,
        "lat": None, "lon": None, "source_name": None, "source_url": None,
    }]
    for row in admin_rows:
        if row["unit_id"] == pack.country_code:
            continue
        lat, lon = centroids.get(row["external_code"].strip(), (None, None))
        variants = [v.strip() for v in row["name_variants"].split("|") if v.strip()]
        population = _num(row["population"])
        region_rows.append({
            "id": row["unit_id"], "country_code": pack.country_code, "level": int(row["level"]),
            "name": row["name"].strip(), "name_variants": variants,
            "parent_id": row["parent_unit_id"].strip() or pack.country_code,
            "external_code": row["external_code"].strip() or None,
            "population": int(population) if population else None, "lat": lat, "lon": lon,
            "source_name": row["source_name"] or None, "source_url": row["source_url"] or None,
        })
    # Parents before children, so the foreign key is always satisfied.
    region_rows.sort(key=lambda r: r["level"])
    for row in region_rows:
        stmt = insert(Region).values(**row)
        db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={k: stmt.excluded[k] for k in row if k != "id"}))

    _, indicator_rows = read_csv(pack.path / "indicators.csv")
    for row in indicator_rows:
        values = {"region_id": row["unit_id"], "key": row["indicator_key"], "value": float(row["value"]),
                  "unit": row["unit"] or None, "period": row["period"], "source_name": row["source_name"],
                  "source_url": row["source_url"] or None}
        stmt = insert(Indicator).values(**values)
        db.execute(stmt.on_conflict_do_update(
            index_elements=["region_id", "key", "period"],
            set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit,
                  "source_name": stmt.excluded.source_name, "source_url": stmt.excluded.source_url}))

    _, project_rows = read_csv(pack.path / "sanctioned_projects.csv")
    for row in project_rows:
        values = {"id": row["project_id"], "region_id": row["unit_id"], "sector": row["sector"],
                  "title": row["title"], "amount": _num(row["amount"]), "currency": row["currency"] or None,
                  "status": row["status"], "sanctioned_date": _date(row["sanctioned_date"]),
                  "completion_date": _date(row["completion_date"]), "source_name": row["source_name"],
                  "source_url": row["source_url"] or None}
        stmt = insert(Project).values(**values)
        db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={k: stmt.excluded[k] for k in values if k != "id"}))

    db.commit()
    return {"regions": len(region_rows), "indicators": len(indicator_rows), "projects": len(project_rows)}
