import logging
from typing import Dict, Any
from app.services.pack_loader import pack_loader

logger = logging.getLogger(__name__)

# Valid verdicts that the scoring engine can produce
VALID_VERDICTS = {"UNSERVED_GAP", "STALLED_ALLOCATION", "UNDERFUNDED_CRITICAL", "DELIVERY_GAP", "WELL_SERVED"}

# Minimum delivery-rate shortfall (in the indicator's own units -- e.g.
# percentage points of households connected) vs. a region's parent district
# before DELIVERY_GAP fires. Below this, a region is treated as merely
# average rather than flagged -- avoids firing on noise-level differences
# between a district and its own blocks. See Phase 13,
# docs/IMPLEMENTATION_PLAN.md.
MIN_DELIVERY_GAP = 2.0

# Minimum number of citizen reports before a priority can be classified as
# anything other than WELL_SERVED.
REPORT_THRESHOLD = 2

# Privacy floor: distinct reporters required before a cluster is shown at all.
# Overridable per country via pack.yaml, because what counts as identifying
# depends on settlement size. Used only when the pack does not set one.
DEFAULT_MIN_DISTINCT_REPORTERS = 5


class ScoringEngine:
    """
    Deterministic scoring engine.

    PriorityScore = w_demand × DemandDensity + w_vulnerability × VulnerabilityIndex
                  + w_gap × ExpenditureGap + w_urgency × Urgency

    Weights are loaded dynamically from the active country pack (pack.yaml),
    ensuring the scoring formula is policy-configurable without code changes.

    The engine classifies each priority into one of five verdicts:
    - UNSERVED_GAP: Real demand, zero budget allocated, and no delivery-rate
      signal to say more than that
    - DELIVERY_GAP: Real demand, zero budget allocated, but a real
      delivery-rate shortfall vs. this region's own parent district exists --
      a sourced finding for regions with no budget data at all (see Phase 13,
      docs/IMPLEMENTATION_PLAN.md, and docs/DECISIONS.md #2 for why India's
      real data has coverage percentages but no district-level budgets)
    - STALLED_ALLOCATION: Budget sanctioned but execution is stalled
    - UNDERFUNDED_CRITICAL: Budget exists but is significantly below estimated need
    - WELL_SERVED: Adequate funding relative to demand
    """

    @staticmethod
    def calculate_priority_score(
        report_count: int,
        max_reports_in_region: int,
        vulnerability_index: float | None,  # 0.0 to 1.0, or None if missing
        allocated_budget: float,
        estimated_cost: float,
        stalled_status: bool,
        average_urgency: float,      # 1.0 to 5.0
        distinct_reporters: int | None = None,
        population: float | None = None,
        reference_intensity: float | None = None,
        min_distinct_reporters: int | None = None,
        delivery_rate: float | None = None,
        delivery_reference: float | None = None,
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
            delivery_rate: This region's own value for a delivery-rate
                indicator (e.g. % households with piped water), when one
                exists for its sector. See DELIVERY_GAP below.
            delivery_reference: The same indicator's value for this region's
                parent (e.g. its district). Only meaningful alongside
                delivery_rate.

        Returns:
            Dict with 'score' (0-100), 'verdict', 'breakdown', and 'weights_applied'.
        """
        # ── Load weights from pack config ───────────────────────────────
        pack = pack_loader.load_active_pack()
        weights = pack.weights

        # ── Clamp & validate inputs ─────────────────────────────────────
        report_count = max(0, int(report_count))
        max_reports_in_region = max(1, int(max_reports_in_region))  # Prevent division by zero
        allocated_budget = max(0.0, float(allocated_budget))
        estimated_cost = max(0.0, float(estimated_cost))
        average_urgency = max(1.0, min(5.0, float(average_urgency)))

        # ── Distinct reporters, not messages ────────────────────────────
        # Scoring on message count means one person sending 500 messages
        # manufactures a hotspot. Counting distinct reporters does not block
        # that attack, it makes it pointless -- 500 messages from one identity
        # contribute exactly one. Falls back to report_count only when the
        # caller cannot supply it, and says so.
        if distinct_reporters is None:
            distinct_reporters = report_count
            demand_basis = "report_count_fallback"
        else:
            distinct_reporters = max(0, int(distinct_reporters))
            demand_basis = "distinct_reporters"

        # ── 1. Demand Density (D) ───────────────────────────────────────
        # Per capita, not raw. Raw counts measure population, not need: a city
        # out-reports a village on every issue forever, so ranking by count
        # builds a machine that funds places which are already served -- the
        # exact bias this system exists to correct.
        if population and population > 0:
            intensity = (distinct_reporters / population) * 1000.0
            ref = reference_intensity if reference_intensity and reference_intensity > 0 else None
            if ref:
                # relative to the pack-wide median for this need type
                demand_density = min(1.0, intensity / (ref * 2.0))
            else:
                demand_density = min(1.0, intensity / 10.0)
            demand_basis += "_per_capita"
        else:
            # No population available. Fall back to the old normalisation and
            # record it, so a skewed ranking is visible rather than silent.
            demand_density = min(1.0, distinct_reporters / max_reports_in_region)
            demand_basis += "_no_population"
            logger.warning(
                "No population for this cluster; scoring on raw counts, which "
                "favours dense areas. Supply population to score per capita."
            )

        # ── 2. Vulnerability Index (V): already clamped above ───────────
        if vulnerability_index is None:
            partial_evidence = True
            vuln = 0.0
            actual_vuln_weight = 0.0
        else:
            partial_evidence = False
            vulnerability_index = max(0.0, min(1.0, float(vulnerability_index)))
            vuln = vulnerability_index
            actual_vuln_weight = weights.vulnerability_index

        # ── 3. Expenditure Gap (G) ──────────────────────────────────────
        # Real Karnataka data has no district-level budget breakdown for any
        # sector (docs/DECISIONS.md #2) -- allocated_budget == 0 is the
        # normal case for every real region, not a rare one. Treating that
        # uniformly as "zero budget, maximum gap" made every real region's
        # expenditure-gap term identical, collapsing the ranking exactly
        # where demand/vulnerability/urgency would otherwise discriminate.
        # A delivery-rate shortfall vs. the region's own parent district is a
        # real, sourced number to use instead, when one exists.
        has_delivery_signal = (
            delivery_rate is not None
            and delivery_reference is not None
            and delivery_reference > 0
            and (delivery_reference - delivery_rate) >= MIN_DELIVERY_GAP
        )

        if allocated_budget > 0:
            if stalled_status:
                expenditure_gap = 0.8  # Budget exists but execution is stalled
            elif estimated_cost > 0:
                # Underfunded gap ratio
                gap_ratio = max(0.0, (estimated_cost - allocated_budget) / estimated_cost)
                expenditure_gap = gap_ratio
            else:
                expenditure_gap = 0.2  # Well-funded, not stalled
        elif has_delivery_signal:
            # No budget row exists at all, but a real coverage shortfall vs.
            # the parent district does -- score the actual shortfall so a
            # 40-point gap outranks a 5-point one, instead of both maxing
            # out identically.
            expenditure_gap = min(1.0, (delivery_reference - delivery_rate) / delivery_reference)
        else:
            expenditure_gap = 1.0  # Zero budget allocated, no delivery signal either → Unserved Gap

        # ── 4. Urgency Score (U): normalize 1-5 scale to 0-1 ──────────
        normalized_urgency = (average_urgency - 1.0) / 4.0

        # ── Calculate final index score ─────────────────────────────────
        weighted = (
            weights.demand_density * demand_density +
            actual_vuln_weight * vuln +
            weights.expenditure_gap * expenditure_gap +
            weights.urgency * normalized_urgency
        )

        # Normalise by the weight sum rather than clamping at 1.0. Clamping
        # made every strong cluster saturate at 100 whenever a pack's weights
        # summed above 1, collapsing the ranking exactly where it matters most
        # -- at the top of the list a ministry would actually read.
        weight_sum = (
            weights.demand_density + actual_vuln_weight +
            weights.expenditure_gap + weights.urgency
        )
        final_score = weighted / weight_sum if weight_sum > 0 else 0.0
        final_score = max(0.0, min(1.0, final_score))

        # ── Aggregation floor ───────────────────────────────────────────
        # A cluster with two reporters in a 300-person village identifies
        # those two people to anyone local, including whoever they complained
        # about. Below the floor the cluster still counts toward its parent
        # region's totals -- the need survives, the individual is not exposed.
        floor = min_distinct_reporters if min_distinct_reporters is not None \
            else getattr(pack, "min_distinct_reporters", None) or DEFAULT_MIN_DISTINCT_REPORTERS
        below_floor = distinct_reporters < floor

        # ── Classify verdict ────────────────────────────────────────────
        verdict = "WELL_SERVED"
        if not below_floor and distinct_reporters > REPORT_THRESHOLD:
            if allocated_budget == 0 and has_delivery_signal:
                verdict = "DELIVERY_GAP"
            elif allocated_budget == 0:
                verdict = "UNSERVED_GAP"
            elif stalled_status:
                verdict = "STALLED_ALLOCATION"
            elif expenditure_gap > 0.5:
                verdict = "UNDERFUNDED_CRITICAL"

        return {
            "score": round(final_score * 100.0, 2),  # Scale to 0-100 index
            "verdict": verdict,
            "suppressed": below_floor,
            "partial_evidence": partial_evidence,
            "distinct_reporters": distinct_reporters,
            "demand_basis": demand_basis,
            "delivery_rate": delivery_rate,
            "delivery_reference": delivery_reference,
            "breakdown": {
                "demand_density": round(demand_density, 3),
                "vulnerability": round(vuln, 3) if not partial_evidence else None,
                "expenditure_gap": round(expenditure_gap, 3),
                "urgency": round(normalized_urgency, 3)
            },
            "weights_applied": {
                "demand_density": weights.demand_density,
                "vulnerability_index": actual_vuln_weight,
                "expenditure_gap": weights.expenditure_gap,
                "urgency": weights.urgency
            }
        }


scoring_engine = ScoringEngine()
