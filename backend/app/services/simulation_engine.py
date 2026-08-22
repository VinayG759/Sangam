from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SimulationEngine:
    """
    Simulates allocation of a fixed public capital pool across priorities
    using different governance strategy preferences.

    Strategies:
    - "equity": Prioritizes high-scoring, high-vulnerability clusters (score × (1 + vulnerability))
    - "reach": Maximizes citizen reports resolved per rupee spent (reports_count / cost_gap)
    - "default": Sorts purely by priority score descending

    Returns a complete allocation breakdown with per-item funding status.
    """

    VALID_STRATEGIES = {"equity", "reach", "default"}

    @staticmethod
    def run_simulation(
        available_budget: float,
        priorities: List[Dict[str, Any]],
        strategy: str = "equity"
    ) -> Dict[str, Any]:
        """
        Run budget allocation simulation.

        Args:
            available_budget: Total budget pool to allocate (must be > 0).
            priorities: List of dicts with keys: cluster_id, score, estimated_cost,
                        allocated_budget, reports_count, vulnerability, title, sector.
            strategy: One of "equity", "reach", or "default".

        Returns:
            Dict with strategy, totals, and per-item allocations.

        Raises:
            ValueError: If budget is non-positive or strategy is invalid.
        """
        # ── Input validation ────────────────────────────────────────────
        if available_budget <= 0:
            raise ValueError(f"available_budget must be positive, got {available_budget}")

        if strategy not in SimulationEngine.VALID_STRATEGIES:
            raise ValueError(
                f"Invalid strategy '{strategy}'. Must be one of: {', '.join(sorted(SimulationEngine.VALID_STRATEGIES))}"
            )

        if not priorities:
            return {
                "strategy": strategy,
                "simulated_budget": available_budget,
                "total_spent": 0.0,
                "remaining_budget": available_budget,
                "gaps_fully_resolved": 0,
                "citizen_needs_addressed": 0,
                "allocations": []
            }

        # ── Parse allocatable items with positive funding gaps ──────────
        allocatable = []
        for p in priorities:
            estimated_cost = max(0.0, float(p.get("estimated_cost", 0.0)))
            allocated_budget = max(0.0, float(p.get("allocated_budget", 0.0)))
            gap = max(0.0, estimated_cost - allocated_budget)

            if gap > 0:
                reports_count = max(0, int(p.get("reports_count", 0)))
                vulnerability = max(0.0, min(1.0, float(p.get("vulnerability", 0.5))))
                score = max(0.0, float(p.get("score", 0.0)))

                allocatable.append({
                    "cluster_id": p["cluster_id"],
                    "title": p.get("title", f"Cluster {p['cluster_id']}"),
                    "sector": p.get("sector", "other"),
                    "score": score,
                    "reports_count": reports_count,
                    "vulnerability": vulnerability,
                    "cost_gap": gap,
                    "original_budget": allocated_budget,
                    "estimated_cost": estimated_cost
                })

        # ── Sort based on strategy ──────────────────────────────────────
        if strategy == "reach":
            # Reach Strategy: maximize citizen reports resolved per dollar spent
            allocatable.sort(
                key=lambda x: (x["reports_count"] / x["cost_gap"]) if x["cost_gap"] > 0 else 0,
                reverse=True
            )
        elif strategy == "equity":
            # Equity Strategy: prioritize based on priority score & regional vulnerability
            allocatable.sort(
                key=lambda x: x["score"] * (1.0 + x["vulnerability"]),
                reverse=True
            )
        else:
            # Default: Sort descending by priority index score
            allocatable.sort(key=lambda x: x["score"], reverse=True)

        # ── Greedy allocation ───────────────────────────────────────────
        allocated_items = []
        remaining_pool = available_budget
        total_spent = 0.0
        gaps_resolved = 0
        total_reports_resolved = 0

        for item in allocatable:
            if remaining_pool <= 0:
                break

            gap = item["cost_gap"]
            if remaining_pool >= gap:
                # Fully fund the gap
                allocated_amount = gap
                remaining_pool -= gap
                total_spent += gap
                gaps_resolved += 1
                total_reports_resolved += item["reports_count"]

                allocated_items.append({
                    "cluster_id": item["cluster_id"],
                    "title": item["title"],
                    "sector": item["sector"],
                    "allocated_amount": round(allocated_amount, 2),
                    "pct_funded": 100.0,
                    "status": "fully_funded"
                })
            else:
                # Partially fund with remaining budget
                allocated_amount = remaining_pool
                pct = round((allocated_amount / gap) * 100.0, 1)
                total_spent += allocated_amount
                remaining_pool = 0.0

                allocated_items.append({
                    "cluster_id": item["cluster_id"],
                    "title": item["title"],
                    "sector": item["sector"],
                    "allocated_amount": round(allocated_amount, 2),
                    "pct_funded": pct,
                    "status": "partially_funded"
                })

        return {
            "strategy": strategy,
            "simulated_budget": available_budget,
            "total_spent": round(total_spent, 2),
            "remaining_budget": round(remaining_pool, 2),
            "gaps_fully_resolved": gaps_resolved,
            "citizen_needs_addressed": total_reports_resolved,
            "allocations": allocated_items
        }


simulation_engine = SimulationEngine()
