"""Guards on the codebase's shape, so the plan's rules can't erode silently."""

import subprocess
import sys
from pathlib import Path

from alembic import command

BACKEND = Path(__file__).parents[1]


def test_migrations_match_the_models(migrated_database):
    """Fails if someone changes a model without writing a migration."""
    command.check(migrated_database)


def test_features_never_import_each_other():
    result = subprocess.run([sys.executable, "-m", "importlinter.cli", "--config", "setup.cfg"],
                            cwd=BACKEND, capture_output=True, text=True)
    if result.returncode != 0:
        result = subprocess.run(["lint-imports", "--config", "setup.cfg"], cwd=BACKEND, capture_output=True,
                                text=True, shell=sys.platform == "win32")
    assert result.returncode == 0, result.stdout + result.stderr


def test_engine_code_contains_no_country_specific_words():
    """A new country must be a folder, not a code change."""
    banned = ["Karnataka", "district", "taluk", "panchayat", "INR", "₹", "Jal Jeevan", "IN-KA"]
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.name}: {word}" for word in banned if word in text]
    assert offenders == []
