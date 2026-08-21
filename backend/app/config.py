import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Sangam"
    ENV: str = "development"
    
    # Supabase / PostgreSQL database URLs
    # SQLAlchemy requires sync driver (psycopg2) for migrations, and async driver (asyncpg) for async fastapi queries
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sangam"
    ASYNC_DATABASE_URL: Optional[str] = None
    
    # Gemini AI configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    
    # Country Pack Directory & Selection
    PACKS_DIR: str = "packs"
    ACTIVE_COUNTRY_PACK: str = "india_karnataka"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __init__(self, **values):
        super().__init__(**values)
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
