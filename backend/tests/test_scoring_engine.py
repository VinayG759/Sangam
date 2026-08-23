"""
Unit tests for ScoringEngine.

Tests cover:
- Score calculation with known weights
- Verdict classification logic
- Input clamping (out-of-range values)
- Edge cases (zero reports, zero budget, all-zero inputs)
- Output structure
"""

import pytest
from unittest.mock import patch, MagicMock
from app.services.pack_loader import WeightsConfig, CountryPack, LanguageConfig, SectorConfig


def _make_mock_pack(weights=None):
    """Create a mock CountryPack with specified or default weights."""
    if weights is None:
        weights = WeightsConfig(
            demand_density=0.35,
            vulnerability_index=0.35,
            expenditure_gap=0.20,
            urgency=0.10
        )
    return CountryPack(
        country_code="TST",
        region_name="TestRegion",
        languages=[LanguageConfig(code="en", name="English", is_default=True)],
        sectors=[SectorConfig(key="water", name="Water")],
        weights=weights
    )


@pytest.fixture(autouse=True)
def mock_pack_loader():
    """Mock the pack_loader to return test weights without needing a YAML file."""
    mock_pack = _make_mock_pack()
    with patch("app.services.scoring_engine.pack_loader") as mock_loader:
        mock_loader.load_active_pack.return_value = mock_pack
        yield mock_loader


# Import AFTER fixture definition so the module-level singleton doesn't fail
from app.services.scoring_engine import ScoringEngine, scoring_engine


class TestScoreCalculation:
    """Tests for the priority score formula."""

    def test_max_score_scenario(self):
        """All sub-scores at maximum → score should be 100.0."""
        result = scoring_engine.calculate_priority_score(
            report_count=100,
            max_reports_in_region=100,  # demand_density = 1.0
            vulnerability_index=1.0,    # vuln = 1.0
            allocated_budget=0.0,       # expenditure_gap = 1.0
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=5.0         # urgency = 1.0
        )
        # 0.35*1 + 0.35*1 + 0.20*1 + 0.10*1 = 1.0 → 100.0
        assert result["score"] == 100.0

    def test_min_score_scenario(self):
        """All sub-scores at minimum → score should be 0."""
        result = scoring_engine.calculate_priority_score(
            report_count=0,
            max_reports_in_region=100,   # demand_density = 0.0
            vulnerability_index=0.0,     # vuln = 0.0
            allocated_budget=1000000.0,  # well-funded
            estimated_cost=1000000.0,    # gap = 0
            stalled_status=False,
            average_urgency=1.0          # urgency = 0.0
        )
        # 0.35*0 + 0.35*0 + 0.20*0 + 0.10*0 = 0.0
        # expenditure_gap when allocated > 0 and estimated > 0: (1M-1M)/1M = 0
        assert result["score"] == pytest.approx(0.0 + 0.35 * 0 + 0.2 * 0 + 0.1 * 0, abs=0.1)

    def test_known_score_calculation(self):
        """Verify score with known inputs."""
        result = scoring_engine.calculate_priority_score(
            report_count=50,
            max_reports_in_region=100,
            vulnerability_index=0.45,
            allocated_budget=2500000.0,
            estimated_cost=7500000.0,
            stalled_status=False,
            average_urgency=4.2
        )
        # demand = 0.5, vuln = 0.45, gap = (7.5M-2.5M)/7.5M ≈ 0.667
        # urgency = (4.2-1)/4 = 0.8
        # score = 0.35*0.5 + 0.35*0.45 + 0.20*0.667 + 0.10*0.8 = 0.175 + 0.1575 + 0.1333 + 0.08 = 0.5458
        assert 50.0 < result["score"] < 60.0

    def test_stalled_allocation_gap(self):
        """Stalled status should give expenditure_gap = 0.8."""
        result = scoring_engine.calculate_priority_score(
            report_count=10,
            max_reports_in_region=10,
            vulnerability_index=0.5,
            allocated_budget=5000000.0,
            estimated_cost=5000000.0,
            stalled_status=True,
            average_urgency=3.0
        )
        assert result["breakdown"]["expenditure_gap"] == 0.8

    def test_missing_vulnerability_index_renormalizes_weights(self):
        """None for vulnerability_index triggers partial evidence and renormalizes remaining weights."""
        result = scoring_engine.calculate_priority_score(
            report_count=50,
            max_reports_in_region=100,  # demand_density = 0.5
            vulnerability_index=None,
            allocated_budget=0.0,       # expenditure_gap = 1.0
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=5.0         # urgency = 1.0
        )
        
        # Original weights:
        # demand_density = 0.35, vulnerability_index = 0.35, expenditure_gap = 0.20, urgency = 0.10
        # Sum without vulnerability = 0.35 + 0.20 + 0.10 = 0.65
        # Weighted = (0.35 * 0.5) + (0.20 * 1.0) + (0.10 * 1.0) = 0.175 + 0.20 + 0.10 = 0.475
        # Final Score = 0.475 / 0.65 = 0.73076...
        
        assert result["partial_evidence"] is True
        assert result["breakdown"]["vulnerability"] is None
        assert result["weights_applied"]["vulnerability_index"] == 0.0
        assert result["score"] == pytest.approx(73.08, abs=0.01)


class TestVerdictClassification:
    """Tests for verdict logic."""

    def test_unserved_gap_verdict(self):
        """Zero budget + > threshold reports → UNSERVED_GAP."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        assert result["verdict"] == "UNSERVED_GAP"

    def test_stalled_allocation_verdict(self):
        """Stalled + budget > 0 + > threshold reports → STALLED_ALLOCATION."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=1000000.0,
            estimated_cost=1000000.0,
            stalled_status=True,
            average_urgency=3.0
        )
        assert result["verdict"] == "STALLED_ALLOCATION"

    def test_underfunded_critical_verdict(self):
        """Budget exists but gap > 50% + > threshold reports → UNDERFUNDED_CRITICAL."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=500000.0,
            estimated_cost=5000000.0,  # Gap = 90%
            stalled_status=False,
            average_urgency=3.0
        )
        assert result["verdict"] == "UNDERFUNDED_CRITICAL"

    def test_well_served_verdict(self):
        """Adequate funding + not stalled → WELL_SERVED."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=4000000.0,
            estimated_cost=5000000.0,  # Gap = 20% (< 50%)
            stalled_status=False,
            average_urgency=3.0
        )
        assert result["verdict"] == "WELL_SERVED"

    def test_low_reports_always_well_served(self):
        """Below report threshold → always WELL_SERVED regardless of budget."""
        result = scoring_engine.calculate_priority_score(
            report_count=1,   # Below threshold of 2
            max_reports_in_region=100,
            vulnerability_index=0.9,
            allocated_budget=0.0,  # Would be UNSERVED_GAP if above threshold
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=5.0
        )
        assert result["verdict"] == "WELL_SERVED"


class TestDeliveryGapVerdict:
    """
    Tests for DELIVERY_GAP (Phase 13, docs/IMPLEMENTATION_PLAN.md): the
    verdict used when no Expenditure rows exist at all for a region+sector,
    but a real delivery-rate shortfall vs. the region's own parent district
    does exist -- the case every real Karnataka region is in today, since
    no district-level budget data exists (docs/DECISIONS.md #2).
    """

    def test_delivery_gap_fires_with_real_shortfall(self):
        """Zero budget + a real delivery shortfall vs. parent → DELIVERY_GAP."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=3.0,
            delivery_rate=77.85,       # Hiriyur's real water.piped_household_pct
            delivery_reference=88.5,   # Chitradurga district's real value
        )
        assert result["verdict"] == "DELIVERY_GAP"
        assert result["delivery_rate"] == 77.85
        assert result["delivery_reference"] == 88.5

    def test_unserved_gap_when_no_delivery_signal_provided(self):
        """Zero budget, no delivery data at all → still UNSERVED_GAP, unchanged."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=3.0,
        )
        assert result["verdict"] == "UNSERVED_GAP"
        assert result["delivery_rate"] is None

    def test_unserved_gap_when_shortfall_below_noise_threshold(self):
        """A trivial gap (< MIN_DELIVERY_GAP) should not fire DELIVERY_GAP."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=1000000.0,
            stalled_status=False,
            average_urgency=3.0,
            delivery_rate=87.0,
            delivery_reference=88.5,  # 1.5-point gap, below the 2.0 threshold
        )
        assert result["verdict"] == "UNSERVED_GAP"

    def test_delivery_gap_never_overrides_real_budget_data(self):
        """A real Expenditure record always takes precedence over a delivery signal."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=1000000.0,  # real budget exists
            estimated_cost=1000000.0,
            stalled_status=True,
            average_urgency=3.0,
            delivery_rate=50.0,
            delivery_reference=90.0,  # a large delivery gap, but irrelevant here
        )
        assert result["verdict"] == "STALLED_ALLOCATION"

    def test_delivery_gap_expenditure_score_reflects_shortfall_magnitude(self):
        """A bigger delivery shortfall should score a bigger expenditure_gap."""
        small_gap = scoring_engine.calculate_priority_score(
            report_count=5, max_reports_in_region=100, vulnerability_index=0.5,
            allocated_budget=0.0, estimated_cost=1000000.0, stalled_status=False,
            average_urgency=3.0, delivery_rate=85.0, delivery_reference=90.0,
        )
        large_gap = scoring_engine.calculate_priority_score(
            report_count=5, max_reports_in_region=100, vulnerability_index=0.5,
            allocated_budget=0.0, estimated_cost=1000000.0, stalled_status=False,
            average_urgency=3.0, delivery_rate=40.0, delivery_reference=90.0,
        )
        assert small_gap["verdict"] == "DELIVERY_GAP"
        assert large_gap["verdict"] == "DELIVERY_GAP"
        assert large_gap["breakdown"]["expenditure_gap"] > small_gap["breakdown"]["expenditure_gap"]
        assert large_gap["score"] > small_gap["score"]


class TestInputClamping:
    """Tests for input validation and clamping."""

    def test_negative_vulnerability_clamped(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=-0.5,  # Should clamp to 0.0
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        assert result["breakdown"]["vulnerability"] == 0.0

    def test_high_vulnerability_clamped(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=2.5,  # Should clamp to 1.0
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        assert result["breakdown"]["vulnerability"] == 1.0

    def test_urgency_below_range_clamped(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=0.0  # Should clamp to 1.0 → normalized 0.0
        )
        assert result["breakdown"]["urgency"] == 0.0

    def test_urgency_above_range_clamped(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=10.0  # Should clamp to 5.0 → normalized 1.0
        )
        assert result["breakdown"]["urgency"] == 1.0

    def test_zero_max_reports_no_division_error(self):
        """max_reports_in_region=0 should be clamped to 1 to prevent ZeroDivisionError."""
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=0,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        # Should not crash, demand_density = min(1.0, 5/1) = 1.0
        assert result["breakdown"]["demand_density"] == 1.0


class TestOutputStructure:
    """Verify output dict shape."""

    def test_output_keys(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        assert "score" in result
        assert "verdict" in result
        assert "breakdown" in result
        assert "weights_applied" in result

    def test_breakdown_keys(self):
        result = scoring_engine.calculate_priority_score(
            report_count=5,
            max_reports_in_region=10,
            vulnerability_index=0.5,
            allocated_budget=0.0,
            estimated_cost=100000.0,
            stalled_status=False,
            average_urgency=3.0
        )
        bd = result["breakdown"]
        assert "demand_density" in bd
        assert "vulnerability" in bd
        assert "expenditure_gap" in bd
        assert "urgency" in bd

    def test_score_in_range(self):
        result = scoring_engine.calculate_priority_score(
            report_count=50,
            max_reports_in_region=100,
            vulnerability_index=0.5,
            allocated_budget=500000.0,
            estimated_cost=2000000.0,
            stalled_status=False,
            average_urgency=3.5
        )
        assert 0.0 <= result["score"] <= 100.0
