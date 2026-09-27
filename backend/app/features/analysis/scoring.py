"""
Scoring and verdicts. Pure functions: no database, no model, no clock.
Every number here can be re-derived by hand from the cluster's inputs.

    demand   = baseline_ratio / max baseline_ratio in this run
    deficit  = how far behind the best-served place this one is (0..1)
    reach    = log10(population), scaled 0..1 across this run
    coverage = money already delivered here (completed projects), 0..1

    score = 100 × Σ(weight × term) / Σ(weights of available terms)  −  100 × w_coverage × coverage

A term with no data drops out and the remaining weights re-normalise; the
priority records which terms were missing.
"""

import math
from dataclasses import dataclass, field
from statistics import median

OPEN_STATUSES = {"sanctioned", "in_progress", "stalled"}

UNSERVED_GAP = "UNSERVED_GAP"  # high demand, official data says NOT served, no money committed → fund
DEMAND_HOTSPOT = "DEMAND_HOTSPOT"  # high demand, no official data to compare against yet → investigate
STALLED_ALLOCATION = "STALLED_ALLOCATION"  # high demand, money committed but not delivered → audit
DELIVERY_GAP = "DELIVERY_GAP"  # high demand, official data says served → audit delivery
PLANNED_NOT_STARTED = "PLANNED_NOT_STARTED"  # high demand, money only planned, nothing started → audit
MONITOR = "MONITOR"  # demand near the norm


@dataclass
class ProjectFact:
    status: str
    amount: float | None


@dataclass
class ClusterInput:
    region_id: str
    level: int
    sector: str
    distinct_reporters: int
    population: float | None
    indicator_value: float | None = None
    higher_is_better: bool = True
    served_threshold: float | None = None
    level_values: list[float] = field(default_factory=list)  # same statistic, every place at this level
    projects: list[ProjectFact] = field(default_factory=list)
    cost_per_unit: float | None = None
    indicator_is_percent: bool = False


@dataclass
class Scored:
    input: ClusterInput
    per_1000: float | None
    baseline_ratio: float
    score: float
    verdict: str
    components: dict
    beneficiaries: int | None
    estimated_cost: float | None


def per_1000(reporters: int, population: float | None) -> float | None:
    return reporters / population * 1000 if population else None


def deficit(value: float | None, values: list[float], higher_is_better: bool) -> float | None:
    if value is None or len(values) < 2:
        return None
    best, worst = (max(values), min(values)) if higher_is_better else (min(values), max(values))
    if best == worst:
        return 0.0
    return min(1.0, max(0.0, (best - value) / (best - worst)))


def verdict(high_demand: bool, projects: list[ProjectFact], value: float | None,
            served_threshold: float | None, higher_is_better: bool) -> str:
    if not high_demand:
        return MONITOR
    if any(p.status in OPEN_STATUSES for p in projects):
        return STALLED_ALLOCATION
    officially_served = value is not None and served_threshold is not None and (
        value >= served_threshold if higher_is_better else value <= served_threshold)
    if officially_served or any(p.status == "completed" for p in projects):
        return DELIVERY_GAP
    if any(p.status == "planned" for p in projects):
        return PLANNED_NOT_STARTED
    if value is None:
        # Without a statistic we cannot say the place is unserved — only that it is loud.
        return DEMAND_HOTSPOT
    return UNSERVED_GAP


def score_clusters(inputs: list[ClusterInput], weights: dict[str, float], high_demand_ratio: float) -> list[Scored]:
    if not inputs:
        return []

    # Demand relative to the median place with the same need at the same level.
    intensity = {id(c): per_1000(c.distinct_reporters, c.population) for c in inputs}
    groups: dict[tuple[str, int], list[float]] = {}
    for c in inputs:
        value = intensity[id(c)] if intensity[id(c)] is not None else float(c.distinct_reporters)
        groups.setdefault((c.sector, c.level), []).append(value)
    ratios = {}
    for c in inputs:
        value = intensity[id(c)] if intensity[id(c)] is not None else float(c.distinct_reporters)
        med = median(groups[(c.sector, c.level)])
        ratios[id(c)] = value / med if med else 1.0
    max_ratio = max(ratios.values()) or 1.0

    logs = [math.log10(c.population) for c in inputs if c.population and c.population > 1]
    log_min, log_max = (min(logs), max(logs)) if logs else (0.0, 0.0)

    results = []
    for c in inputs:
        terms: dict[str, float | None] = {
            "demand": ratios[id(c)] / max_ratio,
            "deficit": deficit(c.indicator_value, c.level_values, c.higher_is_better),
            "reach": ((math.log10(c.population) - log_min) / (log_max - log_min) if log_max > log_min else 1.0)
            if c.population and c.population > 1 else None,
        }
        available = {k: v for k, v in terms.items() if v is not None}
        total_weight = sum(weights[k] for k in available) or 1.0
        components = {k: {"value": round(v, 4), "weight": weights[k],
                          "contribution": round(100 * weights[k] * v / total_weight, 2)} for k, v in available.items()}

        completed = [p for p in c.projects if p.status == "completed"]
        if completed and c.cost_per_unit and c.population:
            spent = sum(p.amount or 0 for p in completed)
            coverage = min(1.0, spent / (c.cost_per_unit * c.population))
        else:
            coverage = 1.0 if completed else 0.0
        components["coverage"] = {"value": round(coverage, 4), "weight": weights["coverage"],
                                  "contribution": round(-100 * weights["coverage"] * coverage, 2)}
        components["missing"] = [k for k, v in terms.items() if v is None]

        score = round(sum(part["contribution"] for key, part in components.items() if key != "missing"), 2)
        high = ratios[id(c)] >= high_demand_ratio
        v = verdict(high, c.projects, c.indicator_value, c.served_threshold, c.higher_is_better)

        beneficiaries = cost = None
        if v == UNSERVED_GAP and c.population and c.indicator_is_percent and c.indicator_value is not None:
            unserved = c.population * (100 - c.indicator_value) / 100 if c.higher_is_better else None
            if unserved is not None:
                beneficiaries = int(round(unserved))
                cost = beneficiaries * c.cost_per_unit if c.cost_per_unit else None

        results.append(Scored(c, intensity[id(c)], ratios[id(c)], score, v, components, beneficiaries, cost))
    return results
