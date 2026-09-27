"""Admin endpoints to start an analysis run and see run history."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import AIClient, get_ai
from app.core.db import get_db, new_session
from app.core.pack import Pack, get_pack
from app.core.security import require_admin
from app.features.analysis.run import run_analysis
from app.models import AnalysisRun

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _run_in_background(run_id: int, ai: AIClient, pack: Pack) -> None:
    with new_session() as db:
        run_analysis(db, ai, pack, run_id=run_id)


@router.post("/runs", status_code=202)
def start_run(background: BackgroundTasks, db: Session = Depends(get_db), ai: AIClient = Depends(get_ai),
              pack: Pack = Depends(get_pack)):
    run = AnalysisRun(country_code=pack.country_code, status="running")
    db.add(run)
    db.commit()
    background.add_task(_run_in_background, run.id, ai, pack)
    return {"run_id": run.id, "status": run.status}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    runs = db.scalars(select(AnalysisRun).where(AnalysisRun.country_code == pack.country_code)
                      .order_by(AnalysisRun.id.desc()).limit(20))
    return [{"id": r.id, "status": r.status, "started_at": r.started_at.isoformat(),
             "completed_at": r.completed_at.isoformat() if r.completed_at else None,
             "error": r.error, "stats": r.stats} for r in runs]
