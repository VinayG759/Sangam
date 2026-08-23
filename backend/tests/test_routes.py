"""
Integration tests for all Sangam API routes.

Uses FastAPI's TestClient with mocked database sessions to test:
- All route modules (overview, priorities, regions, reports, expenditures, clusters, pack)
- Response status codes and structure
- 404 handling for missing resources
- Query parameter filtering

These tests mock the database layer so they don't require a running PostgreSQL instance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ── Mock the database module BEFORE importing the app ────────────────────────
# The app imports db.py at module level, which tries to create engines
# connected to a real PostgreSQL. We need to intercept this.

# Patch the engines and session factories at the db module level
with patch("app.db.create_engine") as mock_engine, \
     patch("app.db.create_async_engine") as mock_async_engine:
    mock_engine.return_value = MagicMock()
    mock_async_engine.return_value = MagicMock()

    from app.main import app
    from app.db import get_db


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Create a TestClient with mocked database dependency."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_db_session():
    """
    Override the get_db dependency with a mock AsyncSession.
    All database queries return empty results by default.
    Individual tests can customize the mock behavior.
    """
    mock_session = AsyncMock()

    # Default: all execute() calls return a result with no rows
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.all.return_value = []
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.run_service.get_latest_complete_run_id_async", new_callable=AsyncMock) as m_get_run_id:
        m_get_run_id.return_value = 1
        yield mock_session
        
    app.dependency_overrides.clear()


# ── Root & Health ────────────────────────────────────────────────────────────

class TestRootEndpoints:

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Sangam" in data["message"]

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_pack" in data
        assert "app" in data


# ── Overview ─────────────────────────────────────────────────────────────────

class TestOverviewRoute:

    def test_overview_returns_200(self, client, mock_db_session):
        # Set up scalar returns for each query
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/overview")
        assert response.status_code == 200
        data = response.json()
        assert "total_citizen_reports" in data
        assert "sectors_breakdown" in data


# ── Pack ─────────────────────────────────────────────────────────────────────

class TestPackRoute:

    def test_pack_returns_200(self, client):
        response = client.get("/api/v1/pack")
        assert response.status_code == 200
        data = response.json()
        assert "country_code" in data
        assert "languages" in data
        assert "sectors" in data
        assert "weights" in data
        assert isinstance(data["languages"], list)
        assert isinstance(data["sectors"], list)

    def test_pack_has_weights(self, client):
        data = client.get("/api/v1/pack").json()
        weights = data["weights"]
        assert "demand_density" in weights
        assert "vulnerability_index" in weights
        assert "expenditure_gap" in weights
        assert "urgency" in weights


# ── Regions ──────────────────────────────────────────────────────────────────

class TestRegionsRoute:

    def test_list_regions_returns_200(self, client):
        response = client.get("/api/v1/regions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_regions_with_level_filter(self, client):
        response = client.get("/api/v1/regions?level=ward")
        assert response.status_code == 200

    def test_region_detail_404(self, client):
        response = client.get("/api/v1/regions/9999")
        assert response.status_code == 404

    def test_region_hierarchy_returns_200(self, client):
        response = client.get("/api/v1/regions/hierarchy/tree")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ── Reports ──────────────────────────────────────────────────────────────────

class TestReportsRoute:

    def test_list_reports_returns_200(self, client, mock_db_session):
        # Mock the count query and the list query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [mock_count_result, mock_list_result]

        response = client.get("/api/v1/reports")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "reports" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_reports_with_sector_filter(self, client, mock_db_session):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [mock_count_result, mock_list_result]

        response = client.get("/api/v1/reports?sector=water")
        assert response.status_code == 200

    def test_report_detail_404(self, client):
        response = client.get("/api/v1/reports/9999")
        assert response.status_code == 404


# ── Citizen Tracking Lookup ──────────────────────────────────────────────────

class TestCitizenTrackingRoute:

    def test_lookup_returns_200_without_specific_issue(self, client, mock_db_session):
        from datetime import datetime
        mock_report = MagicMock()
        mock_report.tracking_id = "SNG-AB12CD"
        mock_report.sector = "water"
        mock_report.specific_issue = "Pipe burst near market"
        mock_report.reported_at = datetime(2026, 8, 1)
        mock_report.channel = "telegram"
        mock_report.cluster_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_report
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/citizens/SNG-AB12CD")
        assert response.status_code == 200
        data = response.json()
        assert data["tracking_id"] == "SNG-AB12CD"
        assert data["sector"] == "water"
        assert data["status"] == "received"
        # Withheld deliberately: this route is unauthenticated, so free-text
        # issue content should never be reachable from a guessed tracking id.
        assert "specific_issue" not in data

    def test_lookup_404_for_unknown_tracking_id(self, client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/citizens/SNG-NOPE00")
        assert response.status_code == 404

    def test_lookup_is_rate_limited_per_ip(self, client, mock_db_session):
        from app.limiter import limiter
        limiter.reset()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        try:
            statuses = [client.get("/api/v1/citizens/SNG-NOPE00").status_code for _ in range(25)]
            assert 429 in statuses, "expected the 20/minute limit to trip within 25 requests"
        finally:
            limiter.reset()


# ── Expenditures ─────────────────────────────────────────────────────────────

class TestExpendituresRoute:

    def test_list_expenditures_returns_200(self, client, mock_db_session):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [mock_count_result, mock_list_result]

        response = client.get("/api/v1/expenditures")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "expenditures" in data

    def test_expenditures_summary_returns_200(self, client, mock_db_session):
        # Two queries: sector totals and status breakdown
        mock_result1 = MagicMock()
        mock_result1.all.return_value = []
        mock_result2 = MagicMock()
        mock_result2.all.return_value = []
        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        response = client.get("/api/v1/expenditures/summary")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_expenditure_detail_404(self, client):
        response = client.get("/api/v1/expenditures/9999")
        assert response.status_code == 404


# ── Clusters ─────────────────────────────────────────────────────────────────

class TestClustersRoute:

    def test_list_clusters_returns_200(self, client):
        response = client.get("/api/v1/clusters")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_cluster_detail_404(self, client):
        response = client.get("/api/v1/clusters/9999")
        assert response.status_code == 404


# ── Priorities ───────────────────────────────────────────────────────────────

class TestPrioritiesRoute:

    def test_list_priorities_returns_200(self, client):
        response = client.get("/api/v1/priorities")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_priority_detail_404(self, client):
        response = client.get("/api/v1/priorities/9999")
        assert response.status_code == 404

    def test_simulate_with_invalid_budget(self, client):
        """Simulation with negative budget should return 500 (ValueError from engine)."""
        response = client.post("/api/v1/simulate", json={
            "available_budget": -100,
            "strategy": "equity"
        })
        assert response.status_code == 500

    def test_simulate_returns_200(self, client):
        """Simulation with valid input (but no priorities in DB) should return 200."""
        response = client.post("/api/v1/simulate", json={
            "available_budget": 1000000,
            "strategy": "equity"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "equity"
        assert data["simulated_budget"] == 1000000


# ── OpenAPI Spec ─────────────────────────────────────────────────────────────

class TestOpenAPISpec:

    def test_openapi_spec_available(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert spec["info"]["title"] == "Sangam API"
        assert "/api/v1/overview" in spec["paths"]
        assert "/api/v1/priorities" in spec["paths"]
        assert "/api/v1/regions" in spec["paths"]
        assert "/api/v1/reports" in spec["paths"]
        assert "/api/v1/expenditures" in spec["paths"]
        assert "/api/v1/clusters" in spec["paths"]
        assert "/api/v1/pack" in spec["paths"]

    def test_docs_page_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200


# ── Aggregation Floor Enforcement ────────────────────────────────────────────

class TestAggregationFloorEnforcement:
    def test_suppressed_priority_hidden_from_all_endpoints(self, client, mock_db_session):
        from app.models.models import Priority, IssueCluster, AdminRegion
        
        # Setup suppressed priority and cluster
        cluster_suppressed = MagicMock(spec=IssueCluster)
        cluster_suppressed.id = 101
        cluster_suppressed.title = "Suppressed Issue"
        cluster_suppressed.sector = "water"
        cluster_suppressed.report_count = 2
        cluster_suppressed.region_id = 1
        cluster_suppressed.centroid = "POINT (75.7 15.3)"

        priority_suppressed = MagicMock(spec=Priority)
        priority_suppressed.id = 201
        priority_suppressed.cluster_id = 101
        priority_suppressed.cluster = cluster_suppressed
        priority_suppressed.score = 90
        priority_suppressed.verdict = "WELL_SERVED"
        priority_suppressed.details = {"suppressed": True, "distinct_reporters": 2}
        priority_suppressed.list = "audit"
        priority_suppressed.evidence_bundle = None

        # Setup normal priority and cluster
        cluster_normal = MagicMock(spec=IssueCluster)
        cluster_normal.id = 102
        cluster_normal.title = "Normal Issue"
        cluster_normal.sector = "roads"
        cluster_normal.report_count = 10
        cluster_normal.region_id = 1
        cluster_normal.centroid = "POINT (75.8 15.4)"

        priority_normal = MagicMock(spec=Priority)
        priority_normal.id = 202
        priority_normal.cluster_id = 102
        priority_normal.cluster = cluster_normal
        priority_normal.score = 80
        priority_normal.verdict = "UNSERVED_GAP"
        priority_normal.details = {"suppressed": False, "distinct_reporters": 10}
        priority_normal.list = "fund"
        priority_normal.evidence_bundle = None

        region = MagicMock(spec=AdminRegion)
        region.id = 1
        region.name = "Test Region"

        # Test 1: GET /api/v1/priorities
        mock_priorities_result = MagicMock()
        mock_priorities_result.scalars.return_value.all.return_value = [priority_suppressed, priority_normal]
        
        mock_region_result = MagicMock()
        mock_region_result.scalar_one_or_none.return_value = region
        
        mock_db_session.execute.side_effect = [
            mock_priorities_result, 
            mock_region_result  # For normal priority only! Suppressed is skipped!
        ]
        
        response = client.get("/api/v1/priorities")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 202
        
        # Test 2: GET /api/v1/priorities/201 (suppressed)
        mock_detail_suppressed = MagicMock()
        mock_detail_suppressed.scalar_one_or_none.return_value = priority_suppressed
        mock_db_session.execute.side_effect = [mock_detail_suppressed]
        
        response = client.get("/api/v1/priorities/201")
        assert response.status_code == 404
        
        # Test 3: GET /api/v1/priorities/202 (normal)
        mock_detail_normal = MagicMock()
        mock_detail_normal.scalar_one_or_none.return_value = priority_normal
        mock_db_session.execute.side_effect = [mock_detail_normal]
        
        response = client.get("/api/v1/priorities/202")
        assert response.status_code == 200
        assert response.json()["id"] == 202
        
        # Test 4: GET /api/v1/clusters
        # list_clusters selects (IssueCluster, ST_AsText(centroid)) tuples --
        # not select(IssueCluster) alone -- so ST_AsText can turn the
        # GeoAlchemy2 geometry into plain WKT text before it reaches
        # jsonable_encoder, which cannot serialize a raw WKBElement.
        mock_clusters_result = MagicMock()
        mock_clusters_result.all.return_value = [
            (cluster_suppressed, cluster_suppressed.centroid),
            (cluster_normal, cluster_normal.centroid),
        ]
        
        mock_region_name_result = MagicMock()
        mock_region_name_result.scalar.return_value = "Test Region"
        
        mock_priority_row_suppressed = MagicMock()
        mock_priority_row_suppressed.first.return_value = (201, 90, "WELL_SERVED", {"suppressed": True})
        
        mock_priority_row_normal = MagicMock()
        mock_priority_row_normal.first.return_value = (202, 80, "UNSERVED_GAP", {"suppressed": False})
        
        mock_db_session.execute.side_effect = [
            mock_clusters_result,
            mock_region_name_result,      # for suppressed cluster
            mock_priority_row_suppressed, # for suppressed cluster
            mock_region_name_result,      # for normal cluster
            mock_priority_row_normal      # for normal cluster
        ]
        
        response = client.get("/api/v1/clusters")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 102
        
        # Test 5: GET /api/v1/clusters/101 (suppressed)
        mock_cluster_detail = MagicMock()
        mock_cluster_detail.scalar_one_or_none.return_value = cluster_suppressed
        
        mock_reports_result = MagicMock()
        mock_reports_result.scalars.return_value.all.return_value = []
        
        mock_priority_detail = MagicMock()
        mock_priority_detail.scalar_one_or_none.return_value = priority_suppressed
        
        mock_db_session.execute.side_effect = [
            mock_cluster_detail,
            mock_region_result,
            mock_reports_result,
            mock_priority_detail
        ]
        
        response = client.get("/api/v1/clusters/101")
        assert response.status_code == 404
        
        # Test 6: GET /api/v1/clusters/102 (normal)
        mock_cluster_detail_normal = MagicMock()
        mock_cluster_detail_normal.scalar_one_or_none.return_value = cluster_normal
        
        mock_priority_detail_normal = MagicMock()
        mock_priority_detail_normal.scalar_one_or_none.return_value = priority_normal
        
        mock_db_session.execute.side_effect = [
            mock_cluster_detail_normal,
            mock_region_result,
            mock_reports_result,
            mock_priority_detail_normal
        ]
        
        response = client.get("/api/v1/clusters/102")
        assert response.status_code == 200
        assert response.json()["id"] == 102


# ── Ingestion ────────────────────────────────────────────────────────────────

class TestIngestionRoute:
    def test_ingest_citizen_web_route(self, client, mock_db_session, monkeypatch):
        from app.models.models import CitizenReport
        
        mock_db_session.add = MagicMock()
        # Ensure mock_db_session.commit returns None/completes immediately 
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        
        async def mock_flush(*args, **kwargs):
            for call in mock_db_session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                    obj.id = 1
        
        mock_db_session.flush = AsyncMock(side_effect=mock_flush)
        
        class MockGeminiService:
            def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
                return {
                    "original_language": "en",
                    "english_translation": text_content,
                    "sector": "roads",
                    "specific_issue": "pothole",
                    "urgency_score": 3.0,
                    "sentiment": "negative",
                    "pii_redacted_text": text_content
                }
                
            def get_embedding(self, text):
                return [0.1] * 768

        import app.services.ingestion_service as ingestion_module
        monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiService())
        
        # We also need to make sure the db.execute for sequence lookup or similar doesn't fail, 
        # though it shouldn't for the tracking ID generation if it's purely UUID or rand based, 
        # but tracking_id is generated locally in ingestion_service.py usually
        
        payload = {
            "text": "There is a massive pothole in front of the bakery.",
            "latitude": "15.3",
            "longitude": "75.7"
        }
        
        response = client.post("/api/v1/ingest/citizen", data=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "tracking_id" in data
        assert data["tracking_id"].startswith("SNG-")
        
        added_report = None
        for call in mock_db_session.add.call_args_list:
            if isinstance(call[0][0], CitizenReport):
                added_report = call[0][0]
                break
                
        assert added_report is not None
        assert added_report.channel == "web"
        assert added_report.reporter_hash is None


# ── Webhooks ─────────────────────────────────────────────────────────────────

class TestWhatsAppWebhookRoute:
    """
    Covers app/routes/webhooks.py's external-URL reconstruction: Twilio signs
    the public URL it actually called, but behind a reverse proxy or PaaS
    (Render, Railway, ...) that terminates TLS and forwards internally as
    plain HTTP, request.url reports the internal scheme/host -- a naive
    comparison would reject every real request. The route rebuilds the
    external URL from X-Forwarded-Proto/X-Forwarded-Host before verifying.
    """

    def _sign(self, url, params, auth_token):
        import hmac, hashlib, base64
        data = url
        for k, v in sorted(params.items()):
            data += f"{k}{v}"
        mac = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def test_valid_signature_behind_a_proxy_is_accepted(self, client, monkeypatch):
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

        form = {"From": "whatsapp:+1234567890", "Body": "Test", "NumMedia": "0"}
        # Twilio signed the *external* URL -- https on the real domain --
        # not the internal http://testserver TestClient uses.
        external_url = "https://sangam.example.com/api/v1/webhooks/whatsapp"
        signature = self._sign(external_url, form, "test_token")

        with patch("app.routes.webhooks.handle_whatsapp_update", new_callable=AsyncMock) as mock_handle:
            response = client.post(
                "/api/v1/webhooks/whatsapp",
                data=form,
                headers={
                    "X-Twilio-Signature": signature,
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "sangam.example.com",
                },
            )

        assert response.status_code == 200
        mock_handle.assert_called_once()

    def test_signature_signed_for_wrong_host_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

        form = {"From": "whatsapp:+1234567890", "Body": "Test", "NumMedia": "0"}
        # Signed for a different host than the one in the forwarded headers below.
        signature = self._sign("https://someone-elses-domain.com/api/v1/webhooks/whatsapp", form, "test_token")

        with patch("app.routes.webhooks.handle_whatsapp_update", new_callable=AsyncMock) as mock_handle:
            response = client.post(
                "/api/v1/webhooks/whatsapp",
                data=form,
                headers={
                    "X-Twilio-Signature": signature,
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "sangam.example.com",
                },
            )

        assert response.status_code == 403
        mock_handle.assert_not_called()

    def test_signature_computed_against_raw_internal_url_is_rejected(self, client, monkeypatch):
        # Proves the fix matters: a signature computed against the internal
        # http://testserver URL (what request.url would report with no
        # forwarded headers) must NOT validate once forwarded headers claim
        # a different external host -- otherwise the reconstruction could be
        # trivially bypassed by omitting the headers.
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token")

        form = {"From": "whatsapp:+1234567890", "Body": "Test", "NumMedia": "0"}
        signature = self._sign("http://testserver/api/v1/webhooks/whatsapp", form, "test_token")

        with patch("app.routes.webhooks.handle_whatsapp_update", new_callable=AsyncMock) as mock_handle:
            response = client.post(
                "/api/v1/webhooks/whatsapp",
                data=form,
                headers={
                    "X-Twilio-Signature": signature,
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "sangam.example.com",
                },
            )

        assert response.status_code == 403
        mock_handle.assert_not_called()
