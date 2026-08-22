# Sangam

Sangam is a multilingual, evidence-backed infrastructure prioritization platform. It bridges the gap between citizen needs and government expenditure by using AI to analyze citizen reports, identify infrastructure gaps, and simulate budget allocations.

## Key Features
- **Multilingual Support**: Ingest citizen reports in multiple local languages and translate them to English using AI.
- **Evidence-Backed Prioritization**: Cross-references citizen reports with historical government expenditure data to prioritize unserved gaps or stalled allocations.
- **Interactive Dashboard**: A modern React/Vite dashboard providing real-time intelligence with metric cards, sector breakdowns, and an interactive cluster map.
- **Budget Simulator**: Model the impact of various allocation strategies (Equity First, Max Reach, Highest Score) on infrastructure gaps given a specific budget.

## Architecture
- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL with PostGIS (for spatial clustering) and pgvector (for semantic search)
- **Frontend**: React + Vite + Recharts + Leaflet
- **AI**: Google Gemini API (for semantic embeddings and narrative brief generation)

## Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- [Google Gemini API Key](https://aistudio.google.com/apikey)

### Start the Application
1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/sangam.git
   cd sangam
   ```
2. Create and configure your environment variables:
   ```bash
   cp .env.example .env
   # Add your GEMINI_API_KEY to the .env file
   ```
3. Start the services with demo data seeded:
   ```bash
   SEED_DB=true docker compose up --build
   ```
4. Access the applications:
   - **Frontend Dashboard**: [http://localhost:5173](http://localhost:5173) (Run `npm run dev` in the `frontend` directory)
   - **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

For more deployment options (local native, Render, Vercel, Supabase), see our detailed [Deployment Guide](DEPLOY.md).

## Project Structure
- `backend/`: FastAPI application, core services (clustering, simulation, scoring, verifier), and database models.
- `frontend/`: React dashboard application.
- `packs/`: Configuration packs for specific countries/regions defining sectors, languages, and prioritization weights.

## Testing
Run backend unit and integration tests (uses SQLite for tests):
```bash
cd backend
python -m pytest tests/ -v
```

## License
MIT License
