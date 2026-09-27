#!/bin/sh
# Container start-up. Every step is safe to repeat on every deploy.
set -e

echo "[start] Applying database migrations..."
alembic upgrade head

echo "[start] Loading country pack '${ACTIVE_COUNTRY_PACK:-india}'..."
python -m app.features.packs load "${ACTIVE_COUNTRY_PACK:-india}"

if [ "${SEED_DEMO}" = "true" ]; then
    echo "[start] SEED_DEMO=true: replacing synthetic demo reports..."
    python -m scripts.seed_demo --reset
fi

# Trust the host's proxy (Render) for client IPs, which the per-IP rate limit uses.
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

echo "[start] Starting API on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
