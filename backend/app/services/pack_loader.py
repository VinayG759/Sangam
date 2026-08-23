import os
import logging
import yaml
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class LanguageConfig(BaseModel):
    code: str
    name: str
    is_default: bool = False


class SectorConfig(BaseModel):
    key: str
    name: str


class WeightsConfig(BaseModel):
    """
    Priority scoring weights. These should sum to 1.0 for a properly
    normalized score, but the engine clamps the output regardless.
    """
    demand_density: float = Field(0.35, ge=0.0, le=1.0, description="Weight for cluster reports density")
    vulnerability_index: float = Field(0.35, ge=0.0, le=1.0, description="Weight for region vulnerability")
    expenditure_gap: float = Field(0.20, ge=0.0, le=1.0, description="Weight for unallocated budget gap")
    urgency: float = Field(0.10, ge=0.0, le=1.0, description="Weight for citizen reported urgency")

    @field_validator("urgency")
    @classmethod
    def weights_should_sum_to_one(cls, v, info):
        """Warn if weights don't sum to ~1.0 (they still work, just un-normalized)."""
        data = info.data
        total = data.get("demand_density", 0) + data.get("vulnerability_index", 0) + data.get("expenditure_gap", 0) + v
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"Pack weights sum to {total:.3f} instead of 1.0. "
                "Scores will still be clamped to [0, 100] but may not use the full range."
            )
        return v


class CountryPack(BaseModel):
    """
    A country/region configuration pack that defines:
    - Supported languages
    - Infrastructure sectors tracked
    - Priority scoring weights
    """
    country_code: str
    region_name: str = "General"
    languages: List[LanguageConfig]
    sectors: List[SectorConfig]
    weights: WeightsConfig
    # Privacy floor override (see scoring_engine.DEFAULT_MIN_DISTINCT_REPORTERS
    # and docs/DECISIONS.md #9). None means "use the engine's default" -- this
    # field previously didn't exist on the model, so scoring_engine.py's
    # getattr(pack, "min_distinct_reporters", None) always silently returned
    # None regardless of what a pack.yaml set, since Pydantic models reject
    # undeclared attributes rather than falling through to getattr's default.
    min_distinct_reporters: Optional[int] = None


class PackLoader:
    """
    Singleton loader for country pack configurations.

    Packs are YAML files stored under settings.PACKS_DIR/<pack_name>/pack.yaml.
    The active pack is determined by settings.ACTIVE_COUNTRY_PACK.
    Falls back to the 'default' pack if the specified pack is not found.
    """
    _instance = None
    _cached_pack = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PackLoader, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def load_active_pack(self) -> CountryPack:
        """
        Load and cache the active country pack configuration.

        Returns:
            CountryPack: The validated pack configuration.

        Raises:
            FileNotFoundError: If neither the active pack nor the default pack exists.
            ValueError: If the YAML content fails Pydantic validation.
        """
        if self._cached_pack:
            return self._cached_pack

        pack_name = settings.ACTIVE_COUNTRY_PACK
        pack_path = os.path.join(settings.PACKS_DIR, pack_name, "pack.yaml")

        # Fallback to default if not found
        if not os.path.exists(pack_path):
            logger.warning(
                f"Pack '{pack_name}' not found at '{pack_path}'. Falling back to 'default' pack."
            )
            pack_path = os.path.join(settings.PACKS_DIR, "default", "pack.yaml")

        if not os.path.exists(pack_path):
            raise FileNotFoundError(
                f"Active pack config not found at '{pack_path}' and default pack is missing. "
                f"Create a pack.yaml file in '{settings.PACKS_DIR}/{pack_name}/' or "
                f"'{settings.PACKS_DIR}/default/'."
            )

        logger.info(f"Loading country pack from: {pack_path}")
        with open(pack_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if not raw_data or not isinstance(raw_data, dict):
            raise ValueError(f"Pack file '{pack_path}' is empty or not a valid YAML mapping.")

        try:
            self._cached_pack = CountryPack(**raw_data)
        except Exception as e:
            raise ValueError(f"Pack file '{pack_path}' failed validation: {e}") from e

        logger.info(
            f"Loaded pack: {self._cached_pack.country_code} / {self._cached_pack.region_name} "
            f"({len(self._cached_pack.languages)} languages, {len(self._cached_pack.sectors)} sectors)"
        )
        return self._cached_pack

    def clear_cache(self):
        """Clear the cached pack (useful for testing or hot-reload)."""
        self._cached_pack = None
        logger.info("Pack cache cleared.")

    def get_sector_keys(self) -> List[str]:
        """Return the list of valid sector keys from the active pack."""
        pack = self.load_active_pack()
        return [s.key for s in pack.sectors]

    def get_language_codes(self) -> List[str]:
        """Return the list of supported language codes from the active pack."""
        pack = self.load_active_pack()
        return [l.code for l in pack.languages]


pack_loader = PackLoader()
