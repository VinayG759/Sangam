# Sangam — Implementation Plan

**Version:** 2.2 · **Written:** 27 Sep 2026 · **Updated:** 27 Sep 2026 (full rewrite done; see §0.1) · **Owner:** Vinay G
**Replaces:** every earlier file in `docs/` (all recoverable from git history at commit `cf20571`).
**Plain-language companion:** [implementation-plan-simple.md](implementation-plan-simple.md) — same plan, same phase numbers, simpler words.
**Full system design (architecture, data model, algorithms):**
https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db

---

## Contents

0. [Open decisions that change this plan](#0-open-decisions-that-change-this-plan)
1. [What Sangam is](#1-what-sangam-is)
2. [Problem-statement coverage](#2-problem-statement-coverage)
3. [Principles that are not re-litigated](#3-principles-that-are-not-re-litigated)
4. [Baseline — what exists today](#4-baseline--what-exists-today)
5. [Engineering standards](#5-engineering-standards)
6. [Phase overview](#6-phase-overview)
7. [Phases in detail](#7-phases-in-detail) (Phases 0–8)
8. [Testing strategy](#8-testing-strategy)
9. [Debugging playbook](#9-debugging-playbook)
10. [Release and deployment process](#10-release-and-deployment-process)
11. [Risk register](#11-risk-register)
12. [Appendix A — Data sourcing rules](#appendix-a--data-sourcing-rules)
13. [Appendix B — Decision log](#appendix-b--decision-log)
14. [Appendix C — Glossary](#appendix-c--glossary)

---

## 0. Confirmed scope and sequencing

### 0.1 Status — 27 Sep 2026, after the rewrite

On 27 Sep Vinay chose to **rewrite the codebase now** rather than patch it. The rewrite is done,
tested and committed locally; **nothing is deployed yet**. What it delivered, mapped to this plan:

| Plan item | State |
|---|---|
| Phase 0 code fixes: Telegram secret (K3), CORS (K4), zero-embedding root cause (K5), admin fail-closed | **Done in code** — verified by tests and a local Docker run |
| Phase 0.7 smoke test | **Done** — `backend/scripts/smoke_test.py`, 9 checks, passes against the Docker image |
| Phase 1.1 repo hygiene: LICENSE, README, CONTRIBUTING, `engine/` removed | **Done** |
| Phase 1.2 demo dataset | **Done** — `scripts/seed_demo.py`, 4,704 synthetic reports placed against real JJM coverage |
| Phase 2 foundations: Alembic, feature folders, import-linter, router, per-page data + error boundaries, frontend CI, kill switches | **Done** |
| Phase 3 SaaS-grade UI | **Done** — checked in a real browser at desktop and phone width |
| Phase 7.2 media retention | **Done** — each analysis run deletes raw media older than the pack's limit |
| Phase 4 impact + close the loop | **Done** — `features/impact` (JJM 2019→2026 progress vs residents, real data now; before/after-project comparison, switches on when project data exists) and `features/notify` (encrypted chat IDs, one update, then deleted; 180-day expiry). WhatsApp updates need a Meta-approved template |
| Phase 5 national view | **Done** — region picker (`?region=`) scopes Overview and Priorities to a place and everything under it; `/rollup` ranks the places one level down by how many places inside need action; `/unlocated` counts unplaced reports **by reason only** (migration `0003`, `reports.location_failure`); new verdict `PLANNED_NOT_STARTED` (Audit group). Checked in a real browser: Overview → district → block → recommendation in three clicks |
| Phase 7 security and DPG | **Done in code** — signed briefs (7.1), retention already scheduled by the keepalive workflow (7.2), security review with two fixes (7.3), `docs/privacy.md` + `docs/do-no-harm.md` drafts (7.4). DPGA application is Vinay's to submit. See "As built" in §7 |
| Phase 1.5 description | **Draft corrected** — no longer claims spending records |
| Tests | 113 backend (real Postgres) + 8 frontend, all passing; `pip-audit` and `npm audit` report no known vulnerabilities; the Docker image last built and passed the smoke test before Phase 5 |

**Two corrections the rewrite forced — both about honesty:**

1. **There is no real spending data.** `packs/india/sanctioned_projects.csv` is empty; every
   spending line the old dashboard showed was invented by the old seed script. The rewrite never
   invents spending. The real join is citizen demand × **Jal Jeevan Mission tap-connection
   coverage** (real, sourced, 2019 and 2026): high demand where JJM reports ≥ 80% coverage is a
   `DELIVERY_GAP` — records say served, residents disagree. `STALLED_ALLOCATION` stays in the
   engine and will appear as soon as real project data is loaded (Phase 6 / data work).
2. **A need with no official statistic cannot be called "unserved".** New verdict
   `DEMAND_HOTSPOT` (verify on the ground). Only water has a statistic today, so roads, power,
   health, schools and sanitation show as hotspots.

**Still needed before submission — each needs Vinay:** a production database for the new schema
(decision D-22), Render + Vercel environment variables and a deploy (DEPLOY.md), registering the
Telegram webhook with its secret, a real-phone WhatsApp and Telegram test (K6), then Phase 1.3–1.5
(video, deck, description).

Both facts that decide this plan's order were confirmed by Vinay on **27 Sep 2026**:

| # | Question | Answer | Consequence |
|---|----------|--------|-------------|
| D1 | Submission deadline | **30 Sep 2026** — 3 days from this plan | Only **Phase 0 and Phase 1** happen before submission. Everything else is the plan for the shortlist and the October finale (New Delhi, date TBA). |
| D2 | Scope wording | **"across BRICS nations"** | The cross-country claim is load-bearing. Before submission it is carried **honestly by the pitch** (architecture + validator + "India live, Brazil next"). After submission, **Phase 6 (Brazil) is the first build priority.** |

**Why Brazil is not built before 30 Sep.** Phase 6 is mostly data research (real Brazilian
admin units, indicators and spending with sources) plus multi-pack serving code that
changes the schema. Doing that in 3 days *alongside* the video and deck would put the
whole submission at risk, and a half-real Brazil pack would contradict Appendix A's
"blank beats wrong" rule. A clear, true statement of what is live and what is next is
worth more to judges than a thin demo that breaks under a question.

**Order of work:**

```
BEFORE SUBMISSION (27–30 Sep)     Phase 0 → Phase 1 → submit
AFTER SUBMISSION (toward finale)  Phase 2  ∥  Phase 6.1 (Brazil data research, no code)
                                  → Phase 6.2–6.4 (validate, multi-pack serving, live switch)
                                  → Phase 4 → Phase 3 → Phase 5 → Phase 7
```

`∥` means in parallel: Phase 6.1 is research in `packs/brazil/` (the data teammate's
area) and never touches the code Phase 2 is reorganising, so the two cannot collide.
Phase 6's code steps wait for Phase 2 because they need migrations to be safe.
Phase 4 (impact) moves ahead of Phase 3 (UI) because it answers a part of the brief
that is otherwise unanswered; the UI polish is valuable but not a scoring gap.

**Before 30 Sep, check the exact submission cut-off time and time zone** on the
hackathon portal; the day-by-day schedule in §6 assumes end of day IST and keeps a
half-day buffer.

Judging weights (confirmed 25 Aug): AI/Technical Execution 25% · Problem-Solution Fit 20% ·
Depth & Reach 20% · Deployability & Scalability 20% · Impact Potential 15%.

Required submission package: public GitHub repo · 3–5 min demo video · 10–12 slide deck ·
2–3 line description · live deployed link.

---

## 1. What Sangam is

An open-source Digital Public Good that turns multilingual citizen voice into
evidence-backed infrastructure investment priorities, designed to run in any country
by adding a data folder rather than code.

**The core claim — "the join".** Citizen feedback and public expenditure records live
in separate systems and are never put side by side. Sangam joins them per
`(administrative region × need sector)` and produces verdicts no complaint tracker can:

| Verdict | Demand | Money | Action it implies |
|---------|--------|-------|-------------------|
| `UNSERVED_GAP` | High | None allocated | Recommend for allocation |
| `STALLED_ALLOCATION` | High | Allocated, not delivered | Send for delivery audit |
| `UNDERFUNDED_CRITICAL` | High | Allocated, too little | Top up |
| `DELIVERY_GAP` | High | Delivery rate low (no project-level data) | Investigate delivery |
| `WELL_SERVED` | Low | Allocated | No action |

**Positioning line:** *"Grievance systems route complaints. Sangam audits priorities."*

---

## 2. Problem-statement coverage

The statement describes a broken feedback loop with four breaks. This table is the
test of whether the product answers the brief; every phase below maps to a row.

| Break in the loop | Statement wording | Status | Closed by |
|-------------------|-------------------|--------|-----------|
| Voice doesn't arrive | "aggregates citizen development requests via voice, text, and messaging apps across diverse linguistic regions" | ✅ Built (Telegram, WhatsApp, web; voice/photo/text) | — |
| Voice isn't aligned with data | "analyse large datasets combining citizen feedback with national demographic data, infrastructure indices, and public investment plans" | ✅ Engine handles sanctioned and planned money (`PLANNED_NOT_STARTED`, Phase 5); ⚠️ no real project data loaded yet | Data work (after submission) |
| Money isn't steered | "surfacing demand hotspots and recommending high-priority development projects" | ✅ Built (scoring, verdicts, hotspots, simulator, PDF brief) | — |
| **Nobody measures impact** | "no way to measure the impact of large-scale DPI initiatives" | ❌ **Not built** | **Phase 4** |
| National audience | "to national policymakers" | ✅ Roll-up and region picker built (Phase 5); ⚠️ only Karnataka's data is loaded, so the view opens on its districts | More states' data |
| Cross-country | "across BRICS nations" | ⚠️ Architecturally supported, Brazil pack is a stub | Pitch framing (Phase 1.6) now; Phase 6 after submission |

---

## 3. Principles that are not re-litigated

These were decided before code was written (16 Aug) and have held. A change to any of
them requires an explicit decision by Vinay, recorded in Appendix B.

1. **Scoring is arithmetic, never the model.** Gemini writes explanations; it never
   decides order. Every rank is reproducible by hand from `score_components`.
2. **Every AI-generated number is verified** against a closed evidence bundle
   (`services/verifier.py`). Unverifiable output is rejected and replaced by a template.
3. **No model call on the dashboard read path.** Free-tier rate limits must be
   structurally unable to break a demo. Model calls live in intake and batch only.
4. **Indicators are tall** `(region, indicator_key, value, period, source)` — a new
   country ships rows, not migrations.
5. **Weights live in `pack.yaml`**, not code. The engine computes; the government sets
   the equity-vs-reach trade-off.
6. **Every analysis run is versioned.** Reads serve the latest *complete* run; a crashed
   run never blanks the dashboard.
7. **Privacy by construction.** Reporter IDs are HMAC-hashed with a server pepper, PII is
   redacted before first write, clusters under 5 distinct reporters are never displayed.
8. **Degrade, never fail.** If Gemini is down, intake still accepts, stores, replies
   with a tracking ID, and reprocesses later.
9. **Every figure shown to a policymaker resolves to a source.**
10. **KISS and feature independence** (new, 27 Sep): one feature = one folder;
    features communicate through database tables, never by importing each other's
    internals. See §5.3.

---

## 4. Baseline — what exists today

Verified against the code on 27 Sep 2026.

### 4.1 Built and working

| Area | Where |
|------|-------|
| Telegram / WhatsApp (Meta Cloud API) / web intake, voice + photo + text | `services/telegram_adapter.py`, `services/whatsapp_adapter.py`, `routes/webhooks.py`, `frontend/src/pages/CitizenPortal.tsx` |
| Gemini understanding + embedding, graceful degrade + reprocess scheduler | `services/gemini_service.py`, `services/ingestion_service.py`, `services/reprocess_scheduler.py` |
| Location resolution: gazetteer fuzzy match, GPS, one-question confidence-gated confirmation | `services/location_resolver.py` |
| Clustering incl. cross-lingual semantic merge (F5) and emerging hotspots (F14) | `services/clustering_engine.py` |
| Deterministic scoring + verdicts, budget simulator | `services/scoring_engine.py`, `services/simulation_engine.py` |
| Narrative briefs + number verification | `services/verifier.py` |
| PDF briefing export (F10), admin runs + flagged endpoints | `services/pdf_export.py`, `routes/admin.py` |
| Abuse resistance: per-reporter cap, coordinated-flood flag | `services/ingestion_service.py` |
| Country packs + validator CLI; real Karnataka data (JJM + LGD) | `packs/india*`, `services/pack_loader.py`, `utils/validate_pack.py` |
| Versioned analysis runs | `services/run_service.py`, `models.AnalysisRun` |
| Dashboard: overview, map, priorities, simulator, reports | `frontend/src/App.tsx`, `components/*` |
| ~20 backend test files; CI runs backend tests on push | `backend/tests/`, `.github/workflows/ci.yml` |

### 4.2 Known defects and gaps (the honest list)

| ID | Defect | Severity | Phase |
|----|--------|----------|-------|
| K1 | `ADMIN_TOKEN` not set on Render → admin routes 401 for everyone | High | 0 |
| K2 | `flagged_coordinated` column fix not yet deployed → production inserts at risk | **Critical** | Superseded — v2 needs a fresh database (D-22) |
| K3 | Telegram webhook has no secret-token check → anyone can inject fake reports | High | ✅ fixed in rewrite |
| K4 | CORS `allow_origins=["*"]` with `allow_credentials=True` in `main.py` | Medium | ✅ fixed in rewrite |
| K5 | 16 of 24 production embeddings are zero-norm → semantic clustering inert on real data | High | ✅ root cause fixed (failed calls returned zeros; now NULL + retry) |
| K6 | WhatsApp never confirmed end-to-end against a real phone | Medium | 0 |
| K7 | No `LICENSE` file; README says MIT, decision is Apache-2.0 | High (DPG requirement) | ✅ done |
| K8 | No migration framework — schema changes are ad-hoc `ALTER TABLE` in `db_init.py` | High | ✅ Alembic |
| K9 | Frontend has no router — tabs in component state; URLs never change | Medium | ✅ done |
| K10 | CI does not build or lint the frontend | Medium | ✅ done |
| K11 | UI reads as AI-generated (dark gradient, glows, two display fonts, emoji) | Medium | ✅ redesigned |
| K12 | Impact measurement absent | High (brief) | 4 |
| K13 | Brazil pack is a stub (no `pack.yaml`) | High (brief says BRICS) | 1.6 framing, 6 build |
| K14 | Leftover untracked `engine/` folder at repo root | Low | ✅ removed |

---

## 5. Engineering standards

These apply to every phase. A task is not done until it meets §5.5.

### 5.1 Branching and commits

- Work on `main` directly for small changes; a short-lived branch for anything
  touching more than one feature folder. No long-lived branches.
- Stage explicit paths only — **never `git add -A`**.
- Commit message format: `type(scope): summary` — types `feat`, `fix`, `refactor`,
  `test`, `docs`, `chore`. One logical change per commit.
- Before any migration or destructive database action: **print and confirm which
  database `DATABASE_URL` points at.**

### 5.2 Target folder structure (reached in Phase 2)

Organised by **feature**, not by layer. To understand one feature you open one folder.

```
backend/app/
  core/                    shared plumbing only — no business logic
    config.py  db.py  limiter.py  security.py  logging.py
  features/
    intake/                router.py  service.py  telegram.py  whatsapp.py  web.py
    location/              service.py
    understanding/         gemini.py
    clustering/            service.py
    scoring/               service.py  verifier.py
    priorities/            router.py
    simulator/             router.py  service.py
    export/                router.py  pdf.py
    impact/                router.py  service.py          (Phase 4)
    regions/               router.py
    admin/                 router.py
  models/                  SQLAlchemy models (shared contract)
  registry.py              the ONE list of routers main.py mounts
backend/migrations/        Alembic
backend/tests/<feature>/   tests mirror features/

frontend/src/
  routes.tsx               the ONE table of URL → page
  app/                     layout, sidebar, providers, error boundary
  features/
    overview/  priorities/  map/  simulator/  reports/  impact/  citizen-report/
      Page.tsx  components/  api.ts
  ui/                      shared primitives (shadcn/ui)
  lib/                     fetch client, formatters
```

**Page map (frontend URLs):**

| URL | Page | Audience |
|-----|------|----------|
| `/` | Overview | Policymaker |
| `/priorities` | Ranked list with filters in the query string | Policymaker |
| `/priorities/:id` | One recommendation, evidence chain, source reports, PDF | Policymaker |
| `/map` | Hotspot map | Policymaker |
| `/simulator` | Budget simulator | Policymaker |
| `/impact` | Before/after for completed projects (Phase 4) | Policymaker |
| `/reports` | Anonymised citizen reports | Policymaker |
| `/report` | Submit a request | Citizen |
| `/track/:trackingId` | Check a request's status | Citizen |

### 5.3 Feature independence rules

1. A feature may import from `core/` and `models/`. It may **not** import from another
   feature's folder. Enforced in CI by `import-linter` (Phase 2).
2. Features exchange data through **tables** — e.g. clustering writes
   `issue_clusters`; scoring reads it. The table shape is the contract; changing it
   requires a migration and updating both sides' tests.
3. Every optional feature has a kill switch (`FEATURE_<NAME>=false` env var or pack flag).
   Turning it off must not break any other page.
4. Every frontend page fetches its own data and is wrapped in its own error boundary.
   One page failing shows an error *in that page only*.
5. Batch steps run inside a versioned run; a step failing marks the run `failed` and the
   previous complete run keeps serving.

### 5.4 Adding a new feature (the checklist)

1. Create `backend/app/features/<name>/` with `router.py` and `service.py`.
2. Add one line to `backend/app/registry.py`.
3. If it needs new columns/tables → an Alembic migration (never edit `db_init.py`).
4. Create `frontend/src/features/<name>/Page.tsx` and `api.ts`.
5. Add one line to `frontend/src/routes.tsx` and one sidebar entry.
6. Add `backend/tests/<name>/` with unit + route tests.
7. Add a kill switch if the feature is optional.

### 5.5 Definition of done (every task)

- [ ] Unit tests for new logic; a regression test for every bug fixed
- [ ] `pytest` green locally and in CI; frontend `build` + `lint` green
- [ ] Verified against a real database and, where relevant, a real Gemini key —
      not only mocks (mocks have hidden four production bugs in this project)
- [ ] For deployed changes: smoke test (§10.3) passes on the live URL
- [ ] This plan's status table (§6) updated
- [ ] Reported as "deployed, needs your test" until Vinay has confirmed it — never "fixed"

---

## 6. Phase overview

| Order | Phase | Name | Goal | Est. effort (solo) | When | Status |
|-------|-------|------|------|-------------------|------|--------|
| 1st | 0 | Stabilise production | Live system is safe and correct | 1 day | **Before submission** | Code done; deploy + real-phone test pending |
| 2nd | 1 | Submission package | Everything judges need, incl. honest BRICS framing | 1.5–2 days | **Before submission** | 1.1–1.2 done; video, deck, description pending |
| 3rd | 2 | Foundations | Migrations, feature folders, router, CI, independence | 3–4 days | After submission | ✅ Done early (rewrite) |
| 3rd ∥ | 6.1 | Brazil data research | Real, sourced Brazil pack for one estado | 3–5 days, data-bound | After submission, parallel to Phase 2 | Not started |
| 4th | 6.2–6.4 | Second country live | Validate, multi-pack serving, live switch | 1–2 days | After Phase 2 | Not started |
| 5th | 4 | Impact measurement + close the loop | Answer the "measure impact" part of the brief | 2–3 days | After Phase 6 | ✅ Done early (27 Sep) |
| 6th | 3 | SaaS-grade UI | Dashboard a ministry would take seriously | 3–4 days | After Phase 4 | ✅ Done early (rewrite) |
| 7th | 5 | National view + reach metrics + investment plans | "National policymakers", "Depth & Reach" | 2–3 days | After Phase 3 | ✅ Done early (27 Sep) — see "As built" in §7 |
| 8th | 7 | Security & DPG hardening | Signed briefs, retention job, DPGA application | 2 days | Before finale | ✅ Code done early (28 Sep); DPGA application is Vinay's |
| — | 8 | Deferred / cut | Explicitly *not* doing | — | — | — |

The finale date is not yet announced. If it lands before all of this fits, cut from the
bottom of the list (Phase 7, then 5, then 3); **never cut Phase 6** — it is the BRICS claim.

### 6.1 Submission schedule (27–30 Sep)

| Day | Work | Output by end of day |
|-----|------|----------------------|
| **27 Sep** (today, remaining hours) | 0.1 deploy column fix · 0.2 `ADMIN_TOKEN` · 0.3 Telegram secret · 0.4 CORS · 0.7 smoke test | Production safe; smoke test green |
| **28 Sep** | 0.5 embeddings (3h time-box) · 0.6 real-phone WhatsApp test · 1.1 repo hygiene · 1.2 demo data | Phase 0 closed; demo data live |
| **29 Sep** | 1.3 record video · 1.4 deck · 1.6 BRICS framing in both | Video exported; deck complete |
| **30 Sep** | Morning: 1.5 description, final smoke test, **submit by midday** · Afternoon: buffer only | Submitted |

The data teammate can draft the deck (1.4) on 28 Sep from the outline in Phase 1, in
parallel with Phase 0; Vinay reviews on 29 Sep. Rule for the last 48 hours: **no new
features, no refactors** — only fixes to things the video or live link would show broken.

---

## 7. Phases in detail

Each phase lists: **Goal · Why · Scope · Build steps · Tests · Debugging notes ·
Exit criteria · Risks.**

---

### Phase 0 — Stabilise production

**Goal.** The live deployment is safe to show a judge and cannot be corrupted by a
stranger.

**Why.** Everything else — video, deck, live link — is recorded against production. A
defect here is visible in every artefact we submit. K2 alone can break every citizen
insert.

**Scope.** K1–K6.

**Build steps.**

0.1 **Deploy the pending column fix (K2).**
   - Confirm `DATABASE_URL` on Render targets the production Supabase project.
   - Push `main`, let Render deploy, then check the logs for the idempotent
     `ALTER TABLE ... ADD COLUMN IF NOT EXISTS flagged_coordinated` line.
   - Verify: `SELECT column_name FROM information_schema.columns WHERE table_name='citizen_reports';`
     includes `flagged_coordinated`.

0.2 **Set `ADMIN_TOKEN` (K1).** Generate with `python -c "import secrets;print(secrets.token_urlsafe(32))"`,
   set in Render env, redeploy. Verify `GET /api/v1/admin/runs` returns 401 without the
   header and 200 with `Authorization: Bearer <token>`.

0.3 **Telegram webhook secret (K3).**
   - Add `TELEGRAM_WEBHOOK_SECRET` to config.
   - Register the webhook with `setWebhook?url=...&secret_token=<secret>`.
   - In `routes/webhooks.py`, reject requests whose `X-Telegram-Bot-Api-Secret-Token`
     header does not match, using `hmac.compare_digest`. Return 403.
   - Keep the "always 200 on processing errors" behaviour for *authenticated* requests
     only.

0.4 **Restrict CORS (K4).** `ALLOWED_ORIGINS` env var (comma-separated): the Vercel
   production domain + `http://localhost:5173`. Set `allow_credentials=False` unless a
   cookie-based flow exists (none does today).

0.5 **Investigate zero-norm embeddings (K5)** — follow §9 strictly; do not guess.
   - Reproduce: `SELECT id, created_at, (embedding <#> embedding) FROM citizen_reports`
     — identify which rows are zero and what they share (date, channel, degraded path?).
   - Leading hypothesis to test, not assume: rows ingested while Gemini was unavailable
     got a zero-vector placeholder and the reprocess path never overwrote it.
   - Fix at source (placeholder must be `NULL`, never zeros; reprocess must select
     `embedding IS NULL`), add a regression test, backfill the 16 rows, re-run analysis.
   - Add a DB guard: reject zero-norm vectors at write time.

0.6 **Confirm WhatsApp end-to-end (K6).** Real phone → voice note in Kannada → tracking
   ID reply → report visible in `/reports` after reprocess. Record the result.

0.7 **Write the smoke-test script** `backend/scripts/smoke_test.py` (see §10.3) — used
   after every deploy from now on.

**Tests.**
- Unit: Telegram secret match / mismatch / missing header; CORS config parsing;
  embedding writer rejects zero vectors; reprocess picks up `NULL` embeddings.
- Integration (real DB): ingest with Gemini mocked to fail → embedding is `NULL`, not
  zeros → reprocess fills it.
- Manual: 0.6 on a real phone; smoke test on the live URL.

**Debugging notes.** K5 is the one real unknown. Time-box investigation to 3 hours;
if the root cause isn't found, ship the write-guard + backfill (symptom containment),
record the open question in §11, and move on — the demo must not wait on it.

**Exit criteria.** All of K1–K6 closed or explicitly contained; smoke test green on
production; Vinay has sent one real Telegram and one real WhatsApp message and seen
them on the dashboard.

**Risks.** Backfill touches production data → run in a transaction, count rows before
and after, and only after confirming the target DB.

---

### Phase 1 — Submission package

**Goal.** Every required submission artefact exists, is consistent, and tells the
story of the join.

**Why.** Judges score what they see in 3–5 minutes of video and 10–12 slides.
Unshipped polish counts for nothing; an unclear story loses Problem-Solution Fit (20%).

**Scope.** Repo hygiene, demo data, video, deck, description, live link.

**Build steps.**

1.1 **Repo hygiene.**
   - Add `LICENSE` (Apache-2.0) at repo root; fix README's license line (K7).
   - Remove the stray `engine/` folder after confirming nothing imports it (K14).
   - Rewrite README: one-paragraph pitch, the verdict table, screenshot, live link,
     "run it in 15 minutes" quick-start, data provenance statement, links to both plan
     documents.
   - Add `CONTRIBUTING.md` (how to add a country pack) — this is DPG evidence.

1.2 **Demo dataset.** ✅ `python -m scripts.seed_demo` — 4,704 synthetic reports in six
   languages, marked `is_synthetic`. Places, households and tap coverage are real JJM/LGD
   data. There is **no real spending data**, so the demo shows `UNSERVED_GAP`,
   `DELIVERY_GAP`, `DEMAND_HOTSPOT` and `MONITOR` — never an invented `STALLED_ALLOCATION`.

1.3 **Demo script (video, 3–5 min).**
   1. 0:00 — Open on a `DELIVERY_GAP` with its evidence chain: "Jal Jeevan Mission reports
      95%+ of households here have a tap. N residents say the water never comes." Records say
      served; residents disagree — the finding no complaint tracker can produce.
   2. 0:40 — Reveal where it came from: voice notes in Kannada/Hindi/English, clustered
      across languages.
   3. 1:30 — Send a real voice note live on WhatsApp/Telegram; show the tracking ID.
   4. 2:10 — Budget simulator: "₹500 crore — what should we fund?", change weights.
   5. 3:00 — Export the PDF brief: every number cites a source. Drop it on the **Verify a
      brief** page ("Authentic and unchanged"), then a copy with one character edited
      ("Altered after export").
   6. 3:40 — Built for BRICS: architecture in one diagram; show `packs/india/` and run the pack
      validator on screen; say plainly "India runs on real government data; Brazil is the next
      pack, and the engine does not change." (There is no `packs/brazil/` yet — do not show
      one.) DPG + privacy.
   Never open on the chatbot or the intake form.

1.4 **Pitch deck (10–12 slides).** Problem (the broken loop) → Insight (the join) →
   Verdict matrix → Demo screenshots → How it works → Why trust it (arithmetic ranking,
   verified numbers, privacy floor) → Reach (languages, channels) → **Built for BRICS**
   (see 1.6) → Scale (numbers from the design doc §2) + Deployability (packs, open source,
   $0 run cost) → Competitors ("they route complaints, we audit priorities") → Roadmap
   (Phase 6 Brazil first; Phases 2–5 and 7 are already built) → Team.
   Include the synthetic-data sentence (Appendix B, D-11) before anyone asks.

1.5 **2–3 line description.** Draft (corrected 28 Sep: the first draft said "government
   spending records", which Sangam does not have — D-20):
   > Sangam is an open-source Digital Public Good that hears citizens in their own language —
   > voice, text or photo, over WhatsApp, Telegram or the web — and sets what they report beside
   > official data, to show officials where public services are missing or failing on the
   > ground. It ranks priorities with transparent arithmetic, checks every AI-written number
   > against a cited source, and signs every brief so it cannot be quietly altered. A new BRICS
   > country is a folder of data, not new code; it runs today on real Indian government data.

1.6 **BRICS framing — honest, specific, checkable.** The brief says "across BRICS
   nations"; judges will ask "does it work outside India?" The answer must be true in
   every word:
   - **What is true now:** the engine contains no country-specific columns or strings; a
     country is a folder of CSV/YAML (`pack.yaml`, admin units, tall indicators,
     sanctioned projects); weights, languages, currency and admin levels are pack
     config; the validator checks a pack before the engine loads it; embeddings cluster
     across languages without per-language rules.
   - **What is not true yet, and must not be implied:** Brazil is not live. Never show the
     Brazil stub as working or put it on the country switcher.
   - **The slide:** one diagram (engine in the middle, India and Brazil packs either side),
     a table of what each BRICS country would supply (admin registry, infrastructure
     indicators, spending source — e.g. India: LGD / JJM / PFMS dashboards; Brazil: IBGE /
     SNIS / Portal da Transparência), and the line *"India live on real data. Brazil is
     our next pack — the engine does not change."*
   - **Q&A answer to rehearse:** "What changes for South Africa?" → "A folder: its
     municipalities, its indicators, its budget lines, and a pack.yaml with isiZulu,
     Afrikaans and English. Zero engine code — the validator tells you when the folder is
     complete."

**Tests.** Full smoke test on production; open the live link in an incognito window on
a phone; run the quick-start from a fresh clone in under 15 minutes (N7).

**Exit criteria.** All five submission items exist; the live link works logged-out on
mobile; the video shows at least one *real* message sent during recording.

**Risks.** Recording against production during a free-tier rate-limit window → record
after running analysis, since the dashboard makes no model calls.

---

### Phase 2 — Foundations

**Goal.** Make the codebase safe to change: schema migrations, feature folders, real
routing, CI on both halves, enforced independence.

**Why.** Every later phase adds tables and pages. Without migrations, each schema change
is a production risk (K2 happened exactly this way). Without routing and feature folders,
every new page grows `App.tsx`.

**Scope.** K8, K9, K10; §5.2 structure; §5.3 rules.

**Build steps.**

2.1 **Adopt Alembic (K8).**
   - `alembic init backend/migrations`; point `env.py` at `app.models` metadata and
     `DATABASE_URL`.
   - Generate a **baseline** migration from current models; on production, run
     `alembic stamp head` (marks it as applied without executing) — never `upgrade` a
     baseline onto a populated DB.
   - Delete the ad-hoc `ALTER TABLE` block from `db_init.py`; container start runs
     `alembic upgrade head`.
   - Enable the `postgis` and `vector` extensions in the baseline explicitly.

2.2 **Backend feature folders.** Move files mechanically into `features/` per §5.2,
   one feature per commit, tests green after each move. No logic changes in the same
   commit as a move. Rename `routes/__init__.py` → `registry.py`.

2.3 **Import-linter.** Add `import-linter` with an `independence` contract: modules under
   `app.features.*` may not import each other. Run in CI. Where scoring needs clustering
   output today via a function call, replace it with a read of `issue_clusters`.

2.4 **Frontend routing and data fetching (K9).**
   - Add `react-router` and `@tanstack/react-query`.
   - Create `routes.tsx` per the page map in §5.2; move each tab into
     `features/<name>/Page.tsx`; filters live in the URL query string.
   - Each page uses its own `useQuery` hooks from its own `api.ts`; remove the global state
     from `App.tsx`.
   - Wrap each route in an error boundary.

2.5 **CI for the frontend (K10).** New job: `npm ci`, `npm run lint`, `npm run build`,
   `npm test` (Vitest, see §8). Trigger on `frontend/**`.

2.6 **Kill switches.** `core/config.py` exposes `FEATURE_*` flags; `registry.py` mounts
   only enabled routers; the frontend reads `/api/v1/pack` for enabled features and hides
   sidebar entries accordingly.

**Tests.**
- `alembic upgrade head` on an empty Postgres produces a schema identical to
  `create_all` (compare with `pg_dump --schema-only`).
- `alembic downgrade -1 && upgrade head` round-trips for every new migration.
- Whole backend suite green after each move commit.
- Vitest: router renders every URL; an error thrown in one page does not unmount the
  sidebar or another page.

**Debugging notes.** Import errors after moves are the expected failure; fix by updating
imports, never by adding `sys.path` hacks. If the linter flags a cross-feature import,
the fix is a table read or moving shared code to `core/`, not an exemption.

**Exit criteria.** Folder tree matches §5.2; CI green with the independence contract;
every page has a URL; a migration has been applied to production via Alembic at least
once.

**Risks.** Stamping the wrong DB. Mitigation: §5.1 target-database check, printed and
confirmed.

---

### Phase 3 — SaaS-grade UI

**Goal.** A dashboard that reads like Linear/Stripe/Plausible: calm, dense, trustworthy.

**Why.** "Could a ministry pilot this?" is part of Deployability (20%). The current look
signals "generated", which undercuts the trust story the evidence chain earns.

**Scope.** K11. Visual system + page redesigns. No new backend features.

**Build steps.**

3.1 **Design system.** Tailwind + shadcn/ui. Tokens:
   - Light theme default, dark theme available. Neutral grey scale + one accent.
   - Colour reserved for meaning: the five verdict colours and nothing else competes.
   - One typeface (Inter or Geist), `font-variant-numeric: tabular-nums` on all figures.
   - 1px borders, radius 6–8px, no gradients, no glows, no emoji, no staggered animations.

3.2 **App shell.** Left sidebar (Overview, Priorities, Map, Simulator, Impact, Reports),
   top bar with country/pack switcher and "data as of <run completed_at>".

3.3 **Overview.** 4 KPIs in one row (unserved gaps, stalled capital, reports this month,
   regions covered) → top 5 priorities table → small map. Each KPI links to its filtered page.

3.4 **Priorities.** Sortable table (rank, region, sector, verdict, score, reporters,
   money allocated) → row opens a side panel: score breakdown bar, evidence list with
   sources, anonymised source reports, "Export brief" button.

3.5 **Source markers.** Every number rendered via a `<Figure value source />` component
   showing a small marker; hover/tap reveals source name, period and link. This is the
   differentiator made visible.

3.6 **States.** Designed empty, loading (skeletons matching final layout) and error
   states for every page. Mobile layout for the citizen pages; desktop-first for
   policymaker pages but no horizontal scroll at 375px.

**Tests.** Vitest + Testing Library for `<Figure>`, table sorting, filters-in-URL.
Accessibility: contrast AA, keyboard navigation through the priorities table. Manual
review at 375px, 768px, 1440px in both themes.

**Exit criteria.** No gradient/glow/emoji remains; every number on screen has a source
marker; a first-time user can find "why is this #1?" in two clicks.

**Risks.** Scope creep. Rule: no backend changes in this phase.

---

### Phase 4 — Impact measurement and closing the loop

**Goal.** Answer "no way to measure the impact" with evidence, and tell citizens what
happened to their request.

**Why.** It is the only part of the problem statement with no answer today (§2). It also
produces the strongest possible demo ending: "this project completed in March; complaints
here fell 70%; the 43 people who reported it were notified."

**Scope.** New `features/impact/`; status notifications in `features/intake/`.

**Build steps.**

4.1 **Impact metric (model-free).** For each `expenditure` with `status='completed'` and a
   `completion_date`, match its `(region_id, sector)` cluster and compute:
   ```
   before_rate = distinct reporters in [completion − W, completion) / population × 1000
   after_rate  = distinct reporters in (completion + G, completion + G + W] / population × 1000
   change_pct  = (after_rate − before_rate) / before_rate
   ```
   `W` = window (default 90 days), `G` = grace period (default 30 days) — both in
   `pack.yaml`. Output labels: `IMPROVED` (≤ −30%), `NO_CHANGE`, `WORSENED` (≥ +30%),
   `INSUFFICIENT_DATA` (fewer than `min_distinct_reporters` in either window).
   Computed inside the versioned analysis run; stored in a new `impact_assessments` table
   (Alembic migration).

4.2 **Impact API + page.** `GET /api/v1/impact` (list), `GET /api/v1/impact/{id}`.
   `/impact` page: table of completed projects with before/after rates and label; detail
   shows a weekly complaint-rate line with the completion date marked.

4.3 **Close the loop.** When a run changes a cluster's state (newly funded, project
   completed), queue a notification per distinct `reporter_hash` in that cluster.
   - Requires storing a reply address: store the channel chat ID **encrypted** (Fernet,
     key in env), separate from the hash; delete it after the notification or after 180
     days. This is a privacy trade-off — **Vinay decides** before build (see Appendix B,
     D-16 pending).
   - Respect channel rules: Telegram free-form; WhatsApp outside the 24h window needs an
     approved template message.
   - Rate-limited, idempotent (one notification per reporter per state change).

4.4 **Citizen tracking page.** `/track/:trackingId` using the existing
   `GET /api/v1/citizens/{tracking_id}`: status timeline (received → grouped → prioritised
   → funded → completed).

**Tests.**
- Unit: impact formula for improved / worsened / insufficient data / zero before_rate
  (no division by zero) / window boundaries.
- Unit: notification idempotency; encrypted chat ID never logged.
- Integration: seeded scenario with a completed project and falling reports produces
  `IMPROVED`.

**Debugging notes.** Before/after comparisons are sensitive to seeding; if every project
reads `INSUFFICIENT_DATA`, check reporter counts per window before touching thresholds.

**Exit criteria.** `/impact` shows at least one real-data project with a correctly
computed label; a test reporter receives a status notification on Telegram.

**Risks.** Correlation is not causation — label copy must say "complaints fell after
completion", never "the project caused". Real JJM completion dates may be sparse → demo
uses seeded reports around real completion dates, disclosed as synthetic.

---

### Phase 5 — National view, reach metrics, investment plans

**Goal.** Serve "national policymakers" and make Depth & Reach measurable.

**Scope.**

5.1 **Roll-up.** Aggregate clusters and priorities up the admin tree
   (block → district → state → country) using `AdminRegion.parent_id`. Region picker
   drives every page; national level shows states ranked by unserved-gap count and
   stalled capital.

5.2 **Coverage metrics.** Overview panel: languages received (count + list), channels
   used, regions with ≥1 report, **unlocated reports count** (honesty metric), degraded
   reports pending reprocess.

5.3 **Investment plans.** Add `planned` to the expenditure `status` enum (migration).
   Verdict logic: high demand + only `planned` money → `PLANNED_NOT_STARTED` (distinct
   from unserved and stalled). Data: pack CSV rows with `status=planned`.

**Tests.** Roll-up sums equal leaf sums (property test); verdict table tests for the new
status; coverage metrics against a seeded fixture.

**Exit criteria.** A user can go from national → state → district → one recommendation in
three clicks; coverage panel numbers match SQL counts.

**As built (27 Sep).**
- **Region scope.** `GET /overview` and `GET /priorities` take `?region=<id>` and include that
  place and every place under it (`app/core/regions.py`). One picker (`ui/RegionPicker.tsx`)
  on both pages, kept in the URL. At region scope, `reports.unlocated` is `null`: an unplaced
  report is inside no region.
- **Roll-up.** `GET /rollup?region=` lists the places one level down, each with its verdict
  counts and `places_needing_action` (distinct places inside with a fund or audit verdict),
  sorted by that count. With no region it skips any chain of single children, so India
  (one state loaded) opens on Karnataka's districts. Only displayable priorities are counted.
  **Changed from the plan:** no "stalled capital" column — there is no real spending data (D-20).
- **Unlocated drill-down.** `GET /unlocated` returns `{total, reasons: [{reason, count}]}` and
  nothing else — never text, tracking IDs or dates (D-24). Reasons are recorded when they
  happen, in `reports.location_failure` (migration `0003`): `no_place_named`,
  `place_not_recognised`, `low_confidence_match`, `gave_up_after_questions`; plus
  `awaiting_place` / `awaiting_confirmation` from status, and `not_recorded` for older rows
  (no guessed backfill). Also fixed: a reprocessed report whose GPS point matched no place was
  left as `understood`; it is now `unlocated` with a reason.
- **Planned money.** Verdict order is now stalled → delivery → **planned** → hotspot → unserved:
  high demand with only `planned` projects is `PLANNED_NOT_STARTED`, in the Audit group (D-23),
  unless official data says the place is served (then `DELIVERY_GAP`). It never appears in the
  demo because no project data is loaded.
- **Tests.** Region scope, roll-up ordering, roll-up sums equal the whole, unlocated
  counts-only (asserts no text in the response), failure reasons at each intake path, and the
  planned-money verdict table.

---

### Phase 6 — Second country pack, live

**Priority.** First build priority after submission — the brief says "across BRICS
nations" (D2, confirmed 27 Sep). 6.1 starts the day after submission, in parallel with
Phase 2; 6.2–6.4 start when Phase 2 is done.

**Goal.** Prove "a new country is a folder" live: switch India ↔ Brazil on the dashboard
with zero code changes.

**Build steps.**

6.1 **Data (research, not code) — owned by the data teammate.** `packs/brazil/`:
   `pack.yaml` (BRL, `pt`, levels country → estado → município), `admin_units.csv`
   (IBGE codes + population), `indicators.csv` (SNIS water/sanitation),
   `sanctioned_projects.csv` (Portal da Transparência / state budget lines). Scope to
   **one estado** first; get **one município** fully right end-to-end before scaling.
   Follow Appendix A.
   **Checkpoint after 2 days:** has real, sourced project-level water spending been
   found for that estado? If not, switch to the fallback below immediately rather than
   searching further.

6.2 **Validate.** `python -m app.utils.validate_pack brazil` passes.

6.3 **Multi-pack serving.** Today `ACTIVE_COUNTRY_PACK` is a single env var. Make runs and
   reads keyed by `country_code`; top-bar switcher selects it. Scoring/clustering code
   must not change — if it does, that is a bug in the pack abstraction and gets fixed
   there.

6.4 **Portuguese intake.** Send Portuguese messages; confirm cross-lingual clustering
   places them correctly.

**Tests.** The full suite parameterised over both packs; a test asserting no
country-specific strings exist in `features/` (grep for `IN-`, `district`, `INR`).

**Exit criteria.** Live switch between packs on production; a Brazilian recommendation
with a real-data evidence chain.

**Risks and fallback.** Brazilian project-level spend data may not be obtainable in time.
A second *Indian* state does **not** answer a BRICS brief, so the fallback stays in
Brazil: ship a real but thinner pack — real IBGE admin units and population plus real
SNIS indicators, with no `sanctioned_projects.csv`. The engine then produces only the
indicator-based verdicts (`DELIVERY_GAP` / `UNSERVED_GAP` without spend matching), and
the dashboard labels the pack "spending data not yet loaded" rather than implying
coverage it doesn't have. That still proves the engine runs unchanged on a second
country, which is the claim.

---

### Phase 7 — Security and DPG hardening

**Goal.** Close the remaining trust gaps a government reviewer would raise.

**Build steps.**

7.1 **Signed briefs.** Generate one Ed25519 key pair (private key in env). Each exported
   PDF embeds `run_id`, a SHA-256 hash of the evidence bundle, and a signature;
   `GET /api/v1/verify/{run_id}` and a public key published in the repo let anyone
   verify a brief was not altered. (This is the one place public-key cryptography earns
   its keep; a full PKI / own certificate authority / mTLS is explicitly out of scope.)

7.2 **Retention job.** Scheduled deletion of raw media older than
   `media_retention_days` (pack), and of encrypted chat IDs per Phase 4.3 policy.

7.3 **Security review.** Webhook auth for every channel, rate limits on public routes,
   dependency audit (`pip-audit`, `npm audit`), secrets only in env, no PII in logs
   (grep logs for phone-number patterns in a test).

7.4 **DPG readiness.** Apply to the Digital Public Goods Alliance registry: license,
   ownership, documentation, data privacy, do-no-harm statement, open standards. Add
   `docs/privacy.md` and `docs/do-no-harm.md` when applying.

**Exit criteria.** A tampered PDF fails verification; retention job verified on a seeded
old file; DPGA application submitted (Vinay submits — it is an organisational
declaration).

**As built (28 Sep).**
- **7.1 Signed briefs — changed from the plan.** Signing a hash of the evidence would let
  someone edit the *visible* PDF text and still pass. So the signature covers **every byte of
  the PDF** and is appended after `%%EOF` as one line (`%SANGAM-SIGNATURE <key id> <sig>`),
  which PDF readers ignore. Run ID and evidence are inside the signed bytes. Re-saving in a PDF
  editor drops the line, so the brief reads as unsigned. Key: `BRIEF_SIGNING_KEY` (base64
  Ed25519 seed, env only; in `backend/.env` and `backend/.env.render`). Public key:
  `docs/brief-signing-key.pub` (key ID `6a4450a69681646e`). `POST /api/v1/verify` (upload,
  5 MB, 20/min, nothing stored) and `GET /api/v1/verify/public-key` replace the planned
  `GET /verify/{run_id}`. Offline: `python -m scripts.verify_brief <pdf>`. Dashboard page
  `/verify`. Checked on a real exported brief: valid → one byte changed → tampered (D-25).
- **7.2 Retention — already scheduled.** The keepalive workflow (every 12 h) calls
  `/admin/notify` (deletes expired chat IDs) and `/admin/runs` (deletes media past
  `media_retention_days`). It runs only once the GitHub secrets `SANGAM_API_URL` and
  `SANGAM_ADMIN_TOKEN` are set — a deploy step.
- **7.3 Security review.** Webhooks: Telegram secret token and WhatsApp HMAC, both fail closed;
  admin routes all behind the bearer token. **Fixed:** the HTTP client logged every request URL
  at INFO, and Telegram URLs contain the bot token — every reply would have written the token
  to Render's logs; `httpx`/`httpcore` now log at WARNING only (D-26). **Fixed:** rate limits
  added to `/track/{id}` (30/min, stops bulk guessing of tracking IDs), brief export (20/min)
  and `/simulate` (30/min). Tests assert no phone number, chat ID or bot token reaches the logs.
  `pip-audit` and `npm audit`: no known vulnerabilities. No secrets in tracked files.
- **7.4 DPG.** `docs/privacy.md` and `docs/do-no-harm.md` drafted from what the code does,
  marked for Vinay's review before any application.

---

### Phase 8 — Deferred / cut (decided, not forgotten)

| Item | Decision | Reason |
|------|----------|--------|
| F15 authenticated policymaker workspace (Clerk) | Deferred past finale | Judges get an open read-only link (D-13); a login is one more thing to fail live |
| Natural-language "ask the data" chatbot | Cut | Violates principle 3 (no model on read path) |
| More chat channels (SMS, Signal, etc.) | Deferred | Depth over breadth; three channels already |
| Own PKI / mTLS | Cut | No threat it addresses that TLS + webhook auth + signed briefs don't |
| Redis / job queue | Deferred | ~3 req/s peak at national scale; Postgres-backed scheduler suffices until measured otherwise |
| IVR / missed-call voice line, Bhashini ASR | Roadmap slide only | Strong reach story; cost and integration time not justified before finale |

---

## 8. Testing strategy

### 8.1 Layers

| Layer | Tool | What it covers | Runs |
|-------|------|----------------|------|
| Unit | pytest | Pure logic: scoring, verdicts, impact formula, resolver, verifier, hashing | Every push (CI) |
| Route | pytest + FastAPI `TestClient` | Status codes, auth, validation, response shapes | Every push |
| Integration | pytest against real Postgres + PostGIS + pgvector (docker compose) | SQL, spatial queries, vectors, migrations | Before every deploy; nightly in CI (Phase 2) |
| Contract | pytest | Each table a feature writes has the columns its readers expect | Every push |
| Frontend unit | Vitest + Testing Library | Components, formatting, filters-in-URL, error boundaries | Every push (Phase 2) |
| Smoke | `scripts/smoke_test.py` | Live deployment: health, overview, priorities, PDF, admin auth | After every deploy |
| Manual E2E | Real phone | Telegram/WhatsApp voice → dashboard | Before recording, before finale |

### 8.2 Rules

- **Every bug fix ships with a failing-first regression test** (write the test, see it
  fail, fix, see it pass).
- **Mocks are for Gemini and channel APIs only.** Database behaviour is tested against a
  real Postgres — SQLite has hidden spatial and vector bugs in this project before.
- Gemini tests use recorded fixtures of real responses, including malformed JSON and
  timeouts.
- Deterministic seeds for any randomness; tests must not depend on wall-clock time
  (inject `now`).
- Coverage target is not a percentage: every verdict, every degrade path and every auth
  check has a test.

### 8.3 Test data

- `tests/fixtures/` holds a tiny pack (3 regions, 2 sectors) used by unit tests.
- Integration tests use a seeded Karnataka subset.
- No production data in tests, ever.

---

## 9. Debugging playbook

The rule: **investigate before proposing.** On 3 Aug and 11 Sep, several confident
hypotheses were wrong before the real cause was found; evidence beat intuition every time.

1. **Reproduce.** Get the exact failing input and environment. If it can't be reproduced,
   add logging and wait — do not fix blind.
2. **Locate the zone.** Intake (live) / batch (analysis run) / serve (dashboard)? Check
   `/health`, the latest `analysis_runs` row, and Render logs in that order.
3. **Check the boring things first:** which database is targeted, env vars present,
   migrations applied, latest deploy actually live, Gemini quota.
4. **State hypotheses explicitly** and the evidence that would disprove each. Test the
   cheapest first. Record disproved hypotheses — they are information.
5. **Find the root cause, not the symptom.** A value is wrong → find where it was first
   written wrong.
6. **Write the failing test**, then fix, then watch it pass.
7. **Verify on the real system** (real DB, real Gemini, live URL as relevant).
8. **Report precisely:** what was wrong, what caused it, what fixed it, what is still
   unverified. "Deployed, needs your test" until confirmed.

**Where to look, by symptom:**

| Symptom | First checks |
|---------|--------------|
| Citizen got no reply | Webhook auth (403 in logs?), adapter exceptions, Gemini degrade path, channel token |
| Report never appears on dashboard | `region_id` null (unlocated)? Below 5-reporter floor? Analysis run not re-run / failed? |
| Dashboard empty or stale | Latest *complete* run; frontend `VITE_API_URL`; CORS errors in browser console |
| Clusters not merging across languages | Zero-norm or `NULL` embeddings; merge threshold in pack |
| Wrong verdict | `score_components` and evidence bundle for that priority — recompute by hand |
| 500 on insert | Schema drift: compare model columns to DB; migration missing |

---

## 10. Release and deployment process

### 10.1 Environments

| Env | Backend | Frontend | Database |
|-----|---------|----------|----------|
| Local | `docker compose up` | `npm run dev` | Local Postgres (docker) |
| Production | Render | Vercel | Supabase (Postgres + PostGIS + pgvector) |

### 10.2 Deploy checklist

1. CI green on `main`.
2. Confirm target DB; if a migration is included, run `alembic upgrade head --sql` first
   to read the SQL, then apply.
3. Deploy backend (Render) → frontend (Vercel).
4. Run smoke test against production.
5. If smoke fails: roll back via Render's previous deploy; migrations must be
   backwards-compatible (additive) so rollback is safe.
6. Ask Vinay before any deploy — deploys are outward-facing.

### 10.3 Smoke test (`backend/scripts/smoke_test.py`)

Checks, each with a clear PASS/FAIL line:
- `GET /health` → 200, expected pack
- `GET /api/v1/overview` → 200, non-zero reports
- `GET /api/v1/priorities` → ≥1 item, each with a verdict and evidence
- `GET /api/v1/export/{first_id}.pdf` → 200, `application/pdf`
- `GET /api/v1/admin/runs` without token → 401
- `POST /api/v1/webhooks/telegram` without secret → 403
- Latest `analysis_runs` row is `complete` and newer than 24h (warn only)

---

## 11. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase 0/1 slip past the 30 Sep deadline | High | Critical | §6.1 schedule; no new features or refactors in the last 48h; submit by midday 30 Sep with an afternoon buffer |
| Judges mark down "BRICS" because only India is live | High | High | Phase 1.6 honest framing + rehearsed Q&A; Phase 6 is first after submission |
| Gemini free-tier rate limit during demo | Medium | High | No model on read path; record after running analysis; paid tier only if needed in final week |
| Production schema drift on deploy | Medium | Critical | Alembic from Phase 2; target-DB check |
| Fake reports via unauthenticated webhook | Medium | High | Phase 0.3 |
| Zero-norm embeddings root cause not found | Medium | Medium | Write-guard + backfill contains it |
| Judge asks "is this data real?" | High | High | Volunteer the synthetic-data sentence first |
| Brazil spending data not obtainable | Medium | High | 2-day checkpoint in 6.1; fall back to a real Brazil pack without spend data (see Phase 6) — never a second Indian state |
| Solo developer bus factor | High | High | This plan + the simple companion + tests as documentation |

---

## Appendix A — Data sourcing rules

(Carried over from the former `DATA-SOURCES.md`.)

**The one rule: every number comes from a published source, and the source is recorded.**
Never estimate, never fill a gap with a plausible figure, never carry a number across
years silently. A missing row is fine; an invented row is the only thing that can
genuinely damage the project. Blank beats wrong.

**Pack files** (per country, under `backend/packs/<country>/`):

| File | Columns |
|------|---------|
| `admin_units.csv` | `unit_id, country_code, level, name, name_variants, parent_unit_id, external_code, population, source_name, source_url` |
| `indicators.csv` (tall) | `unit_id, indicator_key, value, unit, period, source_name, source_url` |
| `sanctioned_projects.csv` | `project_id, unit_id, sector, title, amount, currency, status, sanctioned_date, completion_date, source_name, source_url` |
| `SOURCES.md` | One block per dataset + coverage table + known gaps |

- `unit_id` is readable and stable: `IN`, `IN-KA`, `IN-KA-KOLAR`, `IN-KA-KOLAR-MALUR`.
- `name_variants` (pipe-separated) include English spellings, common misspellings,
  local-script and Hindi names, and old names. Every variant rescues requests the
  resolver would otherwise drop.
- `amount` is a plain number in base units (`40000000`, not "4 crore").
- `status` ∈ `planned | sanctioned | in_progress | completed | stalled`. Use `stalled`
  **only** when a source explicitly says so — never infer it from an old date.
- Indicator keys in use: `water.piped_household_pct`, `sanitation.household_toilet_pct`,
  `road.all_weather_connectivity_pct`, `power.household_electrified_pct`,
  `health.phc_per_100k`, `education.school_infra_index`, `demography.below_poverty_pct`.

**Sources.** India: Jal Jeevan Mission (`ejalshakti.gov.in`), Local Government Directory
(LGD), data.gov.in, Census, PMGSY, Swachh Bharat Mission, state budget documents. There is
no open PFMS API — use published dashboards. Brazil: IBGE (units, population), SNIS
(water/sanitation), Portal da Transparência.

**Method.** Never hand-type; download and transform with a script in `packs/<c>/build/`.
Get one district fully right end-to-end before scaling. Validate with the pack validator.

---

## Appendix B — Decision log

| # | Decision | Chosen | Date |
|---|----------|--------|------|
| D-1 | Deep sector + region | Water, Karnataka (JJM publishes district coverage) | 16 Aug |
| D-2 | Need taxonomy | 6: water, roads, electricity, health, education, sanitation | 16 Aug |
| D-3 | Second country | Brazil (SNIS; Portuguese proves cross-lingual) | 16 Aug |
| D-4 | Admin depth | All India districts; blocks for Karnataka only | 16 Aug |
| D-5 | Indicator storage | Tall | 16 Aug |
| D-6 | Weights | In `pack.yaml`; default demand 0.35 · deficit 0.30 · reach 0.15 · coverage −0.20 | 16 Aug |
| D-7 | Who ranks | Arithmetic; Gemini writes prose only | 16 Aug |
| D-8 | License | Apache-2.0 (patent grant) — LICENSE file to be added in Phase 1 | 16 Aug |
| D-9 | Stalled allocations | Separate list from unserved gaps ("fund this" ≠ "send an inspector") | 16 Aug |
| D-10 | Privacy floor | 5 distinct reporters to display; small clusters still count toward scoring | 16 Aug |
| D-11 | Synthetic data | Volunteer it: *"The citizen messages are synthetic, generated to mirror plausible complaint patterns. The places, the number of rural households and the share with a tap connection are real government data, and every number links to its source. We don't have district spending data yet, so Sangam doesn't invent it."* (Corrected 27 Sep: the original sentence claimed budget lines were real; they were not.) | 16 Aug, corrected 27 Sep |
| D-12 | Retention | Redacted text indefinite; raw audio/photo 90 days | 16 Aug |
| D-13 | Judge access | Open read-only link, no login | 16 Aug |
| D-14 | Gemini tier | Free tier through build; paid only in final week if needed | 25 Aug |
| D-15 | Folder structure | Feature folders + independence rules (§5.2–5.3) | 27 Sep |
| D-16 | Store encrypted chat IDs to notify citizens (Phase 4.3) | **Yes** — encrypted (Fernet, key only on the server), one update when the report reaches the priority list, then deleted; unsent ones deleted after 180 days; no key = nothing stored | 27 Sep |
| D-16b | Impact without project data | **Both** — real JJM 2019→2026 progress vs residents now; before/after-project comparison ready for when project data exists | 27 Sep |
| D-17 | Official scope wording | **"Across BRICS nations"** — Brazil is the first post-submission build (Phase 6); pitch frames it honestly before then | 27 Sep |
| D-18 | Submission deadline | **30 Sep 2026** confirmed — only Phases 0–1 before submission | 27 Sep |
| D-19 | Rewrite now vs patch | **Full rewrite now** (Vinay's decision); production keeps the old code until the new version passes its checks and Vinay approves a deploy | 27 Sep |
| D-20 | Spending data | **Never invented.** Verdicts join demand to real statistics; `DEMAND_HOTSPOT` where no statistic exists | 27 Sep |
| D-21 | Ranking order | Fund/audit verdicts first, then hotspots to verify, then monitor; score orders within each tier | 27 Sep |
| D-23 | Action group for `PLANNED_NOT_STARTED` | **Audit** — money is promised but nothing started; the official's question is "why is this stuck?", as for a stalled allocation. No fifth action group | 27 Sep |
| D-24 | Unlocated reports drill-down | **Counts by reason only, never report text** (Vinay). Text is shown only for a place × need with ≥ 5 distinct reporters (D-10); an unlocated report has no place, so it can never qualify | 27 Sep |
| D-25 | What a brief signature covers | **The whole PDF file**, not a hash of the evidence — otherwise the visible text could be edited without breaking the seal | 28 Sep |
| D-26 | HTTP client logging | `httpx`/`httpcore` at WARNING: at INFO they log request URLs, and Telegram URLs carry the bot token | 28 Sep |
| D-22 | Production database for v2 | **Pending — Vinay's decision:** new empty Supabase project (recommended) or reset the existing one | — |

---

## Appendix C — Glossary

| Term | Meaning |
|------|---------|
| **The join** | Matching citizen demand and government spending on the same `(region, sector)` key |
| **Verdict** | The label a priority gets from the join (unserved gap, stalled allocation, …) |
| **Country pack** | A folder of CSV/YAML files describing one country's regions, statistics, spending and weights |
| **Embedding** | A list of numbers representing a message's meaning; similar meanings → nearby numbers, across languages |
| **Zero-norm vector** | An embedding that is all zeros — carries no meaning and breaks similarity comparisons |
| **Analysis run** | One batch execution of cluster → join → score → explain, versioned by `run_id` |
| **Evidence bundle** | The closed list of facts (with sources) the AI may cite when writing an explanation |
| **Migration** | A versioned, reversible script that changes the database schema (Alembic) |
| **Webhook** | A URL a service (Telegram, WhatsApp) calls to deliver a message to us |
| **CORS** | Browser rule deciding which websites may call our API |
| **Smoke test** | A quick automated check that a deployment's main paths work |
| **Kill switch** | A config flag that turns a feature off without code changes |
| **DPG / DPGA** | Digital Public Good; the Alliance that certifies them |
| **Ed25519 signature** | Public-key signature proving a document hasn't been altered since it was signed |
