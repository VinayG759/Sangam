"""
Tests for app.utils.real_data_mapping -- the pure functions that convert
packs/india/*.csv rows into ORM-ready dicts.

These run without a database, deliberately: the goal is to prove the mapping
logic correct before a single row is written to a real Postgres instance,
which is not available to run against in every environment.
"""

import pytest

from app.utils.real_data_mapping import (
    RowMappingError,
    households_to_population_estimate,
    map_admin_unit_row,
    map_indicator_row,
    normalize_sector_key,
)


class TestMapAdminUnitRow:
    def test_state_row(self):
        row = {
            "unit_id": "IN-KA", "country_code": "IN", "level": "1",
            "name": "Karnataka", "name_variants": "KA|Karnatak", "parent_unit_id": "IN",
            "external_code": "29", "population": "",
            "source_name": "JJM", "source_url": "https://example.gov/",
        }
        result = map_admin_unit_row(row)
        assert result["external_id"] == "IN-KA"
        assert result["level"] == "state"
        assert result["parent_external_id"] == "IN"
        assert result["name"] == "Karnataka"
        assert result["name_variants"] == "KA|Karnatak"

    def test_block_maps_to_ward(self):
        row = {"unit_id": "IN-KA-CHITRADURGA-HIRIYUR", "level": "3", "name": "Hiriyur",
               "parent_unit_id": "IN-KA-CHITRADURGA", "country_code": "IN"}
        result = map_admin_unit_row(row)
        assert result["level"] == "ward"

    def test_district_maps_to_district(self):
        row = {"unit_id": "IN-KA-CHITRADURGA", "level": "2", "name": "Chitradurga",
               "parent_unit_id": "IN-KA", "country_code": "IN"}
        result = map_admin_unit_row(row)
        assert result["level"] == "district"

    def test_missing_unit_id_raises(self):
        with pytest.raises(RowMappingError):
            map_admin_unit_row({"unit_id": "", "level": "1", "name": "X"})

    def test_missing_name_raises(self):
        with pytest.raises(RowMappingError):
            map_admin_unit_row({"unit_id": "IN-KA", "level": "1", "name": ""})

    def test_unknown_level_raises(self):
        with pytest.raises(RowMappingError):
            map_admin_unit_row({"unit_id": "IN-KA", "level": "9", "name": "X"})

    def test_blank_parent_becomes_none(self):
        row = {"unit_id": "IN", "level": "0", "name": "India", "parent_unit_id": ""}
        result = map_admin_unit_row(row)
        assert result["parent_external_id"] is None

    def test_country_code_defaults_when_blank(self):
        row = {"unit_id": "IN-KA", "level": "1", "name": "Karnataka", "country_code": ""}
        result = map_admin_unit_row(row)
        assert result["country_code"] == "IND"


class TestMapIndicatorRow:
    def test_normal_row(self):
        row = {
            "unit_id": "IN-KA-CHITRADURGA-HIRIYUR",
            "indicator_key": "water.piped_household_pct",
            "value": "77.8", "unit": "percent", "period": "2026",
            "source_name": "Jal Jeevan Mission (DDWS, Ministry of Jal Shakti)",
            "source_url": "https://ejalshakti.gov.in/jjmreport/JJMBlockMapView.aspx",
        }
        result = map_indicator_row(row)
        assert result["region_external_id"] == "IN-KA-CHITRADURGA-HIRIYUR"
        assert result["indicator_key"] == "water.piped_household_pct"
        assert result["numeric_value"] == pytest.approx(77.8)
        assert result["source_year"] == 2026
        assert result["source_url"].startswith("https://ejalshakti.gov.in")

    def test_missing_unit_id_raises(self):
        with pytest.raises(RowMappingError):
            map_indicator_row({"unit_id": "", "indicator_key": "x", "value": "1"})

    def test_missing_indicator_key_raises(self):
        with pytest.raises(RowMappingError):
            map_indicator_row({"unit_id": "IN-KA", "indicator_key": "", "value": "1"})

    def test_bad_value_raises(self):
        with pytest.raises(RowMappingError):
            map_indicator_row({"unit_id": "IN-KA", "indicator_key": "x", "value": "not-a-number"})

    def test_blank_period_falls_back_to_zero_not_a_guess(self):
        row = {"unit_id": "IN-KA", "indicator_key": "x", "value": "1", "period": ""}
        result = map_indicator_row(row)
        assert result["source_year"] == 0

    def test_missing_source_becomes_none_not_empty_string(self):
        row = {"unit_id": "IN-KA", "indicator_key": "x", "value": "1"}
        result = map_indicator_row(row)
        assert result["source_name"] is None
        assert result["source_url"] is None


class TestNormalizeSectorKey:
    def test_known_mismatch_translated(self):
        assert normalize_sector_key("road") == "roads"

    def test_already_correct_key_unchanged(self):
        assert normalize_sector_key("water") == "water"
        assert normalize_sector_key("roads") == "roads"

    def test_unknown_key_passed_through(self):
        assert normalize_sector_key("something_new") == "something_new"

    def test_whitespace_stripped(self):
        assert normalize_sector_key("  road  ") == "roads"


class TestHouseholdsToPopulationEstimate:
    def test_real_hiriyur_figure(self):
        # From the actual JJM block-map API response for Hiriyur, Chitradurga.
        assert households_to_population_estimate(78916) == 78916

    def test_rounds_a_float(self):
        assert households_to_population_estimate(1234.6) == 1235

    def test_zero_stays_zero(self):
        assert households_to_population_estimate(0) == 0
