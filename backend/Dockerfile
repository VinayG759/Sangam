# ─────────────────────────────────────────────────────────────────────────────
# Sangam Backend — Multi-stage Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Install dependencies (cached layer)
# Stage 2: Production image with non-root user
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System dependencies for compiling Python extensions (psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /workspace

# Runtime-only system dependency (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN groupadd --gid 1000 sangam && \
    useradd --uid 1000 --gid sangam --shell /bin/bash --create-home sangam

# Copy application code
COPY . .

# Copy entrypoint script and make executable
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set ownership to non-root user
RUN chown -R sangam:sangam /workspace

USER sangam

EXPOSE 8000

# Health check — ensures the container is actually serving
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
