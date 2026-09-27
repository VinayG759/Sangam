"""
Impact labels. Pure functions: no database, no model, no clock.

Two questions a government asks of a large infrastructure programme:

1. Programme progress vs lived experience — the official statistic moved from
   its baseline to today; do residents' reports agree that it reached them?
2. Before and after a completed project — did complaints fall once it finished?
   (Correlation, not causation: the label says "fell after", never "because".)
"""

# Programme progress vs what residents say
NOT_REACHING = "NOT_REACHING"  # official data says served; many residents disagree
STILL_SHORT = "STILL_SHORT"  # below the served level and many residents report problems
NO_MAJOR_COMPLAINTS = "NO_MAJOR_COMPLAINTS"  # demand near the norm, or too few reports to show

# Before and after a completed project
IMPROVED = "IMPROVED"
NO_CHANGE = "NO_CHANGE"
WORSENED = "WORSENED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
TOO_EARLY = "TOO_EARLY"


def progress_label(verdict: str | None) -> str:
    """From the analysis verdict for the same place and need (None = no shown priority)."""
    if verdict in ("DELIVERY_GAP", "STALLED_ALLOCATION", "PLANNED_NOT_STARTED"):
        return NOT_REACHING
    if verdict == "UNSERVED_GAP":
        return STILL_SHORT
    return NO_MAJOR_COMPLAINTS


def change_label(before: int, after: int, floor: int, threshold: float) -> tuple[str, float | None]:
    """Distinct reporters in equal windows before and after completion → (label, fractional change)."""
    if before < floor and after < floor:
        return INSUFFICIENT_DATA, None
    if before == 0:
        return WORSENED, None  # complaints appeared where there were none
    change = (after - before) / before
    if change <= -threshold:
        return IMPROVED, change
    if change >= threshold:
        return WORSENED, change
    return NO_CHANGE, change
