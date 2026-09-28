"""All settings, read once from environment variables (or backend/.env locally)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    ENV: str = "development"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sangam_v2"

    # Which country pack this deployment serves, and where packs live.
    ACTIVE_COUNTRY_PACK: str = "india"
    PACKS_DIR: Path = BACKEND_DIR / "packs"

    # Browser origins allowed to call the API (comma-separated).
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Admin endpoints require "Authorization: Bearer <ADMIN_TOKEN>". Empty = admin disabled.
    ADMIN_TOKEN: str = ""

    # HMAC key for hashing reporter IDs. Must be set in production.
    REPORTER_HASH_PEPPER: str = "local-development-pepper"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIM: int = 768

    TELEGRAM_BOT_TOKEN: str = ""
    # Telegram sends this in X-Telegram-Bot-Api-Secret-Token. Empty = reject every update.
    TELEGRAM_WEBHOOK_SECRET: str = ""

    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    # Meta-approved template for status updates sent after the 24-hour window. Empty = no WhatsApp updates.
    # The template body must take two parameters: {{1}} tracking ID, {{2}} the update sentence.
    WHATSAPP_NOTIFY_TEMPLATE: str = ""
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en"

    # Key for encrypting citizens' chat IDs (so they can be told when their report is prioritised).
    # Empty = contact storage off: no chat ID is ever kept.
    CONTACT_ENCRYPTION_KEY: str = ""

    # Ed25519 private key (base64, 32 bytes) that signs exported briefs. Empty = briefs are unsigned.
    # See app/core/signing.py. Its public key is published in docs/brief-signing-key.pub.
    BRIEF_SIGNING_KEY: str = ""

    # Public address of the dashboard, used in links sent to citizens (e.g. https://sangam.vercel.app).
    PUBLIC_APP_URL: str = ""

    # Kill switches (see docs/implementation-plan.md §5.3).
    FEATURE_TELEGRAM: bool = True
    FEATURE_WHATSAPP: bool = True
    FEATURE_WEB_INTAKE: bool = True
    FEATURE_SIMULATOR: bool = True
    FEATURE_EXPORT: bool = True
    FEATURE_IMPACT: bool = True
    FEATURE_NOTIFY: bool = True

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise any postgres URL to the psycopg 3 driver SQLAlchemy expects."""
        url = self.DATABASE_URL.strip()
        for prefix in ("postgresql+psycopg2://", "postgresql+asyncpg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
