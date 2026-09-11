import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models.models import CitizenReport
from app.services.ingestion_service import ingest_citizen_message
from app.utils.hashing import hash_channel_user


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.asyncio
async def test_per_reporter_cap_rejects_11th_submission_without_gemini_call(monkeypatch):
    """
    Assert that when a reporter has already submitted 10 reports today,
    an 11th report is rejected early without invoking Gemini analysis or embedding.
    """
    mock_session = AsyncMock()
    # Mock count query returning 10
    count_result = MagicMock()
    count_result.scalar.return_value = 10
    mock_session.execute.return_value = count_result

    # Mock gemini_service to blow up if called
    mock_gemini = MagicMock()
    mock_gemini.analyze_citizen_report.side_effect = AssertionError("Gemini should NOT have been called!")
    mock_gemini.get_embedding.side_effect = AssertionError("Gemini embedding should NOT have been called!")

    import app.services.ingestion_service as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "gemini_service", mock_gemini)

    res = await ingest_citizen_message(
        db=mock_session,
        text="Flood report number 11",
        channel="telegram",
        channel_user_id="spammer_123"
    )

    assert res["status"] == "rejected"
    assert "Maximum reports for today reached" in res["message"]
    assert res["report_id"] is None
    assert res["tracking_id"] is None
    # Verify report was never added to DB
    mock_session.add.assert_not_called()
    mock_gemini.analyze_citizen_report.assert_not_called()


@pytest.mark.asyncio
async def test_coordinated_flood_detection_flags_near_identical_embeddings(monkeypatch):
    """
    Assert that two reports from distinct reporters with near-identical embeddings
    (cosine distance < 0.03 / similarity > 0.97) within the 1-hour window
    both get flagged_coordinated=True.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # Create prior report from a different reporter within the last hour
    prior_report = CitizenReport(
        id=50,
        reporter_hash=hash_channel_user("reporter_alpha"),
        reported_at=datetime.utcnow() - timedelta(minutes=15),
        embedding=[0.1] * 768,
        flagged_coordinated=False
    )

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        stmt_str = str(stmt).lower()
        mock_res = MagicMock()
        if "count" in stmt_str:
            # 0 prior reports today for this reporter
            mock_res.scalar.return_value = 0
            return mock_res
        elif "<=>" in stmt_str or "cosine_distance" in stmt_str or "citizen_reports" in stmt_str:
            # Coordinated flood query returning prior_report
            mock_res.scalars.return_value.all.return_value = [prior_report]
            mock_res.all.return_value = [prior_report]
            return mock_res
        mock_res.scalars.return_value.all.return_value = []
        mock_res.all.return_value = []
        return mock_res

    mock_session.execute = mock_execute

    class MockGemini:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": "Damaged water pipe flooding street",
                "sector": "water",
                "specific_issue": "pipe leak",
                "urgency_score": 4.0,
                "sentiment": "negative",
                "pii_redacted_text": "Damaged water pipe flooding street"
            }
        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "gemini_service", MockGemini())
    monkeypatch.setattr(ingestion_mod, "resolve_location_with_confidence", AsyncMock(return_value={
        "region": None, "candidate": None, "confidence": None, "score": 0
    }))

    res = await ingest_citizen_message(
        db=mock_session,
        text="Damaged water pipe flooding street",
        channel="telegram",
        channel_user_id="reporter_beta"
    )

    assert res["status"] == "success"

    # Find the newly added CitizenReport
    added_report = None
    for call in mock_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, CitizenReport):
            added_report = obj
            break

    assert added_report is not None
    assert added_report.flagged_coordinated is True
    assert prior_report.flagged_coordinated is True


@pytest.mark.asyncio
async def test_distinct_reports_different_embeddings_not_flagged(monkeypatch):
    """
    Assert that reports with different embeddings (no matches with cosine distance < 0.03)
    are not flagged as coordinated.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    async def mock_execute(stmt):
        stmt_str = str(stmt).lower()
        mock_res = MagicMock()
        if "count" in stmt_str:
            mock_res.scalar.return_value = 0
            return mock_res
        # No coordinated matches
        mock_res.scalars.return_value.all.return_value = []
        mock_res.all.return_value = []
        return mock_res

    mock_session.execute = mock_execute

    class MockGemini:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": "Street light broken near park",
                "sector": "electricity",
                "specific_issue": "street light",
                "urgency_score": 2.0,
                "sentiment": "neutral",
                "pii_redacted_text": "Street light broken near park"
            }
        def get_embedding(self, text):
            return [0.5] * 768

    import app.services.ingestion_service as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "gemini_service", MockGemini())
    monkeypatch.setattr(ingestion_mod, "resolve_location_with_confidence", AsyncMock(return_value={
        "region": None, "candidate": None, "confidence": None, "score": 0
    }))

    res = await ingest_citizen_message(
        db=mock_session,
        text="Street light broken near park",
        channel="web"
    )

    assert res["status"] == "success"

    added_report = None
    for call in mock_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, CitizenReport):
            added_report = obj
            break

    assert added_report is not None
    assert added_report.flagged_coordinated is False


def test_admin_flagged_endpoint_token_and_response(client, monkeypatch):
    """
    Test GET /api/v1/admin/flagged and /admin/flagged endpoint:
    - Rejects missing / invalid token with 401
    - Returns flagged reports with valid token
    """
    monkeypatch.setenv("ADMIN_TOKEN", "admin_secret_key_123")

    # 1. Missing token -> 401
    res1 = client.get("/api/v1/admin/flagged")
    assert res1.status_code == 401

    res1_compat = client.get("/admin/flagged")
    assert res1_compat.status_code == 401

    # 2. Wrong token -> 401
    res2 = client.get("/api/v1/admin/flagged", headers={"X-Admin-Token": "bad_token"})
    assert res2.status_code == 401

    # 3. Valid token -> 200 with list
    mock_session = AsyncMock()
    r1 = MagicMock()
    r1.id = 88
    r1.tracking_id = "SNG-FLAG-1"
    r1.reported_at = datetime(2026, 8, 23, 14, 0, 0)
    r1.channel = "telegram"
    r1.sector = "water"
    r1.specific_issue = "Pothole flood"
    r1.raw_text = "Flood copy 1"
    r1.flagged_coordinated = True

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [r1]
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res3 = client.get("/api/v1/admin/flagged", headers={"X-Admin-Token": "admin_secret_key_123"})
        assert res3.status_code == 200
        data = res3.json()
        assert len(data) == 1
        assert data[0]["id"] == 88
        assert data[0]["tracking_id"] == "SNG-FLAG-1"
        assert data[0]["flagged_coordinated"] is True

        # Check compat route /admin/flagged also works
        res3_compat = client.get("/admin/flagged", headers={"X-Admin-Token": "admin_secret_key_123"})
        assert res3_compat.status_code == 200
        assert res3_compat.json()[0]["id"] == 88
    finally:
        app.dependency_overrides.pop(get_db, None)
