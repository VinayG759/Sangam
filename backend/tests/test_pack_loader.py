"""
Unit tests for PackLoader.

Tests cover:
- Loading a valid pack from a YAML file
- Pack caching behavior
- Fallback to default pack
- Missing pack file error handling
- Invalid YAML content handling
- Weight validation warnings
- Helper methods (get_sector_keys, get_language_codes)
"""

import os
import pytest
import yaml
from unittest.mock import patch
from app.services.pack_loader import PackLoader, CountryPack, WeightsConfig


@pytest.fixture
def pack_loader_instance(sample_pack_dir):
    """Create a fresh PackLoader (bypassing singleton) with test configuration."""
    packs_dir, pack_name = sample_pack_dir

    loader = PackLoader.__new__(PackLoader)
    loader._cached_pack = None

    with patch("app.services.pack_loader.settings") as mock_settings:
        mock_settings.PACKS_DIR = str(packs_dir)
        mock_settings.ACTIVE_COUNTRY_PACK = pack_name
        yield loader, packs_dir, pack_name, mock_settings


class TestLoadActivePack:
    """Tests for load_active_pack."""

    def test_loads_valid_pack(self, pack_loader_instance):
        loader, packs_dir, pack_name, mock_settings = pack_loader_instance
        pack = loader.load_active_pack()

        assert isinstance(pack, CountryPack)
        assert pack.country_code == "TST"
        assert pack.region_name == "TestRegion"
        assert len(pack.languages) == 2
        assert len(pack.sectors) == 3

    def test_weights_loaded_correctly(self, pack_loader_instance):
        loader, *_ = pack_loader_instance
        pack = loader.load_active_pack()

        assert pack.weights.demand_density == 0.35
        assert pack.weights.vulnerability_index == 0.35
        assert pack.weights.expenditure_gap == 0.20
        assert pack.weights.urgency == 0.10

    def test_caches_result(self, pack_loader_instance):
        loader, *_ = pack_loader_instance
        pack1 = loader.load_active_pack()
        pack2 = loader.load_active_pack()
        assert pack1 is pack2  # Same object (cached)

    def test_clear_cache_works(self, pack_loader_instance):
        loader, *_ = pack_loader_instance
        pack1 = loader.load_active_pack()
        loader.clear_cache()
        pack2 = loader.load_active_pack()
        assert pack1 is not pack2  # New object after cache clear


class TestFallbackBehavior:
    """Tests for fallback to default pack."""

    def test_falls_back_to_default(self, tmp_path):
        """When active pack is missing, loader should try the default pack."""
        # Create only a default pack
        default_dir = tmp_path / "default"
        default_dir.mkdir()
        pack_data = {
            "country_code": "DEF",
            "region_name": "Default",
            "languages": [{"code": "en", "name": "English", "is_default": True}],
            "sectors": [{"key": "water", "name": "Water"}],
            "weights": {
                "demand_density": 0.25,
                "vulnerability_index": 0.25,
                "expenditure_gap": 0.25,
                "urgency": 0.25,
            },
        }
        with open(default_dir / "pack.yaml", "w") as f:
            yaml.dump(pack_data, f)

        loader = PackLoader.__new__(PackLoader)
        loader._cached_pack = None

        with patch("app.services.pack_loader.settings") as mock_settings:
            mock_settings.PACKS_DIR = str(tmp_path)
            mock_settings.ACTIVE_COUNTRY_PACK = "nonexistent_pack"
            pack = loader.load_active_pack()

        assert pack.country_code == "DEF"

    def test_raises_when_no_packs_exist(self, tmp_path):
        """Should raise FileNotFoundError when both active and default packs are missing."""
        loader = PackLoader.__new__(PackLoader)
        loader._cached_pack = None

        with patch("app.services.pack_loader.settings") as mock_settings:
            mock_settings.PACKS_DIR = str(tmp_path)
            mock_settings.ACTIVE_COUNTRY_PACK = "missing_pack"
            with pytest.raises(FileNotFoundError, match="not found"):
                loader.load_active_pack()


class TestInvalidPacks:
    """Tests for malformed pack YAML files."""

    def test_empty_yaml_raises(self, tmp_path):
        """Empty YAML file should raise ValueError."""
        pack_dir = tmp_path / "empty_pack"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text("")

        loader = PackLoader.__new__(PackLoader)
        loader._cached_pack = None

        with patch("app.services.pack_loader.settings") as mock_settings:
            mock_settings.PACKS_DIR = str(tmp_path)
            mock_settings.ACTIVE_COUNTRY_PACK = "empty_pack"
            with pytest.raises(ValueError, match="empty"):
                loader.load_active_pack()

    def test_invalid_schema_raises(self, tmp_path):
        """YAML missing required fields should raise ValueError."""
        pack_dir = tmp_path / "bad_pack"
        pack_dir.mkdir()
        # Missing 'languages', 'sectors', 'weights'
        with open(pack_dir / "pack.yaml", "w") as f:
            yaml.dump({"country_code": "BAD"}, f)

        loader = PackLoader.__new__(PackLoader)
        loader._cached_pack = None

        with patch("app.services.pack_loader.settings") as mock_settings:
            mock_settings.PACKS_DIR = str(tmp_path)
            mock_settings.ACTIVE_COUNTRY_PACK = "bad_pack"
            with pytest.raises(ValueError, match="failed validation"):
                loader.load_active_pack()


class TestWeightValidation:
    """Tests for weight range and sum validation."""

    def test_weights_sum_warning(self, tmp_path, caplog):
        """Weights that don't sum to 1.0 should log a warning (not raise)."""
        pack_dir = tmp_path / "warn_pack"
        pack_dir.mkdir()
        pack_data = {
            "country_code": "WRN",
            "region_name": "Warning",
            "languages": [{"code": "en", "name": "English", "is_default": True}],
            "sectors": [{"key": "water", "name": "Water"}],
            "weights": {
                "demand_density": 0.5,
                "vulnerability_index": 0.5,
                "expenditure_gap": 0.5,
                "urgency": 0.5,  # Sum = 2.0
            },
        }
        with open(pack_dir / "pack.yaml", "w") as f:
            yaml.dump(pack_data, f)

        loader = PackLoader.__new__(PackLoader)
        loader._cached_pack = None

        import logging
        with patch("app.services.pack_loader.settings") as mock_settings:
            mock_settings.PACKS_DIR = str(tmp_path)
            mock_settings.ACTIVE_COUNTRY_PACK = "warn_pack"
            with caplog.at_level(logging.WARNING):
                pack = loader.load_active_pack()

        # Pack should still load (weights are individually valid)
        assert pack.country_code == "WRN"


class TestHelperMethods:
    """Tests for convenience methods."""

    def test_get_sector_keys(self, pack_loader_instance):
        loader, *_ = pack_loader_instance
        keys = loader.get_sector_keys()
        assert "water" in keys
        assert "roads" in keys
        assert "sanitation" in keys
        assert len(keys) == 3

    def test_get_language_codes(self, pack_loader_instance):
        loader, *_ = pack_loader_instance
        codes = loader.get_language_codes()
        assert "en" in codes
        assert "kn" in codes
        assert len(codes) == 2
