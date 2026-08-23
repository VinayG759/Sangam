"""
Tests for the safety guards in app.utils.db_seed.

seed_data() deletes every row in citizen_reports, expenditures, indicators,
and admin_regions before writing its demo dataset. Two guards gate that:

1. tracking_id is only ever set by the real ingestion path (never by this
   script), so its presence means real citizen data exists -- seeding
   refuses outright (RealDataPresentError) unless FORCE_RESEED=true.
2. Any citizen_reports rows at all (real or previously-seeded demo data)
   mean seeding already ran once -- docker-entrypoint.sh runs this on
   every container start when SEED_DB=true, with no way to tell "first
   boot" from "the Nth redeploy", so without this a redeploy silently
   wipes the demo dataset (and any /reprocess-derived clusters/priorities)
   back to empty. Guard 2 makes that a quiet, expected no-op instead.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.utils.db_seed import seed_data, RealDataPresentError


def _mock_session(real_count=0, total_count=0):
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.count.return_value = real_count
    mock_session.query.return_value.count.return_value = total_count
    return mock_session


class TestRealDataGuard:
    def test_refuses_to_seed_when_real_reports_exist(self, monkeypatch):
        monkeypatch.delenv("FORCE_RESEED", raising=False)
        mock_session = _mock_session(real_count=3, total_count=3)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with pytest.raises(RealDataPresentError):
                seed_data()

        # Refusal must happen before any destructive delete is issued.
        mock_session.query.return_value.delete.assert_not_called()

    def test_force_reseed_env_var_overrides_the_guard(self, monkeypatch):
        monkeypatch.setenv("FORCE_RESEED", "true")
        mock_session = _mock_session(real_count=3, total_count=3)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with patch("app.utils.db_seed.gemini_service") as mock_gemini:
                mock_gemini.get_embedding.return_value = [0.0] * 768
                seed_data()  # should not raise despite real reports present

        mock_session.commit.assert_called()


class TestIdempotencyGuard:
    def test_skips_seed_when_demo_data_already_exists(self, monkeypatch):
        # No real (tracking_id) reports, but the table isn't empty --
        # a prior demo seed already ran.
        monkeypatch.delenv("FORCE_RESEED", raising=False)
        mock_session = _mock_session(real_count=0, total_count=15)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            seed_data()  # should not raise, should not re-seed

        mock_session.query.return_value.delete.assert_not_called()
        mock_session.commit.assert_not_called()

    def test_force_reseed_overrides_the_idempotency_guard(self, monkeypatch):
        monkeypatch.setenv("FORCE_RESEED", "true")
        mock_session = _mock_session(real_count=0, total_count=15)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with patch("app.utils.db_seed.gemini_service") as mock_gemini:
                mock_gemini.get_embedding.return_value = [0.0] * 768
                seed_data()  # should not raise, should re-seed

        mock_session.commit.assert_called()

    def test_proceeds_when_no_data_exists(self, monkeypatch):
        monkeypatch.delenv("FORCE_RESEED", raising=False)
        mock_session = _mock_session(real_count=0, total_count=0)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with patch("app.utils.db_seed.gemini_service") as mock_gemini:
                mock_gemini.get_embedding.return_value = [0.0] * 768
                seed_data()  # should not raise

        mock_session.commit.assert_called()
