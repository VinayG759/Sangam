# Sangam — Deployment Guide

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for database)
- [Gemini API key](https://aistudio.google.com/apikey) (free tier is sufficient)

### Option A: Docker Compose (Recommended)

Starts both the PostgreSQL database and the backend API:

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/sangam.git
cd sangam

# 2. Create environment file
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 3. Start everything (first run with demo data)
SEED_DB=true docker compose up --build

# 4. Access the API
#    API:     http://localhost:8000
#    Swagger: http://localhost:8000/docs
#    Health:  http://localhost:8000/health
```

Subsequent runs (data persists in the `pgdata` volume):
```bash
docker compose up --build
```

To reset the database:
```bash
docker compose down -v   # removes the pgdata volume
SEED_DB=true docker compose up --build
```

### Option B: Local Python + Docker DB

Use Docker only for the database, run the backend natively:

```bash
# 1. Start only the database
docker compose up db -d

# 2. Set up the backend
cd backend
cp .env.example .env
# Edit .env — DATABASE_URL should point to localhost:5432

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize the database
python -m app.utils.db_init

# 5. (Optional) Seed demo data
python -m app.utils.db_seed

# 6. Start the API server
uvicorn app.main:app --reload --port 8000
```

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

Tests mock the database, so no PostgreSQL is needed.

---

## Production Deployment

### Backend → Render.com

1. Create a **Web Service** on [Render](https://render.com/)
2. Connect to the GitHub repo
3. Set:
   - **Root directory**: `backend`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | Your Supabase connection string |
   | `GEMINI_API_KEY` | Your Gemini API key |
   | `ACTIVE_COUNTRY_PACK` | `india_karnataka` |
   | `PACKS_DIR` | `packs` |
   | `ENV` | `production` |

### Database → Supabase

1. Create a project on [Supabase](https://supabase.com/)
2. The image ships with PostGIS and pgvector pre-installed
3. Copy the **Connection string** (URI format) → set as `DATABASE_URL`
4. Run `python -m app.utils.db_init` once to create tables
5. Run `python -m app.utils.db_seed` to load demo data

### Frontend → Vercel

1. Connect the repo to [Vercel](https://vercel.com/)
2. Set **Root directory**: `frontend`
3. Set the backend API URL as an environment variable

### Keepalive

After deploying, set the `SANGAM_API_URL` secret in GitHub Actions:
- Go to **Settings → Secrets and variables → Actions**
- Add `SANGAM_API_URL` = `https://your-backend.onrender.com`

The `keepalive.yml` workflow pings the API twice daily to prevent:
- Supabase free-tier project pause (7 days idle)
- Render free-tier spindown (15 minutes idle)

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql://postgres:postgres@localhost:5432/sangam` | PostgreSQL connection string |
| `ASYNC_DATABASE_URL` | No | Auto-derived from `DATABASE_URL` | Async driver URL (asyncpg) |
| `GEMINI_API_KEY` | Yes* | `None` | Google AI Studio API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Text generation model |
| `GEMINI_EMBEDDING_MODEL` | No | `text-embedding-004` | Embedding model (768d) |
| `ACTIVE_COUNTRY_PACK` | No | `india_karnataka` | Active pack name |
| `PACKS_DIR` | No | `packs` | Path to pack configs directory |
| `ENV` | No | `development` | `development` or `production` |
| `SEED_DB` | No | `false` | Set `true` for Docker auto-seed |

\* The app starts without `GEMINI_API_KEY` but AI features return fallback values.

---

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Frontend   │────▶│  Backend (API)   │────▶│   PostgreSQL     │
│  React/Vite  │     │  FastAPI/Python  │     │  PostGIS+pgvector│
│   Vercel     │     │    Render        │     │    Supabase      │
└──────────────┘     └───────┬──────────┘     └──────────────────┘
                             │
                     ┌───────▼──────────┐
                     │  Gemini API      │
                     │  (AI Studio)     │
                     └──────────────────┘
```
