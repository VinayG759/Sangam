import os
import sys
import yaml
from pathlib import Path
from typing import Optional, Tuple
from pydantic import ValidationError

from app.config import settings
from app.services.pack_loader import CountryPack


def resolve_pack_path(pack_name_or_path: str) -> Optional[Path]:
    """
    Resolves a pack name, pack directory, or pack.yaml path to an existing Path.
    """
    candidate = Path(pack_name_or_path)

    # Case 1: Direct path to pack.yaml file
    if candidate.is_file():
        return candidate

    # Case 2: Direct path to directory containing pack.yaml
    if candidate.is_dir() and (candidate / "pack.yaml").is_file():
        return candidate / "pack.yaml"

    # Case 3: Pack name under settings.PACKS_DIR
    packs_dir = Path(settings.PACKS_DIR)
    in_packs = packs_dir / pack_name_or_path / "pack.yaml"
    if in_packs.is_file():
        return in_packs

    # Case 4: Pack name under repo root packs/ if different
    repo_packs = Path(__file__).resolve().parents[3] / "packs" / pack_name_or_path / "pack.yaml"
    if repo_packs.is_file():
        return repo_packs

    return None


def validate_pack(pack_name_or_path: str) -> Tuple[bool, str]:
    """
    Validates a country pack against the CountryPack Pydantic schema.
    Returns (is_valid, message).
    """
    pack_file = resolve_pack_path(pack_name_or_path)
    if not pack_file:
        return False, f"Pack file could not be found for '{pack_name_or_path}'."

    try:
        with open(pack_file, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except Exception as e:
        return False, f"Failed to parse YAML from {pack_file}: {e}"

    if not isinstance(raw_data, dict):
        return False, f"Pack content in {pack_file} must be a YAML mapping (dictionary)."

    try:
        pack = CountryPack(**raw_data)
        langs = ", ".join(l.code for l in pack.languages)
        sectors = ", ".join(s.key for s in pack.sectors)
        summary = (
            f"[PASS] Country pack '{pack_name_or_path}' is valid.\n"
            f"  Path: {pack_file}\n"
            f"  Country: {pack.country_code} ({pack.region_name})\n"
            f"  Languages ({len(pack.languages)}): {langs}\n"
            f"  Sectors ({len(pack.sectors)}): {sectors}\n"
            f"  Weights: demand_density={pack.weights.demand_density}, "
            f"vulnerability_index={pack.weights.vulnerability_index}, "
            f"expenditure_gap={pack.weights.expenditure_gap}, "
            f"urgency={pack.weights.urgency}"
        )
        return True, summary
    except ValidationError as ve:
        return False, f"[FAIL] Country pack '{pack_name_or_path}' failed schema validation:\n{ve}"
    except Exception as e:
        return False, f"[FAIL] Country pack '{pack_name_or_path}' encountered error: {e}"


def main() -> int:
    if len(sys.argv) < 2:
        pack_target = "india_karnataka"
        print(f"No pack specified; defaulting to '{pack_target}'...")
    else:
        pack_target = sys.argv[1]

    is_valid, msg = validate_pack(pack_target)
    print(msg)
    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
