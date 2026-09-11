from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from fastapi import File, Form, UploadFile
from app.db import get_db
from app.models.models import Priority, IssueCluster, AdminRegion, CitizenReport, Indicator, Expenditure, EvidenceBundle, NarrativeBrief
from app.services.simulation_engine import simulation_engine
from app.services.gemini_service import gemini_service
from app.services.clustering_engine import clustering_engine
from app.services.pdf_export import render_briefing_pdf
from app.schemas import CitizenIngestResponse
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
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    try:
        stmt = (
            select(Priority)
            .join(IssueCluster)
            .where(Priority.run_id == run_id)
            .options(
                selectinload(Priority.cluster),
                selectinload(Priority.evidence_bundle)
            )
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
            if p.details and p.details.get("suppressed", False):
                continue
                
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
                "details": p.details,
                "list_type": p.list if p.list else "fund"
            })
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/priorities/{priority_id}")
async def get_priority_detail(priority_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns details for a priority, including the immutable evidence bundle and narrative brief.
    """
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority_id, Priority.run_id == run_id)
        .options(
            selectinload(Priority.evidence_bundle),
            selectinload(Priority.narrative_brief),
            selectinload(Priority.cluster)
        )
    )
    p = result.scalar_one_or_none()
    
    # Return 404 if not found or if the priority is suppressed (privacy floor)
    if not p or (p.details and p.details.get("suppressed", False)):
        raise HTTPException(status_code=404, detail="Priority record not found")

    evidence_data = p.evidence_bundle.data if p.evidence_bundle else {}

    return {
        "id": p.id,
        "score": p.score,
        "verdict": p.verdict,
        "evidence_bundle": evidence_data,
        "narrative_brief": {
            "summary": p.narrative_brief.summary if p.narrative_brief else "Brief missing.",
            "why_prioritized": p.narrative_brief.why_prioritized if p.narrative_brief else "Not analyzed.",
            "fiscal_gap_analysis": p.narrative_brief.fiscal_gap_analysis if p.narrative_brief else "No gap analysis.",
            "recommended_action": p.narrative_brief.recommended_action if p.narrative_brief else "No recommendation."
        }
    }

@router.get("/export/{priority_id}.pdf")
async def export_priority_pdf(priority_id: int, db: AsyncSession = Depends(get_db)):
    """
    Exports a government-ready PDF briefing note for a priority recommendation.
    """
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority_id, Priority.run_id == run_id)
        .options(
            selectinload(Priority.evidence_bundle),
            selectinload(Priority.narrative_brief),
            selectinload(Priority.cluster).selectinload(IssueCluster.region)
        )
    )
    p = result.scalar_one_or_none()

    if not p or (p.details and p.details.get("suppressed", False)):
        raise HTTPException(status_code=404, detail="Priority record not found")

    evidence_data = p.evidence_bundle.data if p.evidence_bundle else {}
    brief_data = {
        "summary": p.narrative_brief.summary if p.narrative_brief else "Brief missing.",
        "why_prioritized": p.narrative_brief.why_prioritized if p.narrative_brief else "Not analyzed.",
        "fiscal_gap_analysis": p.narrative_brief.fiscal_gap_analysis if p.narrative_brief else "No gap analysis.",
        "recommended_action": p.narrative_brief.recommended_action if p.narrative_brief else "No recommendation."
    }

    region_name = None
    sector = None
    report_count = 0
    if p.cluster:
        sector = p.cluster.sector
        report_count = getattr(p.cluster, "report_count", 0)
        if p.cluster.region:
            region_name = p.cluster.region.name

    priority_dict = {
        "id": p.id,
        "score": p.score,
        "verdict": p.verdict,
        "region_name": region_name,
        "sector": sector,
        "report_count": report_count
    }

    pdf_bytes = render_briefing_pdf(priority_dict, evidence_data, brief_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="briefing_{priority_id}.pdf"'}
    )

@router.post("/simulate")
async def run_simulation(req: SimulationRequest, db: AsyncSession = Depends(get_db)):
    """
    Interactive what-if budget allocator simulator.
    """
    from app.services.run_service import get_latest_complete_run_id_async
    run_id = await get_latest_complete_run_id_async(db)
    if run_id is None:
        raise HTTPException(status_code=404, detail="No analysis has completed yet.")

    try:
        result = await db.execute(
            select(Priority)
            .where(Priority.run_id == run_id)
            .options(
                selectinload(Priority.cluster).selectinload(IssueCluster.region),
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
                # dict.get(key, default) only falls back when the key is
                # absent -- Phase 19 made the evidence bundle store an
                # explicit vulnerability_index: null when no real indicator
                # exists (so "no data" isn't shown as a fake 0.5), so the
                # key IS present here and .get() returns that None straight
                # through, which simulation_engine.py's float() then rejects.
                vuln = eb.data.get("vulnerability_index")
                vulnerability = vuln if vuln is not None else 0.5

            # cluster.title is a generic auto-generated label -- "Cluster of
            # 5 water reports" -- shared by the format string across every
            # cluster of the same sector and size, so two different real
            # places (e.g. Hiriyur vs. Indiranagar) render as visually
            # identical truncated text in the simulator's chart and table.
            # The region name is what actually distinguishes one from
            # another; sector is already shown as its own table column and
            # as the bar's color, so it isn't repeated in the title itself.
            region_name = cluster.region.name if cluster.region else "Unknown region"
            sim_input.append({
                "cluster_id": cluster.id,
                "title": region_name,
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

@router.post("/ingest/citizen", response_model=CitizenIngestResponse)
async def ingest_citizen_report(
    text: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a new citizen voice/text/image report, translate, analyze PII, and save to DB.
    """
    from app.services.ingestion_service import ingest_citizen_message

    audio_bytes = None
    mime_type = None
    if file:
        audio_bytes = await file.read()
        mime_type = file.content_type
        if audio_bytes and len(audio_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="The media file is too large (maximum size is 10 MB)."
            )

    result = await ingest_citizen_message(
        db=db,
        text=text,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        latitude=latitude,
        longitude=longitude,
        channel="web"
    )
    return result

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
