import os
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.models import AnalysisRun, CitizenReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


async def verify_admin_token(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")):
    admin_token = os.environ.get("ADMIN_TOKEN")
    if not admin_token or not x_admin_token or x_admin_token != admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token"
        )
    return True


@router.get("/runs")
async def get_admin_runs(
    db: AsyncSession = Depends(get_db),
    authorized: bool = Depends(verify_admin_token)
):
    """
    Returns list of analysis runs, newest first.
    Protected by X-Admin-Token header matching ADMIN_TOKEN env var.
    """
    result = await db.execute(
        select(AnalysisRun).order_by(AnalysisRun.id.desc())
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "note": r.note
        }
        for r in runs
    ]
