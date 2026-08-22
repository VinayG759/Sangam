from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from app.db import get_db
from app.models.models import Priority, IssueCluster, AdminRegion, CitizenReport, Indicator, Expenditure, EvidenceBundle, NarrativeBrief
from app.services.simulation_engine import simulation_engine
from app.services.gemini_service import gemini_service
from app.services.clustering_engine import clustering_engine
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["Priorities & Actions"])

class SimulationRequest(BaseModel):
    available_budget: float
    strategy: str = "equity"  # equity or reach

class CitizenInflowRequest(BaseModel):
    text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

@router.get("/priorities")
async def get_priorities(
    sector: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns ranked priorities with index scores, report counts, and region references.
    """
    try:
        stmt = (
            select(Priority)
            .join(IssueCluster)
            .options(selectinload(Priority.cluster))
        )

        if sector:
            stmt = stmt.where(IssueCluster.sector == sector)
        if verdict:
            stmt = stmt.where(Priority.verdict == verdict)

        # Order descending by priority score
        stmt = stmt.order_by(Priority.score.desc())
        result = await db.execute(stmt)
        priorities = result.scalars().all()

        output = []
        for p in priorities:
            cluster = p.cluster
            # Fetch region name
            region_result = await db.execute(
                select(AdminRegion).where(AdminRegion.id == cluster.region_id)
            )
            region = region_result.scalar_one_or_none()
            region_name = region.name if region else "Unknown Ward"

            output.append({
                "id": p.id,
                "cluster_id": cluster.id,
                "title": cluster.title,
                "sector": cluster.sector,
                "score": p.score,
                "verdict": p.verdict,
                "report_count": cluster.report_count,
                "region_name": region_name,
                "details": p.details
            })
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/priorities/{priority_id}")
async def get_priority_detail(priority_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns details for a priority, including the immutable evidence bundle and narrative brief.
    """
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority_id)
        .options(
            selectinload(Priority.evidence_bundle),
            selectinload(Priority.narrative_brief)
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Priority record not found")

    evidence = p.evidence_bundle
    brief = p.narrative_brief

    return {
        "id": p.id,
        "score": p.score,
        "verdict": p.verdict,
        "evidence_bundle": evidence.data if evidence else {},
        "narrative_brief": {
            "summary": brief.summary if brief else "Brief missing.",
            "why_prioritized": brief.why_prioritized if brief else "Not analyzed.",
            "fiscal_gap_analysis": brief.fiscal_gap_analysis if brief else "No gap analysis.",
            "recommended_action": brief.recommended_action if brief else "No recommendation."
        }
    }

@router.post("/simulate")
async def run_simulation(req: SimulationRequest, db: AsyncSession = Depends(get_db)):
    """
    Interactive what-if budget allocator simulator.
    """
    try:
        result = await db.execute(
            select(Priority)
            .options(
                selectinload(Priority.cluster),
                selectinload(Priority.evidence_bundle)
            )
        )
        priorities = result.scalars().all()

        sim_input = []
        for p in priorities:
            cluster = p.cluster
            eb = p.evidence_bundle
            cost_gap = 1500000.0 * cluster.report_count
            allocated_budget = 0.0
            vulnerability = 0.5

            if eb:
                cost_gap = eb.data.get("estimated_cost", cost_gap)
                allocated_budget = eb.data.get("allocated_budget", 0.0)
                vulnerability = eb.data.get("vulnerability_index", 0.5)

            sim_input.append({
                "cluster_id": cluster.id,
                "title": cluster.title,
                "sector": cluster.sector,
                "score": p.score,
                "reports_count": cluster.report_count,
                "vulnerability": vulnerability,
                "allocated_budget": allocated_budget,
                "estimated_cost": cost_gap
            })

        result = simulation_engine.run_simulation(
            available_budget=req.available_budget,
            priorities=sim_input,
            strategy=req.strategy
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest/citizen")
async def ingest_citizen_report(
    req: CitizenInflowRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a new citizen voice/text report, translate, analyze PII, and save to DB.
    """
    try:
        # Run Call 1 Gemini analysis
        analysis = gemini_service.analyze_citizen_report(req.text)

        # Get semantic embedding
        embedding = gemini_service.get_embedding(analysis.get("english_translation", req.text))

        # Save report
        location_wkt = None
        if req.latitude is not None and req.longitude is not None:
            location_wkt = f"SRID=4326;POINT({req.longitude} {req.latitude})"

        report = CitizenReport(
            raw_text=req.text,
            detected_language=analysis.get("original_language", "en"),
            english_translation=analysis.get("english_translation", req.text),
            sector=analysis.get("sector", "other"),
            specific_issue=analysis.get("specific_issue", ""),
            urgency_score=analysis.get("urgency_score", 1.0),
            sentiment=analysis.get("sentiment", "neutral"),
            pii_redacted_text=analysis.get("pii_redacted_text", req.text),
            location=location_wkt,
            embedding=embedding
        )
        db.add(report)
        await db.flush()

        return {
            "status": "success",
            "report_id": report.id,
            "analysis_extracted": analysis
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reprocess")
async def trigger_reprocessing(db: AsyncSession = Depends(get_db)):
    """
    Trigger the spatial clustering and priority scoring pipeline manually.
    Note: The clustering engine uses a sync session internally since it performs
    complex multi-step transactions with PostGIS operations.
    """
    from app.db import SessionLocal
    try:
        sync_db = SessionLocal()
        try:
            clustering_engine.process_and_prioritize(sync_db)
        finally:
            sync_db.close()
        return {"status": "success", "message": "Reprocessing pipeline completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
