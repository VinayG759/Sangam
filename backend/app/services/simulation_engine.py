from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SimulationEngine:
    """
    Simulates allocation of a fixed public capital pool across priorities
    using different governance strategy preferences.
    """
    
    @staticmethod
    def run_simulation(
        available_budget: float,
        priorities: List[Dict[str, Any]],  # list of dicts with cluster_id, score, cost_gap, reports_count, vulnerability
        strategy: str = "equity"  # "equity" (score/vulnerability prioritized) or "reach" (max reports resolved per dollar)
    ) -> Dict[str, Any]:
        
        # Parse and clean items that have a positive funding gap
        allocatable = []
        for p in priorities:
            gap = max(0.0, p.get("estimated_cost", 0.0) - p.get("allocated_budget", 0.0))
            if gap > 0:
                allocatable.append({
                    "cluster_id": p["cluster_id"],
                    "title": p.get("title", f"Cluster {p['cluster_id']}"),
                    "sector": p.get("sector", "other"),
                    "score": p.get("score", 0.0),
                    "reports_count": p.get("reports_count", 0),
                    "vulnerability": p.get("vulnerability", 0.5),
                    "cost_gap": gap,
                    "original_budget": p.get("allocated_budget", 0.0),
                    "estimated_cost": p.get("estimated_cost", 0.0)
                })

        # Sort based on strategy
        if strategy == "reach":
            # Reach Strategy: prioritize maximum citizen reports resolved per dollar spent
            # Sort descending by (reports_count / cost_gap)
            allocatable.sort(
                key=lambda x: (x["reports_count"] / x["cost_gap"]) if x["cost_gap"] > 0 else 0,
                reverse=True
            )
        elif strategy == "equity":
            # Equity Strategy: prioritize based on priority score & regional vulnerability
            # Sort descending by score * vulnerability
            allocatable.sort(
                key=lambda x: x["score"] * (1.0 + x["vulnerability"]),
                reverse=True
            )
        else:
            # Default: Sort descending by priority index score
            allocatable.sort(key=lambda x: x["score"], reverse=True)

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
