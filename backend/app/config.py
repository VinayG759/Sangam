import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Sangam"
    ENV: str = "development"
    
    # Supabase / PostgreSQL database URLs
    # SQLAlchemy requires sync driver (psycopg2) for migrations, and async driver (asyncpg) for async fastapi queries
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sangam"
    ASYNC_DATABASE_URL: Optional[str] = None
    
    # Gemini AI configuration.
    #
    # Model ids verified against the live API on 22 Aug 2026:
    #   - text-embedding-004 returns 404 NOT_FOUND. It no longer exists.
    #   - gemini-embedding-001 defaults to 3072 dimensions, but the
    #     citizen_reports.embedding column is Vector(768), so
    #     GEMINI_EMBEDDING_DIM must be passed explicitly on every call or
    #     inserts fail. Keep these two settings in step.
    #   - gemini-3.6-flash returns 503 "high demand" on the free tier;
    #     gemini-3.5-flash-lite answers the same schema-locked extraction in
    #     ~1.2s. Availability beats capability when a demo is live.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIM: int = 768

    # Country Pack Directory & Selection.
    # Resolved against the repository root, not the working directory: the app
    # runs from /app inside Docker and from backend/ under pytest, so a relative
    # "packs" path silently fails to resolve in both.
    PACKS_DIR: str = str(Path(__file__).resolve().parents[2] / "packs")
    ACTIVE_COUNTRY_PACK: str = "india_karnataka"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __init__(self, **values):
        super().__init__(**values)
        # Some PaaS env-var UIs (confirmed on Render) save a trailing
        # newline/whitespace when a value is pasted into a multi-line
        # textarea instead of trimming it. libpq then treats it as part of
        # the dbname itself -- e.g. "postgres\n" -- and fails with a
        # confusing "database does not exist" rather than any hint about
        # whitespace. Stripping here makes the app immune regardless of
        # what the hosting UI does with pasted values.
        self.DATABASE_URL = self.DATABASE_URL.strip()
        if self.ASYNC_DATABASE_URL:
            self.ASYNC_DATABASE_URL = self.ASYNC_DATABASE_URL.strip()
        # Automatically generate async database URL from sync URL if not explicitly provided
        if not self.ASYNC_DATABASE_URL and self.DATABASE_URL:
            # Replace postgresql:// with postgresql+asyncpg://
            if self.DATABASE_URL.startswith("postgresql://"):
                self.ASYNC_DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
            elif self.DATABASE_URL.startswith("postgres://"):
                self.ASYNC_DATABASE_URL = self.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")
            else:
                self.ASYNC_DATABASE_URL = self.DATABASE_URL

settings = Settings()
