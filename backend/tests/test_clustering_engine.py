import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from app.services.clustering_engine import clustering_engine, _is_emerging_hotspot
from app.models.models import CitizenReport, IssueCluster, AnalysisRun, Priority, AdminRegion

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
    
    # Emerging-hotspot "now"/"oldest" query: a now that predates nothing and
    # an oldest_report_at well before the window, so this fixture's own
    # is_emerging_hotspot assertions stay meaningful (cold-start gate is
    # open; the recent-count minimum is what's actually under test).
    mock_hotspot_clock = MagicMock()
    mock_hotspot_clock.first.return_value = (datetime.utcnow(), datetime.utcnow() - timedelta(days=30))

    def execute_side_effect(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "ST_ClusterDBSCAN" in stmt_str:
            return mock_cluster_result
        elif "centroid c" in stmt_str:
            return mock_split_result
        elif "ST_Centroid" in stmt_str:
            return mock_centroid
        elif "MIN(reported_at)" in stmt_str:
            return mock_hotspot_clock
        return MagicMock()

    db.execute.side_effect = execute_side_effect

    citizen_report_query_mock = MagicMock()
    # Recent (1 day old) but below HOTSPOT_MIN_RECENT_REPORTS (3) for the
    # 2-report cluster below -- exercises the real is_emerging_hotspot
    # computation rather than a value the fixture can't actually verify.
    report1 = CitizenReport(id=1, sector="water", urgency_score=5, reported_at=datetime.utcnow() - timedelta(days=1))
    report2 = CitizenReport(id=2, sector="water", urgency_score=5, reported_at=datetime.utcnow() - timedelta(days=1))
    report3 = CitizenReport(id=3, sector="water", urgency_score=5, reported_at=datetime.utcnow() - timedelta(days=1))
    citizen_report_query_mock.filter.return_value.all.side_effect = [
        [], # pending_reports
        [], # gazetteer_reports
        [report1, report2], # merge region-hint: cluster 0
        [report3], # merge region-hint: cluster 1
        [report1, report2], # Create Issue Clusters: cluster 1 reports
        [report3] # Create Issue Clusters: cluster 2 reports
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
    # Hotspot clock query (SELECT now(), MIN(reported_at) ...) -- this test
    # never reaches the clusters loop (no spatial or gazetteer clusters), so
    # the exact values don't matter, only that unpacking succeeds.
    db.execute.return_value.first.return_value = (datetime.utcnow(), None)

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


def _make_mock_db_for_merge(merge_distance: float, region2_parent_id, will_merge: bool) -> MagicMock:
    db = MagicMock()

    # No GPS-based spatial clusters -- both groups arrive via the gazetteer
    # (region_id, sector) path instead, which is where the merge gap lives.
    mock_cluster_result = MagicMock()
    mock_cluster_result.fetchall.return_value = []

    mock_centroid = MagicMock()
    mock_centroid.scalar.return_value = "POINT(0 0)"

    mock_hotspot_clock = MagicMock()
    mock_hotspot_clock.first.return_value = (datetime.utcnow(), datetime.utcnow() - timedelta(days=30))

    def execute_side_effect(stmt, params=None, *args, **kwargs):
        stmt_str = str(stmt)
        if "ST_ClusterDBSCAN" in stmt_str:
            return mock_cluster_result
        if "centroid c" in stmt_str:
            # Split-query: keep every report inside its own group (small
            # distance), so the merge step is what's under test here, not
            # the pre-existing split step.
            ids = params["report_ids"]
            result = MagicMock()
            result.fetchall.return_value = [MagicMock(id=i, distance=0.05) for i in ids]
            return result
        if "WITH a AS" in stmt_str:
            result = MagicMock()
            result.scalar.return_value = merge_distance
            return result
        if "ST_Centroid" in stmt_str:
            return mock_centroid
        if "MIN(reported_at)" in stmt_str:
            return mock_hotspot_clock
        return MagicMock()

    db.execute.side_effect = execute_side_effect

    report1 = CitizenReport(id=1, sector="water",      region_id=1, urgency_score=5)
    report2 = CitizenReport(id=2, sector="water",      region_id=1, urgency_score=5)
    report3 = CitizenReport(id=3, sector="sanitation", region_id=2, urgency_score=5)
    report4 = CitizenReport(id=4, sector="sanitation", region_id=2, urgency_score=5)

    tail = (
        [[report1, report2, report3, report4]]       # merged: one final cluster
        if will_merge else
        [[report1, report2], [report3, report4]]     # not merged: two final clusters
    )

    citizen_report_query_mock = MagicMock()
    citizen_report_query_mock.filter.return_value.all.side_effect = [
        [],                                     # pending_reports
        [report1, report2, report3, report4],   # gazetteer_reports
        [report1, report2],                     # merge region-hint: cluster 0
        [report3, report4],                     # merge region-hint: cluster 1
        *tail,                                  # "Create Issue Clusters" loop
    ]

    region1 = MagicMock(id=1, parent_id=None,             population=1000.0, centroid=None)
    region2 = MagicMock(id=2, parent_id=region2_parent_id, population=1000.0, centroid=None)
    region_by_id = {1: region1, 2: region2}

    def query_side_effect(model):
        if model is CitizenReport:
            return citizen_report_query_mock
        q = MagicMock()
        if model is AdminRegion:
            q.get.side_effect = lambda rid: region_by_id.get(rid)
            q.filter.return_value.first.return_value = region1
        return q
    db.query.side_effect = query_side_effect

    db.added_objects = []
    def add_side_effect(obj):
        if isinstance(obj, AnalysisRun) and obj.id is None:
            obj.id = 99
        if obj not in db.added_objects:
            db.added_objects.append(obj)
    db.add.side_effect = add_side_effect

    return db


def _patch_gemini_and_verifier(monkeypatch):
    class MockGemini:
        def generate_policy_brief(self, data):
            return {"summary": "S", "why_prioritized": "W", "fiscal_gap_analysis": "F", "recommended_action": "R"}
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGemini())

    class MockVerifier:
        def verify_brief(self, text, bundle):
            return {"verified": True, "unverified_numbers": []}
    monkeypatch.setattr("app.services.clustering_engine.verification_engine", MockVerifier())


@pytest.fixture
def mock_db_for_merge(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.05, region2_parent_id=1, will_merge=True)
    _patch_gemini_and_verifier(monkeypatch)
    return db


@pytest.fixture
def mock_db_for_merge_too_distant(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.5, region2_parent_id=1, will_merge=False)
    _patch_gemini_and_verifier(monkeypatch)
    return db


@pytest.fixture
def mock_db_for_merge_unrelated_region(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.05, region2_parent_id=999, will_merge=False)
    _patch_gemini_and_verifier(monkeypatch)
    return db


def test_cross_bucket_merge_joins_related_regions_within_threshold(mock_db_for_merge):
    clustering_engine.process_and_prioritize(mock_db_for_merge)

    clusters = [obj for obj in mock_db_for_merge.added_objects if isinstance(obj, IssueCluster)]

    # Two gazetteer buckets -- (region 1, water) and (region 2, sanitation)
    # -- start out separate. Region 2 is a child of region 1, and their
    # embeddings are near-identical (0.05, under the 0.15 merge threshold),
    # so they should end up as ONE cluster covering all 4 reports.
    assert len(clusters) == 1
    assert clusters[0].report_count == 4


def test_cross_bucket_merge_skips_when_distance_exceeds_threshold(mock_db_for_merge_too_distant):
    clustering_engine.process_and_prioritize(mock_db_for_merge_too_distant)

    clusters = [obj for obj in mock_db_for_merge_too_distant.added_objects if isinstance(obj, IssueCluster)]

    # Same related regions as the merge case, but the embeddings are 0.5
    # apart -- well over the threshold. Must stay two separate clusters.
    assert len(clusters) == 2
    assert sorted(c.report_count for c in clusters) == [2, 2]


def test_cross_bucket_merge_skips_when_regions_unrelated(mock_db_for_merge_unrelated_region):
    clustering_engine.process_and_prioritize(mock_db_for_merge_unrelated_region)

    clusters = [obj for obj in mock_db_for_merge_unrelated_region.added_objects if isinstance(obj, IssueCluster)]

    # Same near-identical embeddings as the merge case, but region 2's
    # parent is 999, not region 1 -- geographically unrelated. Must NOT
    # merge just because the text reads similarly; two clusters expected.
    assert len(clusters) == 2
    assert sorted(c.report_count for c in clusters) == [2, 2]


def _report_at(days_ago: float) -> MagicMock:
    return MagicMock(reported_at=datetime.utcnow() - timedelta(days=days_ago))


def test_is_emerging_hotspot_true_when_recent_rate_accelerates():
    # 3 reports in the last 7 days, 1 report 7-14 days ago -> ratio 3.0, >= 2.0.
    reports = [_report_at(1), _report_at(2), _report_at(3), _report_at(9)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=30)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is True


def test_is_emerging_hotspot_false_when_below_minimum_recent_count():
    # Only 2 recent reports -- below the minimum of 3, regardless of ratio.
    reports = [_report_at(1), _report_at(2)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=30)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is False


def test_is_emerging_hotspot_false_when_rate_not_accelerating():
    # 3 recent, 3 prior -> ratio 1.0, below the 2.0 threshold.
    reports = [_report_at(1), _report_at(2), _report_at(3), _report_at(8), _report_at(9), _report_at(10)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=30)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is False


def test_is_emerging_hotspot_true_when_all_new_with_no_prior_activity():
    # 3 recent, 0 prior -- brand-new activity is itself the strongest signal
    # (and avoids a division by zero) -- but only because the dataset has
    # history predating the window, so "0 prior" is a real signal and not
    # just "no data yet."
    reports = [_report_at(1), _report_at(2), _report_at(3)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=30)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is True


def test_is_emerging_hotspot_false_when_dataset_has_no_history_yet():
    # Same reports as the all-new test (3 recent, 0 prior), but the dataset
    # itself has no history older than the window -- a fresh deployment or
    # newly imported region, not a genuine emerging hotspot.
    reports = [_report_at(1), _report_at(2), _report_at(3)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=2)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is False


def test_is_emerging_hotspot_false_when_reports_missing_timestamp():
    reports = [MagicMock(reported_at=None), MagicMock(reported_at=None), MagicMock(reported_at=None)]
    now = datetime.utcnow()
    oldest_report_at = now - timedelta(days=30)
    assert _is_emerging_hotspot(reports, now, oldest_report_at) is False


def test_priority_details_include_emerging_hotspot_flag(mock_db_for_split):
    clustering_engine.process_and_prioritize(mock_db_for_split)

    priorities = [obj for obj in mock_db_for_split.added_objects if isinstance(obj, Priority)]

    # Every cluster in this fixture has fewer than HOTSPOT_MIN_RECENT_REPORTS
    # (3) recent reports -- the split produces one cluster of 2 reports and
    # one of 1 -- even though report1/2/3 all carry a recent reported_at.
    # This exercises the real is_emerging_hotspot computation (not just key
    # presence): if the flag were hardcoded True, or the recent-count gate
    # were broken, this assertion would catch it.
    assert priorities
    for p in priorities:
        assert "is_emerging_hotspot" in p.details
        assert p.details["is_emerging_hotspot"] is False
