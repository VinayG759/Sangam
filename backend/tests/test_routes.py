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
