import pytest

from app.features.analysis.scoring import (
    DELIVERY_GAP,
    DEMAND_HOTSPOT,
    MONITOR,
    PLANNED_NOT_STARTED,
    STALLED_ALLOCATION,
    UNSERVED_GAP,
    ClusterInput,
    ProjectFact,
    deficit,
    score_clusters,
    verdict,
)
from app.features.analysis.verify import unsupported_numbers

WEIGHTS = {"demand": 0.35, "deficit": 0.30, "reach": 0.15, "coverage": 0.20}


@pytest.mark.parametrize("high, projects, value, expected", [
    (False, [], 20, MONITOR),
    (True, [ProjectFact("in_progress", 100)], 20, STALLED_ALLOCATION),
    (True, [ProjectFact("stalled", 100)], 95, STALLED_ALLOCATION),
    (True, [], 95, DELIVERY_GAP),
    (True, [ProjectFact("completed", 100)], 20, DELIVERY_GAP),
    (True, [], 20, UNSERVED_GAP),
    (True, [], None, DEMAND_HOTSPOT),
    (True, [ProjectFact("planned", 100)], 20, PLANNED_NOT_STARTED),
    (True, [ProjectFact("planned", 100)], None, PLANNED_NOT_STARTED),  # the plan is known even without a statistic
    (True, [ProjectFact("planned", 100)], 95, DELIVERY_GAP),  # records say served: residents disagree
    (True, [ProjectFact("planned", 100), ProjectFact("in_progress", 50)], 20, STALLED_ALLOCATION),
    (False, [ProjectFact("planned", 100)], 20, MONITOR),
])
def test_verdict_table(high, projects, value, expected):
    assert verdict(high, projects, value, served_threshold=80, higher_is_better=True) == expected


def test_deficit_is_distance_from_the_best_place():
    assert deficit(20, [20, 60, 100], True) == 1.0
    assert deficit(100, [20, 60, 100], True) == 0.0
    assert deficit(60, [20, 60, 100], True) == 0.5
    assert deficit(60, [60], True) is None  # nothing to compare against


def cluster(region, reporters, population=1000, value=None, **kw):
    return ClusterInput(region_id=region, level=2, sector="water", distinct_reporters=reporters,
                        population=population, indicator_value=value, served_threshold=80,
                        level_values=[20, 60, 90], indicator_is_percent=True, cost_per_unit=1000, **kw)


def test_demand_is_per_capita_relative_to_the_median_place():
    a, b, c = score_clusters([cluster("a", 2), cluster("b", 4), cluster("c", 20)], WEIGHTS, 1.5)
    assert (a.baseline_ratio, b.baseline_ratio, c.baseline_ratio) == (0.5, 1.0, 5.0)
    assert c.per_1000 == 20.0
    assert c.score > b.score > a.score


def test_small_place_with_same_reporters_ranks_higher_than_big_one():
    small, big, mid = score_clusters(
        [cluster("small", 10, population=500), cluster("big", 10, population=50000), cluster("mid", 10, 5000)],
        WEIGHTS, 1.5)
    assert small.baseline_ratio > big.baseline_ratio


def test_missing_statistic_drops_out_and_is_recorded():
    (result,) = score_clusters([cluster("a", 5, value=None)], WEIGHTS, 1.5)
    assert "deficit" in result.components["missing"]
    assert "deficit" not in result.components


def test_cost_and_beneficiaries_only_for_unserved_gaps():
    # Median demand here is 17.5 reporters per 1,000, so 30 is 1.7× the norm (high) and 1 is not.
    low, _, high, served = score_clusters(
        [cluster("low", 1, value=20), cluster("mid", 5, value=20), cluster("high", 30, value=20),
         cluster("served", 30, value=90)], WEIGHTS, 1.5)
    assert high.verdict == UNSERVED_GAP
    assert high.beneficiaries == 800 and high.estimated_cost == 800_000  # 1000 households × 80% unserved
    assert served.verdict == DELIVERY_GAP and served.estimated_cost is None
    assert low.verdict == MONITOR and low.estimated_cost is None


def test_completed_money_is_subtracted():
    plain, funded = score_clusters(
        [cluster("plain", 10, value=20), cluster("funded", 10, value=20,
                                                 projects=[ProjectFact("completed", 1_000_000)])], WEIGHTS, 1.5)
    assert funded.components["coverage"]["contribution"] == -20.0
    assert funded.score == pytest.approx(plain.score - 20.0)


FACTS = [{"id": "F1", "value": 12}, {"id": "F5", "value": 91.5, "period": "2026"}, {"id": "F8", "value": 1250000}]


def test_summary_using_only_evidence_numbers_passes():
    text = "12 residents report problems although 91.5% of households are connected (2026). Cost: 1,250,000."
    assert unsupported_numbers(text, FACTS) == []


def test_rounded_forms_of_evidence_numbers_pass():
    assert unsupported_numbers("About 92% are connected.", FACTS) == []


def test_invented_number_is_caught():
    assert unsupported_numbers("12 residents; 40 villages affected.", FACTS) == ["40"]
