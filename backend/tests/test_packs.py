import shutil
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import BACKEND_DIR
from app.features.packs.load import load_pack_into_db
from app.features.packs.validate import validate_pack
from app.models import Indicator, Project, Region

FIXTURES = Path(__file__).parent / "fixtures" / "packs"


def test_real_india_pack_is_valid():
    assert validate_pack("india", BACKEND_DIR / "packs") == []


def test_brazil_stub_is_rejected_until_it_has_a_pack_yaml():
    problems = validate_pack("brazil", BACKEND_DIR / "packs")
    assert problems and "pack.yaml" in problems[0]


def test_testland_fixture_is_valid():
    assert validate_pack("testland", FIXTURES) == []


def _broken_copy(tmp_path, filename, old, new):
    target = tmp_path / "testland"
    shutil.copytree(FIXTURES / "testland", target)
    path = target / filename
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    return validate_pack("testland", tmp_path)


def test_unknown_parent_is_reported(tmp_path):
    problems = _broken_copy(tmp_path, "admin_units.csv", "Riverton,,TL-A-NORTH", "Riverton,,TL-A-NOWHERE")
    assert any("parent TL-A-NOWHERE not found" in p for p in problems)


def test_invented_project_status_is_reported(tmp_path):
    problems = _broken_copy(tmp_path, "sanctioned_projects.csv", "in_progress", "probably_stalled")
    assert any("status must be one of" in p for p in problems)


def test_number_without_source_is_reported(tmp_path):
    problems = _broken_copy(tmp_path, "indicators.csv", "90,percent,2026,Test statistics office",
                            "90,percent,2026,")
    assert any("needs a source_name" in p for p in problems)


def test_loading_twice_does_not_duplicate(db):
    first = load_pack_into_db(db, "testland")
    second = load_pack_into_db(db, "testland")
    assert first == second == {"regions": 12, "indicators": 30, "projects": 1}
    assert db.scalar(select(func.count()).select_from(Region)) == 12
    assert db.scalar(select(func.count()).select_from(Indicator)) == 30
    assert db.scalar(select(func.count()).select_from(Project)) == 1
    north = db.get(Region, "TL-A-NORTH")
    assert north.name_variants == ["Nordstadt", "North Field"] and north.lat == 12.0
    assert db.get(Region, "TL-A-NORTH-HILLVIEW").lat is None  # no centroid published
