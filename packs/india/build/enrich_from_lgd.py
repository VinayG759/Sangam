"""
Enrich admin_units.csv with Local Government Directory (LGD) codes and the
alternate place names the gazetteer needs.

Source: Local Government Directory, Ministry of Panchayati Raj
        https://lgdirectory.gov.in/
        CSV mirror: https://ckandev.indiadataportal.com/dataset/lgd-codes

Why this matters more than it looks:

The resolver turns a spoken place name into an admin unit. A citizen saying
"Bengaluru" and a dataset saying "Bangalore" must land on the same row, or the
request is dropped from the entire analysis. So `name_variants` is not
decoration -- every variant added is requests rescued.

Three sources of variants are merged here:
  1. the name JJM uses          (often the pre-2014 name, e.g. GULBARGA)
  2. the name LGD uses          (usually the current official name)
  3. a curated rename map       (Karnataka renamed 12 places in 2014)

Usage:
    python enrich_from_lgd.py --state Karnataka
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
RAW = PACK / "raw"

LGD_SOURCE = "Local Government Directory (Ministry of Panchayati Raj)"
LGD_URL = "https://lgdirectory.gov.in/"

# Karnataka's 2014 renames, plus spellings in common use. Left side is any form
# someone might say or write; right side is the current official name.
# These are the variants a global geocoder gets wrong and a local list gets right.
RENAMES = {
    "Bengaluru Urban": ["Bangalore Urban", "Bengaluru", "Bangalore", "ಬೆಂಗಳೂರು"],
    "Bengaluru Rural": ["Bangalore Rural", "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ"],
    "Mysuru": ["Mysore", "ಮೈಸೂರು"],
    "Belagavi": ["Belgaum", "ಬೆಳಗಾವಿ"],
    "Ballari": ["Bellary", "ಬಳ್ಳಾರಿ"],
    "Vijayapura": ["Bijapur", "Vijayapur", "ವಿಜಯಪುರ"],
    "Kalaburagi": ["Gulbarga", "ಕಲಬುರಗಿ"],
    "Shivamogga": ["Shimoga", "ಶಿವಮೊಗ್ಗ"],
    "Tumakuru": ["Tumkur", "ತುಮಕೂರು"],
    "Chikkamagaluru": ["Chikmagalur", "Chickmagalur", "ಚಿಕ್ಕಮಗಳೂರು"],
    "Chamarajanagara": ["Chamarajanagar", "ಚಾಮರಾಜನಗರ"],
    "Bagalkote": ["Bagalkot", "ಬಾಗಲಕೋಟೆ"],
    "Hosapete": ["Hospet"],
    "Hubballi": ["Hubli"],
    "Mangaluru": ["Mangalore", "ಮಂಗಳೂರು"],
    "Dakshina Kannada": ["South Canara", "Dakshin Kannada"],
    "Uttara Kannada": ["North Canara", "Uttar Kannada", "Karwar"],
    "Chitradurga": ["ಚಿತ್ರದುರ್ಗ"],
    "Kolar": ["ಕೋಲಾರ"],
    "Raichur": ["ರಾಯಚೂರು"],
}

UNIT_COLS = [
    "unit_id", "country_code", "level", "name", "name_variants",
    "parent_unit_id", "external_code", "population", "source_name", "source_url",
]


def norm(name: str) -> str:
    """Lowercase, strip punctuation and spacing, for matching only."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def best_match(name: str, candidates: dict[str, dict]) -> dict | None:
    """Exact normalised match first, then close match. None if nothing plausible."""
    key = norm(name)
    if key in candidates:
        return candidates[key]
    close = difflib.get_close_matches(key, list(candidates), n=1, cutoff=0.86)
    return candidates[close[0]] if close else None


def variants_for(*names: str) -> list[str]:
    """Every spelling we know for a place, deduped, official name excluded."""
    out: list[str] = []
    seen = set()
    for name in names:
        for candidate in [name] + RENAMES.get(name.strip(), []):
            candidate = candidate.strip()
            if candidate and norm(candidate) not in seen:
                seen.add(norm(candidate))
                out.append(candidate)
    # also pick up renames keyed the other way round (JJM name -> official)
    for official, alts in RENAMES.items():
        if any(norm(n) == norm(official) for n in names):
            continue
        if any(norm(a) in {norm(n) for n in names} for a in alts):
            if norm(official) not in seen:
                seen.add(norm(official))
                out.append(official)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="Karnataka")
    args = ap.parse_args()

    units = read_csv(PACK / "admin_units.csv")
    lgd_d = [r for r in read_csv(RAW / "lgd_districts.csv")
             if r["state_name"].strip().lower() == args.state.lower()]
    lgd_b = [r for r in read_csv(RAW / "lgd_blocks.csv")
             if r["state_name"].strip().lower() == args.state.lower()]

    print(f"LGD: {len(lgd_d)} districts, {len(lgd_b)} blocks in {args.state}")
    print(f"pack: {sum(1 for u in units if u['level']=='2')} districts, "
          f"{sum(1 for u in units if u['level']=='3')} blocks\n")

    d_index = {norm(r["district_name"]): r for r in lgd_d}
    # blocks are indexed per district so two blocks with the same name don't collide
    b_index: dict[str, dict[str, dict]] = {}
    for r in lgd_b:
        b_index.setdefault(norm(r["district_name"]), {})[norm(r["block_name"])] = r

    by_id = {u["unit_id"]: u for u in units}
    unmatched: list[str] = []
    matched_d = matched_b = 0

    for unit in units:
        level = unit["level"]

        if level == "2":
            hit = best_match(unit["name"], d_index)
            if hit:
                matched_d += 1
                unit["external_code"] = hit["district_code"]
                unit["name_variants"] = "|".join(
                    v for v in variants_for(unit["name"], hit["district_name"])
                    if norm(v) != norm(unit["name"]))
                unit["source_name"] = LGD_SOURCE
                unit["source_url"] = LGD_URL
            else:
                unmatched.append(f"district  {unit['name']}")
                unit["name_variants"] = "|".join(
                    v for v in variants_for(unit["name"]) if norm(v) != norm(unit["name"]))

        elif level == "3":
            parent = by_id.get(unit["parent_unit_id"], {})
            pool = b_index.get(norm(parent.get("name", "")), {})
            # the parent may be known to LGD under its other name
            if not pool:
                for alt in variants_for(parent.get("name", "")):
                    pool = b_index.get(norm(alt), {})
                    if pool:
                        break
            hit = best_match(unit["name"], pool) if pool else None
            if hit:
                matched_b += 1
                unit["external_code"] = hit["block_code"]
                unit["name_variants"] = "|".join(
                    v for v in variants_for(unit["name"], hit["block_name"])
                    if norm(v) != norm(unit["name"]))
                unit["source_name"] = LGD_SOURCE
                unit["source_url"] = LGD_URL
            else:
                unmatched.append(f"block     {parent.get('name','?')} / {unit['name']}")
                unit["name_variants"] = "|".join(
                    v for v in variants_for(unit["name"]) if norm(v) != norm(unit["name"]))

    write_csv(PACK / "admin_units.csv", units, UNIT_COLS)

    n_d = sum(1 for u in units if u["level"] == "2")
    n_b = sum(1 for u in units if u["level"] == "3")
    with_var = sum(1 for u in units if u["name_variants"])
    print(f"districts matched to LGD  {matched_d}/{n_d}")
    print(f"blocks matched to LGD     {matched_b}/{n_b}")
    print(f"units with name variants  {with_var}/{len(units)}")
    if unmatched:
        print(f"\nunmatched ({len(unmatched)}) -- these need a manual variant:")
        for line in unmatched:
            print("  -", line)


if __name__ == "__main__":
    main()
