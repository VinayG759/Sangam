import logging
from typing import Dict, Any
from app.services.pack_loader import pack_loader

logger = logging.getLogger(__name__)

# Valid verdicts that the scoring engine can produce
VALID_VERDICTS = {"UNSERVED_GAP", "STALLED_ALLOCATION", "UNDERFUNDED_CRITICAL", "WELL_SERVED"}

# Minimum number of citizen reports before a priority can be classified as anything other than WELL_SERVED
REPORT_THRESHOLD = 2


class ScoringEngine:
    """
    Deterministic scoring engine.

    PriorityScore = w_demand × DemandDensity + w_vulnerability × VulnerabilityIndex
                  + w_gap × ExpenditureGap + w_urgency × Urgency

    Weights are loaded dynamically from the active country pack (pack.yaml),
    ensuring the scoring formula is policy-configurable without code changes.

    The engine classifies each priority into one of four verdicts:
    - UNSERVED_GAP: Real demand with zero budget allocated
    - STALLED_ALLOCATION: Budget sanctioned but execution is stalled
    - UNDERFUNDED_CRITICAL: Budget exists but is significantly below estimated need
    - WELL_SERVED: Adequate funding relative to demand
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
        """
        Calculate a deterministic priority score and verdict.

        Args:
            report_count: Number of citizen reports in this cluster.
            max_reports_in_region: Maximum report count across all clusters (for normalization).
            vulnerability_index: Regional vulnerability (0.0 = affluent, 1.0 = most vulnerable).
            allocated_budget: Total budget already allocated/sanctioned.
            estimated_cost: Estimated cost to address the issue fully.
            stalled_status: Whether the allocated budget execution is stalled.
            average_urgency: Mean urgency from citizen reports (1.0 to 5.0 scale).

        Returns:
            Dict with 'score' (0-100), 'verdict', 'breakdown', and 'weights_applied'.
        """
        # ── Load weights from pack config ───────────────────────────────
        pack = pack_loader.load_active_pack()
        weights = pack.weights

        # ── Clamp & validate inputs ─────────────────────────────────────
        report_count = max(0, int(report_count))
        max_reports_in_region = max(1, int(max_reports_in_region))  # Prevent division by zero
        vulnerability_index = max(0.0, min(1.0, float(vulnerability_index)))
        allocated_budget = max(0.0, float(allocated_budget))
        estimated_cost = max(0.0, float(estimated_cost))
        average_urgency = max(1.0, min(5.0, float(average_urgency)))

        # ── 1. Demand Density (D): normalized report count ──────────────
        demand_density = min(1.0, report_count / max_reports_in_region)

        # ── 2. Vulnerability Index (V): already clamped above ───────────
        vuln = vulnerability_index

        # ── 3. Expenditure Gap (G) ──────────────────────────────────────
        if allocated_budget > 0:
            if stalled_status:
                expenditure_gap = 0.8  # Budget exists but execution is stalled
            elif estimated_cost > 0:
                # Underfunded gap ratio
                gap_ratio = max(0.0, (estimated_cost - allocated_budget) / estimated_cost)
                expenditure_gap = gap_ratio
            else:
                expenditure_gap = 0.2  # Well-funded, not stalled
        else:
            expenditure_gap = 1.0  # Zero budget allocated → Unserved Gap

        # ── 4. Urgency Score (U): normalize 1-5 scale to 0-1 ──────────
        normalized_urgency = (average_urgency - 1.0) / 4.0

        # ── Calculate final index score ─────────────────────────────────
        final_score = (
            weights.demand_density * demand_density +
            weights.vulnerability_index * vuln +
            weights.expenditure_gap * expenditure_gap +
            weights.urgency * normalized_urgency
        )

        # Clamp to [0, 1] before scaling (protects against misconfigured weights)
        final_score = max(0.0, min(1.0, final_score))

        # ── Classify verdict ────────────────────────────────────────────
        verdict = "WELL_SERVED"
        if report_count > REPORT_THRESHOLD:
            if allocated_budget == 0:
                verdict = "UNSERVED_GAP"
            elif stalled_status:
                verdict = "STALLED_ALLOCATION"
            elif expenditure_gap > 0.5:
                verdict = "UNDERFUNDED_CRITICAL"

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
