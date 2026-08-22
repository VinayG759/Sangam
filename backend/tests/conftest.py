"""
Shared pytest fixtures and configuration for Sangam backend tests.

Uses a temporary YAML pack file and mocked Gemini service to
ensure tests run without external dependencies.
"""

import os
import sys
import pytest
import tempfile
import shutil
import yaml

# Ensure the backend directory is on the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_pack_dir(tmp_path):
    """
    Create a temporary pack directory with a valid pack.yaml.
    Returns the path to the pack directory.
    """
    pack_name = "test_pack"
    pack_dir = tmp_path / pack_name
    pack_dir.mkdir()

    pack_data = {
        "country_code": "TST",
        "region_name": "TestRegion",
        "languages": [
            {"code": "en", "name": "English", "is_default": True},
            {"code": "kn", "name": "Kannada", "is_default": False},
        ],
        "sectors": [
            {"key": "water", "name": "Water Supply"},
            {"key": "roads", "name": "Road Repairs"},
            {"key": "sanitation", "name": "Waste Management"},
        ],
        "weights": {
            "demand_density": 0.35,
            "vulnerability_index": 0.35,
            "expenditure_gap": 0.20,
            "urgency": 0.10,
        },
    }

    with open(pack_dir / "pack.yaml", "w", encoding="utf-8") as f:
        yaml.dump(pack_data, f)

    return tmp_path, pack_name


@pytest.fixture
def sample_evidence_bundle():
    """Return a realistic evidence bundle for testing the verifier and Gemini service."""
    return {
        "cluster_id": 1,
        "title": "Cluster of 5 water reports",
        "sector": "water",
        "report_count": 5,
        "average_urgency": 4.2,
        "vulnerability_index": 0.45,
        "allocated_budget": 2500000.0,
        "estimated_cost": 7500000.0,
        "budget_stalled": False,
        "expenditure_records": [
            {"title": "Borewell Water Treatment", "amount": 2500000.0, "status": "completed"}
        ],
        "citizen_quotes": [
            "There is no drinking water in our area for the last 10 days.",
            "Pipeline leak causing zero water pressure.",
            "Please fix the borewell pump, it has been broken for weeks."
        ]
    }


@pytest.fixture
def sample_priorities():
    """Return a list of priority dicts for simulation testing."""
    return [
        {
            "cluster_id": 1,
            "title": "Water Crisis - Ward A",
            "sector": "water",
            "score": 85.0,
            "reports_count": 10,
            "vulnerability": 0.7,
            "allocated_budget": 500000.0,
            "estimated_cost": 3000000.0,
        },
        {
            "cluster_id": 2,
            "title": "Pothole Cluster - Ward B",
            "sector": "roads",
            "score": 72.0,
            "reports_count": 25,
            "vulnerability": 0.3,
            "allocated_budget": 1000000.0,
            "estimated_cost": 4000000.0,
        },
        {
            "cluster_id": 3,
            "title": "Sanitation Issues - Ward C",
            "sector": "sanitation",
            "score": 60.0,
            "reports_count": 5,
            "vulnerability": 0.5,
            "allocated_budget": 0.0,
            "estimated_cost": 1500000.0,
        },
    ]
