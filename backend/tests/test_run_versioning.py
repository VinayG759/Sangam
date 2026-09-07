import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.models import AnalysisRun, IssueCluster, Priority, EvidenceBundle, NarrativeBrief, CitizenReport, Indicator
from app.services.clustering_engine import clustering_engine
from app.main import app
from app.db import get_db

@pytest.fixture
def mock_db():
    db = MagicMock()
    
    # For spatial clustering query
    mock_cluster_result = MagicMock()
    mock_cluster_result.fetchall.return_value = [(1, 0), (2, 0)]
    
    # centroid and region queries
    mock_centroid = MagicMock()
    mock_centroid.scalar.return_value = "POINT(0 0)"
    
    mock_region_row = MagicMock()
    mock_region_row.first.return_value = (1,)

    # Hotspot clock query (SELECT now(), MIN(reported_at) ...) -- not what
    # either test here exercises, so an oldest_report_at predating the
    # window is enough to keep it out of the way.
    mock_hotspot_clock = MagicMock()
    mock_hotspot_clock.first.return_value = (datetime.utcnow(), datetime.utcnow() - timedelta(days=30))

    # Return mock values based on query
    def execute_side_effect(stmt, *args, **kwargs):
        if "ST_ClusterDBSCAN" in str(stmt):
            return mock_cluster_result
        elif "ST_Centroid" in str(stmt):
            return mock_centroid
        elif "MIN(reported_at)" in str(stmt):
            return mock_hotspot_clock
        elif "admin_regions" in str(stmt):
            return mock_region_row
        return MagicMock()
        
    db.execute.side_effect = execute_side_effect
    
    # Mocking db.query
    def query_side_effect(model):
        q = MagicMock()
        if model is CitizenReport:
            report1 = CitizenReport(id=1, sector="water", urgency_score=5)
            report2 = CitizenReport(id=2, sector="water", urgency_score=5)
            q.filter.return_value.all.return_value = [report1, report2]
            q.filter.return_value.first.return_value = report1
            return q

        if model is Indicator:
            # No indicator data in this fixture -- vulnerability_index falls
            # back to its 0.5 default, and no delivery-gap signal is present
            # (both behaviors this test doesn't exercise), matching what a
            # real query returns when no row matches.
            q.filter.return_value.first.return_value = None
            return q

        region_mock = MagicMock()
        region_mock.id = 1
        region_mock.population = 1000.0
        q.get.return_value = region_mock
        q.filter.return_value.first.return_value = region_mock

        return q
    
    db.query.side_effect = query_side_effect
    
    # Track added objects
    db.added_objects = []
    # Use a variable to track IDs across clearing added_objects
    db.run_id_counter = 0

    def add_side_effect(obj):
        if isinstance(obj, AnalysisRun):
            if obj.id is None:
                db.run_id_counter += 1
                obj.id = db.run_id_counter
        # if the object is being updated (e.g. status), it's already in the list
        if obj not in db.added_objects:
            db.added_objects.append(obj)
    db.add.side_effect = add_side_effect
    
    return db


def test_consecutive_runs_separate_ids(mock_db, monkeypatch):
    class MockGemini:
        def generate_policy_brief(self, data):
            return {"summary": "S", "why_prioritized": "W", "fiscal_gap_analysis": "F", "recommended_action": "R"}
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGemini())
    
    # Mock verifier to avoid strict JSON output issues
    class MockVerifier:
        def verify_brief(self, text, bundle):
            return {"verified": True, "unverified_numbers": []}
    monkeypatch.setattr("app.services.clustering_engine.verification_engine", MockVerifier())

    # Run 1
    clustering_engine.process_and_prioritize(mock_db)
    
    runs = [obj for obj in mock_db.added_objects if isinstance(obj, AnalysisRun)]
    assert len(runs) >= 1
    run1 = runs[0]
    assert run1.status == "complete"
    
    clusters_r1 = [o for o in mock_db.added_objects if isinstance(o, IssueCluster)]
    assert len(clusters_r1) > 0
    assert clusters_r1[0].run_id == run1.id
    
    # Clear added objects for run 2
    mock_db.added_objects.clear()
    
    # Run 2
    clustering_engine.process_and_prioritize(mock_db)
    
    runs2 = [obj for obj in mock_db.added_objects if isinstance(obj, AnalysisRun)]
    assert len(runs2) >= 1
    run2 = runs2[0]
    assert run2.id > run1.id
    
    clusters_r2 = [o for o in mock_db.added_objects if isinstance(o, IssueCluster)]
    assert len(clusters_r2) > 0
    assert clusters_r2[0].run_id == run2.id
    assert run1.id != run2.id


def test_forced_mid_run_failure(mock_db, monkeypatch):
    class MockGeminiFail:
        def generate_policy_brief(self, data):
            raise Exception("Forced Gemini Failure")
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGeminiFail())
    
    with pytest.raises(Exception, match="Forced Gemini Failure"):
        clustering_engine.process_and_prioritize(mock_db)
    
    # Check that UPDATE analysis_runs SET status = 'failed' was called
    update_calls = [call for call in mock_db.execute.call_args_list if "UPDATE analysis_runs" in str(call[0][0])]
    assert len(update_calls) == 1
    assert update_calls[0][0][1]["run_id"] is not None


def test_route_returns_explicit_no_data_yet_response():
    client = TestClient(app)
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # No completed run
    mock_session.execute.return_value = mock_result
    
    app.dependency_overrides[get_db] = lambda: mock_session
    
    # Test overview
    resp = client.get("/api/v1/overview")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No analysis has completed yet."

    # Test priorities
    resp = client.get("/api/v1/priorities")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No analysis has completed yet."

    # Test clusters
    resp = client.get("/api/v1/clusters")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No analysis has completed yet."

    # Test reports
    resp = client.get("/api/v1/reports")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No analysis has completed yet."

    app.dependency_overrides.clear()
