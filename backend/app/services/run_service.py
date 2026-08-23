import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AnalysisRun

logger = logging.getLogger(__name__)

async def get_latest_complete_run_id_async(db: AsyncSession) -> int | None:
    """
    Get the ID of the most recently completed analysis run asynchronously.
    Used by read routes to ensure they only serve complete data.
    """
    stmt = select(AnalysisRun.id).where(AnalysisRun.status == "complete").order_by(AnalysisRun.id.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

def get_latest_complete_run_id(db: Session) -> int | None:
    """
    Get the ID of the most recently completed analysis run synchronously.
    """
    stmt = select(AnalysisRun.id).where(AnalysisRun.status == "complete").order_by(AnalysisRun.id.desc()).limit(1)
    result = db.execute(stmt)
    return result.scalar_one_or_none()
