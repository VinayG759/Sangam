import logging
from typing import Dict, Any, List
from app.services.pack_loader import pack_loader

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Deterministic scoring engine.
    PriorityScore = w_demand * DemandDensity + w_vulnerability * VulnerabilityIndex + w_gap * ExpenditureGap + w_urgency * Urgency
    """
    
    @staticmethod
    def calculate_priority_score(
        report_count: int,
        max_reports_in_region: int,
        vulnerability_index: float,  # 0.0 to 1.0
        allocated_budget: float,
        estimated_cost: float,
        stalled_status: bool,
        average_urgency: float,      # 1.0 to 5.0
    ) -> Dict[str, Any]:
        
        # Load weights dynamically from pack config
        pack = pack_loader.load_active_pack()
        weights = pack.weights
        
        # 1. Demand Density (D): normalized report count
        demand_density = 0.0
        if max_reports_in_region > 0:
            demand_density = min(1.0, report_count / max_reports_in_region)
        else:
            demand_density = min(1.0, report_count / 100.0) # Fallback scale

        # 2. Vulnerability Index (V): bounded 0 to 1
        vuln = min(1.0, max(0.0, vulnerability_index))

        # 3. Expenditure Gap (G)
        expenditure_gap = 1.0
        if allocated_budget > 0:
            if stalled_status:
                expenditure_gap = 0.8  # Budget exists but execution is stalled
            elif estimated_cost > 0:
                # Underfunded gap
                gap_ratio = max(0.0, (estimated_cost - allocated_budget) / estimated_cost)
                expenditure_gap = gap_ratio
            else:
                expenditure_gap = 0.2  # Well-funded but not stalled
        else:
            expenditure_gap = 1.0  # Zero budget allocated (Unserved Gap)

        # 4. Urgency Score (U): normalize 1-5 scale to 0-1 scale
        normalized_urgency = max(0.0, min(1.0, (average_urgency - 1.0) / 4.0))

        # Calculate final index score
        final_score = (
            weights.demand_density * demand_density +
            weights.vulnerability_index * vuln +
            weights.expenditure_gap * expenditure_gap +
            weights.urgency * normalized_urgency
        )

        # Classify verdict
        verdict = "WELL_SERVED"
        if report_count > 2:  # Threshold of reports to consider priority
            if allocated_budget == 0:
                verdict = "UNSERVED_GAP"
            elif stalled_status:
                verdict = "STALLED_ALLOCATION"
            elif expenditure_gap > 0.5:
                verdict = "UNDERFUNDED_CRITICAL"
            else:
                verdict = "WELL_SERVED"
        else:
            verdict = "WELL_SERVED"

        return {
            "score": round(final_score * 100.0, 2),  # Scale to 0-100 index
            "verdict": verdict,
            "breakdown": {
                "demand_density": round(demand_density, 3),
                "vulnerability": round(vuln, 3),
                "expenditure_gap": round(expenditure_gap, 3),
                "urgency": round(normalized_urgency, 3)
            },
            "weights_applied": {
                "demand_density": weights.demand_density,
                "vulnerability_index": weights.vulnerability_index,
                "expenditure_gap": weights.expenditure_gap,
                "urgency": weights.urgency
            }
        }

scoring_engine = ScoringEngine()
