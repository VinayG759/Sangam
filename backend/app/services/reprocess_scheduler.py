import asyncio
import logging

logger = logging.getLogger(__name__)

# Turning raw citizen reports into what the dashboard shows (clusters,
# priorities, evidence bundles, policy briefs) is a heavy batch job --
# clustering_engine.process_and_prioritize rebuilds the full analysis from
# every report in the table, using a sync DB session, and calls Gemini once
# per priority for its policy brief. Running it after every single message
# would be slow and wasteful, especially when several reports arrive close
# together (e.g. a burst of Telegram messages). This debounces: the first
# ingestion after an idle period schedules a run DEBOUNCE_SECONDS later;
# any ingestion that lands while a run is already scheduled or in flight is
# a no-op, since the pending run will pick it up too. Previously this step
# only ran when someone manually POSTed /api/v1/reprocess.
DEBOUNCE_SECONDS = 15

_pending = False
_lock = asyncio.Lock()


def schedule_reprocess() -> None:
    """
    Fire-and-forget: call this after a citizen report is successfully
    ingested. Safe to call from any request handler -- never raises, never
    blocks the caller.
    """
    asyncio.create_task(_schedule())


async def _schedule() -> None:
    global _pending
    async with _lock:
        if _pending:
            return
        _pending = True
    asyncio.create_task(_run_after_debounce())


async def _run_after_debounce() -> None:
    global _pending
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        await _run_reprocess()
    finally:
        async with _lock:
            _pending = False


async def _run_reprocess() -> None:
    # process_and_prioritize is sync (it uses PostGIS-heavy multi-step
    # transactions via a sync Session, per the existing /reprocess route's
    # own docstring) -- run it off the event loop thread so it can't block
    # other requests being served concurrently.
    def _sync_run() -> None:
        from app.db import SessionLocal
        from app.services.clustering_engine import clustering_engine

        db = SessionLocal()
        try:
            clustering_engine.process_and_prioritize(db)
        finally:
            db.close()

    try:
        await asyncio.to_thread(_sync_run)
        logger.info("Background reprocess completed successfully.")
    except Exception as e:
        logger.error(f"Background reprocess failed: {e}")
