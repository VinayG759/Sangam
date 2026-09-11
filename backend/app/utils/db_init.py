import logging
from sqlalchemy import text
from app.db import engine, Base
# Import models to ensure they are registered with Base metadata
from app.models.models import AdminRegion, CitizenReport, Expenditure, Indicator, IssueCluster, Priority, EvidenceBundle, NarrativeBrief

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    logger.info("Initializing database...")
    try:
        with engine.connect() as conn:
            # Enable PostGIS and pgvector extensions
            logger.info("Enabling PostGIS and pgvector extensions...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            logger.info("Extensions enabled successfully.")
        
        # Create all tables
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")

        # This project has no migration framework. create_all() above only
        # creates tables that don't exist yet -- it never alters an existing
        # table's columns. citizen_reports already holds real production
        # data, so a new column added to the model (Phase 20's
        # flagged_coordinated) would otherwise never actually reach the real
        # database: every subsequent INSERT would fail with "column ...
        # does not exist" the moment this code deployed. Idempotent and
        # safe to run on every startup, including a fresh database where
        # create_all() already created the column correctly.
        logger.info("Ensuring columns added after initial table creation exist...")
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE citizen_reports "
                "ADD COLUMN IF NOT EXISTS flagged_coordinated boolean NOT NULL DEFAULT false;"
            ))
            conn.commit()
        logger.info("Column check complete.")

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    init_db()
