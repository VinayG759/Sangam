import os
import yaml
from pydantic import BaseModel, Field
from typing import List, Dict
from app.config import settings

class LanguageConfig(BaseModel):
    code: str
    name: str
    is_default: bool = False

class SectorConfig(BaseModel):
    key: str
    name: str

class WeightsConfig(BaseModel):
    demand_density: float = Field(0.35, description="Weight for cluster reports density")
    vulnerability_index: float = Field(0.35, description="Weight for region vulnerability")
    expenditure_gap: float = Field(0.20, description="Weight for unallocated budget gap")
    urgency: float = Field(0.10, description="Weight for citizen reported urgency")

class CountryPack(BaseModel):
    country_code: str
    region_name: str = "General"
    languages: List[LanguageConfig]
    sectors: List[SectorConfig]
    weights: WeightsConfig

class PackLoader:
    _instance = None
    _cached_pack = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PackLoader, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def load_active_pack(self) -> CountryPack:
        if self._cached_pack:
            return self._cached_pack

        pack_name = settings.ACTIVE_COUNTRY_PACK
        pack_path = os.path.join(settings.PACKS_DIR, pack_name, "pack.yaml")

        # Fallback to default if not found
        if not os.path.exists(pack_path):
            pack_path = os.path.join(settings.PACKS_DIR, "default", "pack.yaml")

        if not os.path.exists(pack_path):
            raise FileNotFoundError(
                f"Active pack config not found at '{pack_path}' and default pack is missing."
            )

        with open(pack_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        self._cached_pack = CountryPack(**raw_data)
        return self._cached_pack

    def clear_cache(self):
        self._cached_pack = None

pack_loader = PackLoader()
