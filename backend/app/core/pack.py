"""
The country pack: the single seam between code and country.

A pack is a folder under packs/<name>/ containing pack.yaml, need_taxonomy.yaml
and three CSVs. Everything country-specific (languages, needs, weights,
thresholds, which statistic measures which need) comes from here.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.config import get_settings


class Need(BaseModel):
    key: str
    label_en: str
    labels: dict[str, str] = Field(default_factory=dict)  # language code -> label
    examples_en: list[str] = Field(default_factory=list)


class IndicatorRule(BaseModel):
    """Which statistic says how well served a place already is for one need."""

    key: str
    label: str | None = None  # how the statistic is named on screen
    unit: str | None = None  # "percent" lets the engine estimate how many are unserved
    higher_is_better: bool = True
    # At or above this value, official data says the place is served.
    served_threshold: float | None = None
    # Optional older reading of the same statistic, shown as context.
    baseline_key: str | None = None


class CostRule(BaseModel):
    """Planning assumption for the budget simulator. Always labelled as an estimate."""

    per_unit: float
    unit_label: str
    note: str
    source_url: str | None = None


class Weights(BaseModel):
    demand: float = 0.35
    deficit: float = 0.30
    reach: float = 0.15
    coverage: float = 0.20


class Thresholds(BaseModel):
    high_demand_ratio: float = 1.5  # baseline_ratio at/above this = high demand
    location_accept: float = 90  # fuzzy score at/above: accept place name
    location_confirm: float = 75  # fuzzy score at/above: ask "did you mean…?"
    coordinated_similarity: float = 0.97
    daily_reports_per_reporter: int = 10
    emerging_window_days: int = 14
    # Impact of a completed project: compare complaints in the window before completion with the
    # window after it (skipping a grace period while the work settles in).
    impact_window_days: int = 90
    impact_grace_days: int = 30
    impact_change: float = 0.3  # a 30% fall counts as improved, a 30% rise as worsened


class Privacy(BaseModel):
    min_distinct_reporters: int = 5
    media_retention_days: int = 90
    # Encrypted chat IDs are deleted after the update is sent, or after this many days.
    contact_retention_days: int = 180


class Places(BaseModel):
    """How citizens name places in this country."""

    # Admin level (index into admin_levels) citizens may be matched to; deeper = more specific.
    min_match_level: int = 2
    # Words that describe a kind of place rather than name it, in this country's usage.
    generic_words: list[str] = Field(default_factory=list)
    # How the follow-up question asks for a place.
    ask: str = "Which village or town is this about?"


class Population(BaseModel):
    """Which number is the per-capita denominator, and what to call it."""

    indicator: str | None = None  # use this indicator when the region has no population
    label: str = "people"


class Pack(BaseModel):
    name: str
    country_code: str
    country_name: str
    currency: str
    currency_symbol: str
    languages: list[str]
    admin_levels: list[str]
    population: Population = Population()
    places: Places = Places()
    needs: list[Need]
    fallback_need: str = "other"
    indicators: dict[str, IndicatorRule] = Field(default_factory=dict)
    costs: dict[str, CostRule] = Field(default_factory=dict)
    weights: Weights = Weights()
    thresholds: Thresholds = Thresholds()
    privacy: Privacy = Privacy()
    path: Path

    @property
    def need_keys(self) -> list[str]:
        return [n.key for n in self.needs]

    def need(self, key: str) -> Need | None:
        return next((n for n in self.needs if n.key == key), None)


def load_pack(name: str, packs_dir: Path | None = None) -> Pack:
    """Load and validate packs/<name>/pack.yaml + need_taxonomy.yaml. Raises on anything missing."""
    folder = (packs_dir or get_settings().PACKS_DIR) / name
    config_file = folder / "pack.yaml"
    if not config_file.exists():
        raise FileNotFoundError(f"{config_file} does not exist")
    config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    taxonomy_file = folder / "need_taxonomy.yaml"
    taxonomy = yaml.safe_load(taxonomy_file.read_text(encoding="utf-8")) if taxonomy_file.exists() else {}
    needs = []
    for raw in taxonomy.get("needs", []):
        labels = {k.removeprefix("label_"): v for k, v in raw.items() if k.startswith("label_")}
        needs.append(Need(key=raw["key"], label_en=raw["label_en"], labels=labels,
                          examples_en=raw.get("examples_en", [])))

    return Pack(name=name, needs=needs, fallback_need=taxonomy.get("fallback_key", "other"),
                path=folder, **config)


@lru_cache
def get_pack() -> Pack:
    """The pack this deployment serves (ACTIVE_COUNTRY_PACK)."""
    return load_pack(get_settings().ACTIVE_COUNTRY_PACK)
