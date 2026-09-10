import io
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import pypdf

from app.services.pdf_export import render_briefing_pdf
from app.main import app
from app.db import get_db
from app.models.models import AnalysisRun, Priority, IssueCluster, AdminRegion, EvidenceBundle, NarrativeBrief


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_render_briefing_pdf_structure_and_magic_header():
    priority = {
        "id": 101,
        "score": 92.4,
        "verdict": "UNSERVED_GAP",
        "region_name": "Hiriyur",
        "sector": "water",
        "report_count": 8
    }
    evidence = {
        "report_count": 8,
        "average_urgency": 4.5,
        "vulnerability_index": 0.62,
        "allocated_budget": 0.0,
        "estimated_cost": 4500000.0,
        "delivery_rate": 0.72,
        "delivery_benchmark": 0.88,
        "expenditure_records": [
            {"title": "Borewell Water Tank", "amount": 1500000.0, "status": "stalled"}
        ],
        "citizen_quotes": [
            "Severe shortage of clean drinking water in Hiriyur."
        ]
    }
    brief = {
        "summary": "Critical drinking water deficiency in Hiriyur with 8 unserved citizen reports.",
        "why_prioritized": "High urgency reports combined with zero public expenditure allocation.",
        "fiscal_gap_analysis": "₹45.00 Lakh needed to restore water supply pipelines.",
        "recommended_action": "Sanction immediate pipeline repair and borewell installation."
    }

    pdf_bytes = render_briefing_pdf(priority, evidence, brief)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF"), "PDF must start with %PDF magic header"
    assert len(pdf_bytes) > 1000

    # Extract text with pypdf and verify all expected key fields
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    extracted_text = ""
    for page in reader.pages:
        extracted_text += page.extract_text() + "\n"

    assert "UNSERVED_GAP" in extracted_text
    assert "92.4" in extracted_text
    assert "Hiriyur" in extracted_text
    assert "Critical drinking water deficiency" in extracted_text
    assert "Why Prioritized" in extracted_text
    assert "Fiscal Gap Analysis" in extracted_text
    assert "Recommended Action" in extracted_text
    assert "Severe shortage of clean drinking water" in extracted_text
    assert "Borewell Water Tank" in extracted_text


def test_export_priority_pdf_endpoint(client):
    mock_session = AsyncMock()

    # Mock run ID query
    mock_run_result = MagicMock()
    mock_run_result.scalar.return_value = 1
    mock_run_result.scalar_one_or_none.return_value = 1

    # Mock priority object
    region = MagicMock()
    region.name = "Kalaburagi"
    
    cluster = MagicMock()
    cluster.sector = "roads"
    cluster.report_count = 14
    cluster.region = region

    evidence = MagicMock()
    evidence.data = {
        "report_count": 14,
        "allocated_budget": 500000.0,
        "estimated_cost": 2500000.0
    }

    brief = MagicMock()
    brief.summary = "Damaged road stretch near bus terminal."
    brief.why_prioritized = "High traffic route severely damaged."
    brief.fiscal_gap_analysis = "Budget shortfall of ₹20 Lakh."
    brief.recommended_action = "Resurface 2km stretch."

    priority = MagicMock()
    priority.id = 42
    priority.score = 78.5
    priority.verdict = "STALLED_ALLOCATION"
    priority.details = None
    priority.evidence_bundle = evidence
    priority.narrative_brief = brief
    priority.cluster = cluster

    mock_priority_result = MagicMock()
    mock_priority_result.scalar_one_or_none.return_value = priority

    async def mock_execute(stmt):
        stmt_str = str(stmt).lower()
        if "analysis_runs" in stmt_str:
            return mock_run_result
        return mock_priority_result

    mock_session.execute = mock_execute

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/api/v1/export/42.pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert 'attachment; filename="briefing_42.pdf"' in response.headers.get("content-disposition", "")
        assert response.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_export_priority_pdf_not_found(client):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/api/v1/export/999.pdf")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_admin_runs_token_protection(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "super_secret_admin_token")

    # 1. Missing token -> 401
    res_missing = client.get("/api/v1/admin/runs")
    assert res_missing.status_code == 401
    assert "Invalid or missing admin token" in res_missing.json()["detail"]

    # 2. Wrong token -> 401
    res_wrong = client.get("/api/v1/admin/runs", headers={"X-Admin-Token": "incorrect_token"})
    assert res_wrong.status_code == 401

    # 3. Correct token -> 200 and returns run list
    mock_session = AsyncMock()
    run1 = MagicMock()
    run1.id = 2
    run1.status = "complete"
    run1.started_at = datetime(2026, 8, 22, 10, 0, 0)
    run1.completed_at = datetime(2026, 8, 22, 10, 5, 0)
    run1.note = "Scheduled daily run"

    run2 = MagicMock()
    run2.id = 1
    run2.status = "complete"
    run2.started_at = datetime(2026, 8, 21, 10, 0, 0)
    run2.completed_at = datetime(2026, 8, 21, 10, 4, 0)
    run2.note = "Initial seed run"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [run1, run2]
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        res_ok = client.get("/api/v1/admin/runs", headers={"X-Admin-Token": "super_secret_admin_token"})
        assert res_ok.status_code == 200
        runs_data = res_ok.json()
        assert len(runs_data) == 2
        assert runs_data[0]["id"] == 2
        assert runs_data[0]["status"] == "complete"
        assert runs_data[0]["note"] == "Scheduled daily run"
        assert runs_data[1]["id"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
