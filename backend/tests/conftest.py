"""
Tests run against a real Postgres database (never SQLite, never a mock),
migrated with Alembic exactly as production is. Only Gemini is faked.

Database: TEST_DATABASE_URL, or the configured DATABASE_URL with the
database name replaced by sangam_test. It is wiped between tests.
"""

import hashlib
import os
from pathlib import Path

HERE = Path(__file__).parent


def _test_database_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    from app.core.config import Settings

    base = Settings().DATABASE_URL.rsplit("/", 1)[0]
    return f"{base}/sangam_test"


# Must happen before anything imports app settings.
os.environ.update({
    "DATABASE_URL": _test_database_url(),
    "ACTIVE_COUNTRY_PACK": "testland",
    "PACKS_DIR": str(HERE / "fixtures" / "packs"),
    "ADMIN_TOKEN": "test-admin-token",
    "TELEGRAM_WEBHOOK_SECRET": "test-telegram-secret",
    "TELEGRAM_BOT_TOKEN": "test-bot-token",
    "WHATSAPP_APP_SECRET": "test-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
    "REPORTER_HASH_PEPPER": "test-pepper",
    "ALLOWED_ORIGINS": "http://localhost:5173",
    "GEMINI_API_KEY": "",
    "SARVAM_API_KEY": "",  # never call the real speech service from tests
    # Fixed test-only key so encrypted contacts can be exercised.
    "CONTACT_ENCRYPTION_KEY": "q9bYk0Qm2p8m9cRcS6o5Qx1k3Yv6wL0tJm4uZ7aB2cE=",
    "PUBLIC_APP_URL": "https://sangam.example",
    # Fixed test-only brief signing key (bytes 0..31).
    "BRIEF_SIGNING_KEY": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.ai import AIUnavailable, Summary, Understanding  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine, new_session  # noqa: E402
from app.core.pack import get_pack  # noqa: E402

TABLES = ["priorities", "clusters", "analysis_runs", "contacts", "conversations", "report_media", "reports",
          "projects", "indicators", "regions"]


class FakeAI:
    """Deterministic stand-in for Gemini. Tests set .down, .places, .sector or .summary_text."""

    def __init__(self):
        self.down = False
        self.sector = "water"
        self.places: list[str] = []
        self.language = "en"
        self.actionable = True
        self.summary_text = "Summary."
        self.summary_calls = 0

    def understand(self, pack, text, media, mime_type):
        if self.down:
            raise AIUnavailable("fake outage")
        return Understanding(language=self.language, transcript=text or "[voice note]",
                             text_en=(text or "voice note") + " (en)", sector=self.sector, urgency=3,
                             place_names=list(self.places), is_actionable=self.actionable)

    def embed(self, text):
        if self.down:
            raise AIUnavailable("fake outage")
        digest = hashlib.sha256(text.encode()).digest()
        return [((digest[i % 32] + i) % 17 + 1) / 17 for i in range(768)]

    def write_summary(self, facts, context):
        self.summary_calls += 1
        if self.down:
            raise AIUnavailable("fake outage")
        return Summary(summary=self.summary_text, cited_fact_ids=[])


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    get_settings.cache_clear()
    get_pack.cache_clear()
    config = Config(str(HERE.parent / "alembic.ini"))
    config.set_main_option("script_location", str(HERE.parent / "migrations"))
    command.upgrade(config, "head")
    yield config


@pytest.fixture(autouse=True)
def clean_database():
    from app.core.limiter import limiter

    limiter.reset()  # each test starts with fresh rate-limit counters
    yield
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def pack():
    return get_pack()


@pytest.fixture
def loaded(pack):
    """Testland's regions, indicators and project, loaded into the database."""
    from app.features.packs.load import load_pack_into_db

    with new_session() as db:
        load_pack_into_db(db, "testland")
    return pack


@pytest.fixture
def db():
    with new_session() as session:
        yield session


@pytest.fixture
def ai():
    return FakeAI()


@pytest.fixture
def client(ai):
    from app.core.ai import get_ai
    from app.main import app

    app.dependency_overrides[get_ai] = lambda: ai
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


ADMIN = {"Authorization": "Bearer test-admin-token"}
