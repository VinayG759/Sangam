#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Sangam Backend — Docker Entrypoint Script
# ─────────────────────────────────────────────────────────────────────────────
# This script runs BEFORE uvicorn starts. It:
# 1. Waits for PostgreSQL to be ready
# 2. Initializes the database (creates tables + extensions)
# 3. Optionally seeds demo data (if SEED_DB=true)
# 4. Starts the application (exec's into CMD)
# ─────────────────────────────────────────────────────────────────────────────

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║         Sangam Backend — Starting            ║"
echo "╚══════════════════════════════════════════════╝"

# ── Step 1: Wait for database ──────────────────────────────────────────────
echo "[entrypoint] Waiting for database to be ready..."

MAX_RETRIES=30
RETRY_INTERVAL=2
RETRIES=0

while [ $RETRIES -lt $MAX_RETRIES ]; do
    if python -c "
from sqlalchemy import create_engine, text
import os, sys
url = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/sangam').strip()
try:
    engine = create_engine(url, connect_args={'connect_timeout': 10})
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('OK')
except Exception as e:
    print(f'[entrypoint] DB connection error: {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
"; then
        echo "[entrypoint] Database is ready."
        break
    fi
    RETRIES=$((RETRIES + 1))
    echo "[entrypoint] Database not ready (attempt $RETRIES/$MAX_RETRIES). Retrying in ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

if [ $RETRIES -ge $MAX_RETRIES ]; then
    echo "[entrypoint] ERROR: Database did not become ready after $MAX_RETRIES attempts."
    exit 1
fi

# ── Step 2: Initialize database (extensions + tables) ──────────────────────
echo "[entrypoint] Initializing database (extensions + tables)..."
python -m app.utils.db_init || {
    echo "[entrypoint] WARNING: Database initialization failed (extensions may require superuser). Continuing..."
}

# ── Step 3: Optional data seeding ──────────────────────────────────────────
if [ "${SEED_DB}" = "true" ]; then
    echo "[entrypoint] SEED_DB=true — seeding demo data..."
    python -m app.utils.db_seed || {
        echo "[entrypoint] WARNING: Seeding failed. Continuing without seed data."
    }
else
    echo "[entrypoint] SEED_DB not set — skipping data seeding."
    echo "[entrypoint] Set SEED_DB=true in docker-compose to auto-seed on first run."
fi

# ── Step 3b: Optional real-data import (packs/india, government-sourced) ───
# Separate from SEED_DB on purpose: db_seed.py writes a hand-crafted demo
# scenario (fictional wards, matching citizen reports + expenditures, built
# to show every verdict clearly). This imports real Karnataka admin regions
# and Jal Jeevan Mission coverage indicators -- no citizen reports, no
# expenditures, because packs/india has none to import and inventing rupee
# figures to force a verdict is not something this script will do. Both can
# run together: real regions/indicators for the map and evidence drawer,
# synthetic demo regions for a verdict to actually show. See
# docs/DECISIONS.md #11 for how to describe the split honestly in the demo.
if [ "${LOAD_REAL_DATA}" = "true" ]; then
    echo "[entrypoint] LOAD_REAL_DATA=true — importing real Karnataka data from packs/india..."
    python -m app.utils.load_real_data || {
        echo "[entrypoint] WARNING: Real data import failed. Continuing without it."
    }
else
    echo "[entrypoint] LOAD_REAL_DATA not set — skipping real-data import."
    echo "[entrypoint] Set LOAD_REAL_DATA=true in docker-compose to import packs/india on start."
fi

echo "[entrypoint] Startup complete. Launching application..."
echo "─────────────────────────────────────────────────"

# ── Step 4: Execute the CMD (uvicorn) ──────────────────────────────────────
exec "$@"
