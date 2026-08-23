"""
Tests for the real-data safety guard in app.utils.db_seed.

seed_data() deletes every row in citizen_reports, expenditures, indicators,
and admin_regions before writing its demo dataset. tracking_id is only ever
set by the real ingestion path (app.services.ingestion_service), never by
this script, so its presence is used to detect real citizen data and refuse
to proceed -- see the guard at the top of seed_data().
"""

import pytest
from unittest.mock import MagicMock, patch

from app.utils.db_seed import seed_data, RealDataPresentError


def _mock_session_with_real_report_count(count):
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.count.return_value = count
    return mock_session


class TestRealDataGuard:
    def test_refuses_to_seed_when_real_reports_exist(self, monkeypatch):
        monkeypatch.delenv("FORCE_RESEED", raising=False)
        mock_session = _mock_session_with_real_report_count(3)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with pytest.raises(RealDataPresentError):
                seed_data()

        # Refusal must happen before any destructive delete is issued.
        mock_session.query.return_value.delete.assert_not_called()

    def test_proceeds_when_no_real_reports_exist(self, monkeypatch):
        monkeypatch.delenv("FORCE_RESEED", raising=False)
        mock_session = _mock_session_with_real_report_count(0)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with patch("app.utils.db_seed.gemini_service") as mock_gemini:
                mock_gemini.get_embedding.return_value = [0.0] * 768
                seed_data()  # should not raise

        mock_session.commit.assert_called()

    def test_force_reseed_env_var_overrides_the_guard(self, monkeypatch):
        monkeypatch.setenv("FORCE_RESEED", "true")
        mock_session = _mock_session_with_real_report_count(3)

        with patch("app.utils.db_seed.SessionLocal", return_value=mock_session):
            with patch("app.utils.db_seed.gemini_service") as mock_gemini:
                mock_gemini.get_embedding.return_value = [0.0] * 768
                seed_data()  # should not raise despite real reports present

        mock_session.commit.assert_called()
