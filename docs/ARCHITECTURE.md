# Sangam — System Design

**Full system design document:**
https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db

**Implementation Plan:**
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)


Published 16 Aug 2026 · v1.0 · private artifact (share from the page's share menu)

---

## What Sangam is

An open-source Digital Public Good that turns multilingual citizen voice into
evidence-backed infrastructure investment priorities — designed to run in any
country, not just one.

Built for the Google Cloud "Build with AI: Code for Communities" hackathon,
Track 1 — AI for Digital Public Infrastructure & Governance (BRICS / Innovation).

**The core claim — "the join":** citizen feedback and public expenditure records
live in separate systems and are never put side by side. Sangam joins them, which
surfaces two findings no complaint tracker can produce:

- **Unserved gap** — real demand, no money allocated
- **Stalled allocation** — money already sanctioned, citizens still reporting the problem

## Contents of the design document

| § | Section |
|---|---------|
| 1 | Requirements — functional & non-functional |
| 2 | Scale & workload shape |
| 3 | Architecture — three latency zones |
| 4 | Components & contracts |
| 5 | Data model — 8 tables |
| 6 | API surface |
| 7 | The AI pipeline — 3 Gemini calls |
| 8 | Algorithms — scoring, verdicts, budget simulation |
| 9 | Country packs |
| 10 | Privacy & abuse resistance |
| 11 | Failure modes |
| 12 | Deployment topology |
| 13 | Scaling path |
| 14 | Repository tree |
| 15 | Build sequence |
| 16 | Risk register |

## Load-bearing decisions

1. **`indicators` is tall, not wide** — adding a country ships rows, not migrations.
2. **Weights live in `pack.yaml`, not in code** — the engine computes, the ministry
   sets the political trade-off between equity and reach.
3. **Scoring is model-free** — Gemini writes the explanation, never decides the order.
4. **Generated numbers are programmatically verified** against a closed evidence
   bundle; unverifiable output is rejected, not trusted.
5. **No model call on the dashboard read path** — free-tier rate limits cannot
   break a live demo.

## Key dates

- **16 Aug 2026** — build starts (day 1)
- **23 Aug 2026** — target submission
- **24 Aug 2026** — deadline (buffer only, nothing planned)
- **29 Aug 2026** — virtual finale, top 20
- **4 Sep 2026** — in-person Demo Day

## Stack

Python / FastAPI · Supabase (Postgres + pgvector + PostGIS) · Gemini API
(free tier, AI Studio) · React + Leaflet · Render + Vercel · Apache-2.0

> Keep this file pointing at the current version of the design. If the
> architecture changes, update the artifact rather than letting it rot.
