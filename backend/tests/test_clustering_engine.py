import pytest
from unittest.mock import MagicMock
from app.services.clustering_engine import clustering_engine
from app.models.models import CitizenReport, IssueCluster, AnalysisRun, Priority

@pytest.fixture
def mock_db_for_split(monkeypatch):
    db = MagicMock()
    
    # Mocking Spatial DBSCAN
    mock_cluster_result = MagicMock()
    # Reports 1, 2, 3 in cluster 0
    mock_cluster_result.fetchall.return_value = [(1, 0), (2, 0), (3, 0)]
    
    # Mocking Centroid
    mock_centroid = MagicMock()
    mock_centroid.scalar.return_value = "POINT(0 0)"
    
    # Mocking Split Query
    mock_split_result = MagicMock()
    # distance > 0.35 means split. 
    # Let 1 and 2 be close to centroid, 3 be far.
    row1 = MagicMock(); row1.id = 1; row1.distance = 0.1
    row2 = MagicMock(); row2.id = 2; row2.distance = 0.1
    row3 = MagicMock(); row3.id = 3; row3.distance = 0.4
    mock_split_result.fetchall.return_value = [row1, row2, row3]
    
    def execute_side_effect(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "ST_ClusterDBSCAN" in stmt_str:
            return mock_cluster_result
        elif "centroid c" in stmt_str:
            return mock_split_result
        elif "ST_Centroid" in stmt_str:
            return mock_centroid
        return MagicMock()
        
    db.execute.side_effect = execute_side_effect
    
    citizen_report_query_mock = MagicMock()
    report1 = CitizenReport(id=1, sector="water", urgency_score=5)
    report2 = CitizenReport(id=2, sector="water", urgency_score=5)
    report3 = CitizenReport(id=3, sector="water", urgency_score=5)
    citizen_report_query_mock.filter.return_value.all.side_effect = [
        [], # pending_reports
        [], # gazetteer_reports
        [report1, report2], # cluster 1 reports
        [report3] # cluster 2 reports
    ]

    from app.models.models import AdminRegion, Indicator
    def query_side_effect(model):
        if model is CitizenReport:
            return citizen_report_query_mock
        q = MagicMock()
        if model is AdminRegion:
            region_mock = MagicMock()
            region_mock.id = 1
            region_mock.population = 1000.0
            q.get.return_value = region_mock
            q.filter.return_value.first.return_value = region_mock
        elif model is Indicator:
            # No indicator rows in this fixture -- neither vulnerability nor
            # the delivery-gap signal (Phase 13) are what this test is about.
            q.filter.return_value.first.return_value = None
        return q
    db.query.side_effect = query_side_effect
    
    db.added_objects = []
    def add_side_effect(obj):
        if isinstance(obj, AnalysisRun) and obj.id is None:
            obj.id = 99
        if obj not in db.added_objects:
            db.added_objects.append(obj)
    db.add.side_effect = add_side_effect
    
    # Mock dependencies
    class MockGemini:
        def generate_policy_brief(self, data):
            return {"summary": "S", "why_prioritized": "W", "fiscal_gap_analysis": "F", "recommended_action": "R"}
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGemini())
    
    class MockVerifier:
        def verify_brief(self, text, bundle):
            return {"verified": True, "unverified_numbers": []}
    monkeypatch.setattr("app.services.clustering_engine.verification_engine", MockVerifier())
    
    return db


def test_semantic_clustering_split(mock_db_for_split):
    # During development, a genuine same-issue multilingual pair (English/Kannada about a broken pipe)
    # yielded a cosine distance of ~0.12 against gemini-embedding-001.
    # A completely unrelated issue in the same block yielded a distance of ~0.42.
    # Threshold is set at 0.35.
    
    clustering_engine.process_and_prioritize(mock_db_for_split)
    
    clusters = [obj for obj in mock_db_for_split.added_objects if isinstance(obj, IssueCluster)]
    
    # We started with 1 spatial cluster (id 0) containing [1, 2, 3].
    # Report 3 should be split out into a new cluster.
    # Therefore we expect 2 IssueCluster objects to be created.
    assert len(clusters) == 2
    
    # Report count should be 2 for the first cluster and 1 for the second.
    # The order of insertion matches the iteration of final_cluster_map items.
    assert clusters[0].report_count == 2
    assert clusters[1].report_count == 1

def test_clustering_engine_retries_pending_reports(monkeypatch):
    db = MagicMock()
    
    pending_report = CitizenReport(
        id=99,
        status="pending_analysis",
        raw_text="Test pending report",
        region_id=None
    )
    
    # Setup db.query to return the pending report first, then empty for others
    citizen_report_query_mock = MagicMock()
    # It gets called for pending_reports, then gazetteer_reports, then clusters...
    # We will simulate 0 spatial clusters so it doesn't query further.
    citizen_report_query_mock.filter.return_value.all.side_effect = [
        [pending_report], # pending_reports
        []  # gazetteer_reports
    ]
    
    def query_side_effect(model):
        if model is CitizenReport:
            return citizen_report_query_mock
        return MagicMock()
    db.query.side_effect = query_side_effect
    
    db.execute.return_value.fetchall.return_value = [] # no spatial clusters
    
    class MockGemini:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": "Translated pending",
                "sector": "roads",
                "specific_issue": "pothole",
                "urgency_score": 4.0,
                "sentiment": "negative",
                "pii_redacted_text": "Translated pending"
            }
        def get_embedding(self, text):
            return [0.1] * 768
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGemini())
    
    clustering_engine.process_and_prioritize(db)
    
    # Assert that the pending report was updated and committed
    assert pending_report.status == "complete"
    assert pending_report.english_translation == "Translated pending"
    assert pending_report.sector == "roads"
    assert pending_report.urgency_score == 4.0
    assert pending_report.embedding == [0.1] * 768
    assert pending_report.raw_text == "Redacted"
