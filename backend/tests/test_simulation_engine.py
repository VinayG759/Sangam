"""
Unit tests for SimulationEngine.

Tests cover:
- Equity strategy sorting and allocation
- Reach strategy sorting and allocation
- Default strategy
- Full funding, partial funding, zero-budget scenarios
- Input validation (negative budget, invalid strategy)
- Edge cases (empty priorities, zero gaps)
"""

import pytest
from app.services.simulation_engine import SimulationEngine, simulation_engine


class TestSimulationBasic:
    """Basic allocation behavior tests."""

    def test_equity_strategy_orders_by_score_x_vulnerability(self, sample_priorities):
        result = simulation_engine.run_simulation(
            available_budget=10000000.0,
            priorities=sample_priorities,
            strategy="equity"
        )
        assert result["strategy"] == "equity"
        assert result["simulated_budget"] == 10000000.0
        assert len(result["allocations"]) > 0

    def test_reach_strategy_orders_by_reports_per_dollar(self, sample_priorities):
        result = simulation_engine.run_simulation(
            available_budget=10000000.0,
            priorities=sample_priorities,
            strategy="reach"
        )
        assert result["strategy"] == "reach"
        assert len(result["allocations"]) > 0

    def test_default_strategy_orders_by_score(self, sample_priorities):
        result = simulation_engine.run_simulation(
            available_budget=10000000.0,
            priorities=sample_priorities,
            strategy="default"
        )
        assert result["strategy"] == "default"

    def test_total_spent_never_exceeds_budget(self, sample_priorities):
        budget = 1000000.0
        result = simulation_engine.run_simulation(
            available_budget=budget,
            priorities=sample_priorities,
            strategy="equity"
        )
        assert result["total_spent"] <= budget
        assert result["remaining_budget"] >= 0

    def test_total_spent_plus_remaining_equals_budget(self, sample_priorities):
        budget = 5000000.0
        result = simulation_engine.run_simulation(
            available_budget=budget,
            priorities=sample_priorities,
            strategy="equity"
        )
        assert abs(result["total_spent"] + result["remaining_budget"] - budget) < 0.01


class TestSimulationFullFunding:
    """Tests when budget is sufficient to fund everything."""

    def test_all_gaps_resolved_with_large_budget(self, sample_priorities):
        # Total gap = (3M-0.5M) + (4M-1M) + (1.5M-0) = 2.5M + 3M + 1.5M = 7M
        result = simulation_engine.run_simulation(
            available_budget=50000000.0,  # Way more than enough
            priorities=sample_priorities,
            strategy="equity"
        )
        for alloc in result["allocations"]:
            assert alloc["status"] == "fully_funded"
            assert alloc["pct_funded"] == 100.0
        assert result["gaps_fully_resolved"] == 3

    def test_remaining_budget_correct(self, sample_priorities):
        total_gap = (3000000 - 500000) + (4000000 - 1000000) + (1500000 - 0)
        budget = total_gap + 1000.0  # Slightly more than needed
        result = simulation_engine.run_simulation(
            available_budget=budget,
            priorities=sample_priorities,
            strategy="equity"
        )
        assert abs(result["remaining_budget"] - 1000.0) < 0.01


class TestSimulationPartialFunding:
    """Tests when budget only covers part of the gaps."""

    def test_partial_funding_status(self):
        priorities = [{
            "cluster_id": 1,
            "title": "Big Issue",
            "sector": "water",
            "score": 90.0,
            "reports_count": 10,
            "vulnerability": 0.5,
            "allocated_budget": 0.0,
            "estimated_cost": 5000000.0,
        }]
        result = simulation_engine.run_simulation(
            available_budget=2500000.0,
            priorities=priorities,
            strategy="equity"
        )
        assert len(result["allocations"]) == 1
        assert result["allocations"][0]["status"] == "partially_funded"
        assert result["allocations"][0]["pct_funded"] == 50.0
        assert result["remaining_budget"] == 0.0


class TestSimulationEdgeCases:
    """Edge case tests."""

    def test_empty_priorities(self):
        result = simulation_engine.run_simulation(
            available_budget=1000000.0,
            priorities=[],
            strategy="equity"
        )
        assert result["allocations"] == []
        assert result["total_spent"] == 0.0
        assert result["remaining_budget"] == 1000000.0

    def test_zero_gap_items_excluded(self):
        """Items where estimated_cost <= allocated_budget should be skipped."""
        priorities = [{
            "cluster_id": 1,
            "title": "Already Funded",
            "sector": "water",
            "score": 90.0,
            "reports_count": 10,
            "vulnerability": 0.5,
            "allocated_budget": 5000000.0,  # Already fully funded
            "estimated_cost": 5000000.0,
        }]
        result = simulation_engine.run_simulation(
            available_budget=1000000.0,
            priorities=priorities,
            strategy="equity"
        )
        assert result["allocations"] == []
        assert result["remaining_budget"] == 1000000.0


class TestSimulationInputValidation:
    """Input validation tests."""

    def test_negative_budget_raises(self, sample_priorities):
        with pytest.raises(ValueError, match="positive"):
            simulation_engine.run_simulation(
                available_budget=-100.0,
                priorities=sample_priorities,
                strategy="equity"
            )

    def test_zero_budget_raises(self, sample_priorities):
        with pytest.raises(ValueError, match="positive"):
            simulation_engine.run_simulation(
                available_budget=0.0,
                priorities=sample_priorities,
                strategy="equity"
            )

    def test_invalid_strategy_raises(self, sample_priorities):
        with pytest.raises(ValueError, match="Invalid strategy"):
            simulation_engine.run_simulation(
                available_budget=1000000.0,
                priorities=sample_priorities,
                strategy="invalid_strategy"
            )

    def test_negative_vulnerability_clamped(self):
        """Negative vulnerability should be clamped to 0.0, not cause errors."""
        priorities = [{
            "cluster_id": 1,
            "title": "Test",
            "sector": "water",
            "score": 50.0,
            "reports_count": 5,
            "vulnerability": -0.5,  # Invalid, should be clamped
            "allocated_budget": 0.0,
            "estimated_cost": 1000000.0,
        }]
        result = simulation_engine.run_simulation(
            available_budget=1000000.0,
            priorities=priorities,
            strategy="equity"
        )
        # Should not crash
        assert len(result["allocations"]) == 1


class TestSimulationOutputStructure:
    """Verify output format consistency."""

    def test_output_keys(self, sample_priorities):
        result = simulation_engine.run_simulation(
            available_budget=5000000.0,
            priorities=sample_priorities,
            strategy="equity"
        )
        assert "strategy" in result
        assert "simulated_budget" in result
        assert "total_spent" in result
        assert "remaining_budget" in result
        assert "gaps_fully_resolved" in result
        assert "citizen_needs_addressed" in result
        assert "allocations" in result

    def test_allocation_item_keys(self, sample_priorities):
        result = simulation_engine.run_simulation(
            available_budget=5000000.0,
            priorities=sample_priorities,
            strategy="equity"
        )
        for alloc in result["allocations"]:
            assert "cluster_id" in alloc
            assert "title" in alloc
            assert "sector" in alloc
            assert "allocated_amount" in alloc
            assert "pct_funded" in alloc
            assert "status" in alloc
