"""
Tests for the background reprocess debounce in app.services.reprocess_scheduler.

ingest_citizen_message used to leave the dashboard stale until someone
manually POSTed /api/v1/reprocess. schedule_reprocess() now runs that
pipeline automatically a short while after ingestion -- these tests verify
the debounce actually collapses a burst of calls into one run, rather than
running the (expensive, Gemini-calling) pipeline once per report.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

import app.services.reprocess_scheduler as scheduler


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    # Module-level debounce state must not leak between tests.
    scheduler._pending = False
    yield
    scheduler._pending = False


@pytest.fixture
def fast_debounce(monkeypatch):
    monkeypatch.setattr(scheduler, "DEBOUNCE_SECONDS", 0.05)


@pytest.mark.asyncio
async def test_schedule_reprocess_runs_once_after_debounce(fast_debounce):
    mock_run = MagicMock()
    with patch("app.services.clustering_engine.clustering_engine") as mock_engine, \
         patch("app.db.SessionLocal") as mock_session_local:
        mock_engine.process_and_prioritize = mock_run

        scheduler.schedule_reprocess()
        await asyncio.sleep(0.2)  # well past the debounced 0.05s

        mock_run.assert_called_once()
        mock_session_local.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_calls_during_debounce_window_collapse_into_one_run(fast_debounce):
    mock_run = MagicMock()
    with patch("app.services.clustering_engine.clustering_engine") as mock_engine, \
         patch("app.db.SessionLocal"):
        mock_engine.process_and_prioritize = mock_run

        # Five ingestions arriving in quick succession (well inside the
        # debounce window) must not each schedule their own run.
        for _ in range(5):
            scheduler.schedule_reprocess()
        await asyncio.sleep(0.2)

        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_a_call_after_a_run_completes_schedules_a_new_one(fast_debounce):
    mock_run = MagicMock()
    with patch("app.services.clustering_engine.clustering_engine") as mock_engine, \
         patch("app.db.SessionLocal"):
        mock_engine.process_and_prioritize = mock_run

        scheduler.schedule_reprocess()
        await asyncio.sleep(0.2)
        assert mock_run.call_count == 1

        # A later report, after the debounced run already finished, must
        # schedule its own run rather than being silently dropped.
        scheduler.schedule_reprocess()
        await asyncio.sleep(0.2)
        assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_engine_failure_does_not_raise(fast_debounce):
    with patch("app.services.clustering_engine.clustering_engine") as mock_engine, \
         patch("app.db.SessionLocal"):
        mock_engine.process_and_prioritize = MagicMock(side_effect=RuntimeError("boom"))

        scheduler.schedule_reprocess()
        await asyncio.sleep(0.2)  # must not raise / crash the event loop

        # The pending flag must still clear even after a failed run, so a
        # later report can trigger another attempt.
        assert scheduler._pending is False
