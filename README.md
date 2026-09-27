# Sangam

**Citizen voice, joined with public data, to show where infrastructure money is missing — or not reaching people.**

Sangam is an open-source Digital Public Good. Citizens report local problems (water, roads, electricity,
health, schools, sanitation) by voice, photo or text, in their own language, over WhatsApp, Telegram or
the web. Sangam groups those reports by place and need, then puts them **side by side with official
statistics and public spending** — the join that complaint systems never make.

| Verdict | What the join shows | Recommended action |
|---|---|---|
| **Unserved gap** | Many residents report the problem; official data says the place is not served | Fund |
| **Delivery gap** | Official data says the place *is* served; many residents say otherwise | Audit |
| **Stalled allocation** | Money is committed here; residents still report the problem | Audit |
| **Demand hotspot** | Many residents report the problem; no official data loaded yet to compare | Verify |
| **Monitor** | Demand close to the typical place | Monitor |

**Impact:** for every place, official programme progress (e.g. Jal Jeevan Mission tap coverage,
2019 → 2026) is set beside what residents report today — showing where investment is not reaching
people. Once completed-project data is loaded, complaints before and after each project are compared too.

> *Grievance systems route complaints. Sangam audits priorities.*

## Why you can trust the ranking

- **The AI never decides the order.** Ranking is plain arithmetic with weights the government sets in
  the country pack. Every score shows its working.
- **Every AI-written number is checked by code.** Gemini writes a short explanation from a closed list of
  sourced facts; if it writes any number that is not in those facts, the explanation is rejected.
- **Every figure links to its source.**
- **Reporters are protected.** A reporter's identity is stored only as a keyed hash; personal details
  are removed before storage; groups of fewer than 5 people are never shown. To tell a citizen when
  their report reaches the priority list, their chat ID is kept **encrypted**, used for that one
  message, then deleted — or deleted unsent after 180 days. Without an encryption key configured,
  nothing that can reach a citizen is stored at all.
- **Degrade, never fail.** If Gemini is unavailable, citizens still get a tracking ID and their report is
  processed later.

## Data honesty

The citizen messages in the live demo are **synthetic**, generated to mirror plausible patterns and
marked as such everywhere they appear. Everything else — the places, the number of rural households and
the share with a tap connection — is **real government data** (Local Government Directory and Jal Jeevan
Mission, Karnataka), and every number links to its source. Sangam does not invent spending: where no
spending data is loaded, it says so.

## Built for any country (BRICS)

A country is a folder under [`backend/packs/`](backend/packs): a `pack.yaml` (languages, needs, weights,
thresholds, which statistic measures which need) and three CSVs (places, statistics, sanctioned
projects). The engine code contains no country-specific words — a test enforces it. India (Karnataka) is
live on real data; `packs/brazil/` is the next pack. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Run it locally

**Requirements:** Python 3.11, Node 20+, and Postgres with the `pgvector` extension (or Docker).

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # set DATABASE_URL; GEMINI_API_KEY is optional
alembic upgrade head                                # create the schema
python -m app.features.packs load india             # load real Karnataka data
python -m scripts.seed_demo                         # optional: ~4,700 synthetic demo reports
uvicorn app.main:app --reload                       # http://localhost:8000/docs

# Start an analysis run (use the ADMIN_TOKEN from .env)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/admin/runs

# Frontend
cd frontend
npm install
npm run dev                                         # http://localhost:5173
```

Or with Docker: `docker compose up --build` (starts Postgres + API with demo data).

## Tests

```bash
cd backend && python -m pytest       # 82 tests against a real Postgres database (sangam_test)
cd frontend && npm test              # unit tests
python -m scripts.smoke_test <API>   # 10-second check of a live deployment
```

## Project layout

```
backend/app/core/        shared plumbing: settings, database, country pack, Gemini, security
backend/app/features/    one folder per feature; features never import each other
backend/app/models.py    the tables — the contracts between features
backend/migrations/      Alembic schema migrations
backend/packs/           country packs (data, not code)
frontend/src/routes.tsx  every page and its address
frontend/src/features/   one folder per page
docs/                    the implementation plan (technical and plain-language)
```

## Documentation

- [Implementation plan](docs/implementation-plan.md) · [plain-language version](docs/implementation-plan-simple.md)
- [Deployment guide](DEPLOY.md)
- [Adding a country](CONTRIBUTING.md)

## Licence

[Apache-2.0](LICENSE)
