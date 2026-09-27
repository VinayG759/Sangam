"""
Budget simulator: "I have this much money — what should I fund?"

Greedy, on purpose: sort the fundable recommendations by the chosen strategy
and fund in order while money remains. An official can follow every step,
which matters more than the last few percent an exact optimiser would find.

Only UNSERVED_GAP recommendations are fundable. Stalled allocations and
delivery gaps need an audit, not more money, so they are listed separately.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.core.runs import latest_complete_run
from app.models import Priority, Region

router = APIRouter(prefix="/api/v1", tags=["simulator"])

Strategy = Literal["balanced", "reach", "equity"]


class SimulationRequest(BaseModel):
    budget: float = Field(gt=0)
    strategy: Strategy = "balanced"


def order_candidates(candidates: list[dict], strategy: Strategy) -> list[dict]:
    keys = {
        "balanced": lambda c: c["score"] / c["cost"],  # priority per rupee
        "reach": lambda c: c["beneficiaries"] / c["cost"],  # people served per rupee
        "equity": lambda c: c["deficit"],  # worst-served first
    }
    return sorted(candidates, key=keys[strategy], reverse=True)


def allocate(candidates: list[dict], budget: float) -> tuple[list[dict], float]:
    funded, spent = [], 0.0
    for candidate in candidates:
        if spent + candidate["cost"] <= budget:
            funded.append(candidate)
            spent += candidate["cost"]
    return funded, spent


@router.post("/simulate")
def simulate(body: SimulationRequest, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    run = latest_complete_run(db, pack.country_code)
    if not run:
        return {"funded": [], "total_cost": 0, "beneficiaries": 0, "candidates": 0, "audit_count": 0, "notes": []}
    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    priorities = list(db.scalars(select(Priority).where(Priority.run_id == run.id, Priority.displayable.is_(True))))

    candidates = [{
        "priority_id": p.id, "rank": p.rank, "region_name": regions[p.region_id].name, "sector": p.sector,
        "score": p.score, "cost": p.estimated_cost, "beneficiaries": p.beneficiaries or 0,
        "deficit": (p.components.get("deficit") or {}).get("value", 0),
    } for p in priorities if p.verdict == "UNSERVED_GAP" and p.estimated_cost]

    funded, spent = allocate(order_candidates(candidates, body.strategy), body.budget)
    notes = [f"{pack.need(sector).label_en}: {rule.note}" for sector, rule in pack.costs.items() if pack.need(sector)]
    unpriced = sum(1 for p in priorities if p.verdict == "UNSERVED_GAP" and not p.estimated_cost)
    if unpriced:
        notes.append(f"{unpriced} unserved gaps have no cost model or statistic yet and are not included.")
    return {
        "currency": pack.currency, "currency_symbol": pack.currency_symbol, "strategy": body.strategy,
        "budget": body.budget, "total_cost": round(spent), "remaining": round(body.budget - spent),
        "beneficiaries": sum(c["beneficiaries"] for c in funded), "candidates": len(candidates),
        "funded": funded,
        "audit_count": sum(1 for p in priorities if p.verdict in ("STALLED_ALLOCATION", "DELIVERY_GAP", "PLANNED_NOT_STARTED")),
        "notes": notes,
    }
