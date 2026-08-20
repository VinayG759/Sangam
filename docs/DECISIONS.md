# Decision log

Decisions made 16 Aug 2026, before any code was written. Recorded so nobody
re-litigates them mid-build, and so the pitch answers are consistent.

## Scope

| # | Decision | Chosen |
|---|----------|--------|
| 1 | Deep sector + region | **Water, Karnataka** — Jal Jeevan Mission publishes district-wise coverage, and water is a need people voice out loud |
| 2 | Need taxonomy size | **6** — water, roads, electricity, health, education, sanitation |
| 3 | Second country | **Brazil** — SNIS has municipal water data; Portuguese also proves cross-lingual clustering visually |
| 4 | Admin depth | **All India districts + block level for Karnataka only.** Nationwide block data is a week of work on its own |

## Architecture

| # | Decision | Chosen | Reversible? |
|---|----------|--------|-------------|
| 5a | Indicator storage | **Tall** — one row per (place, statistic) | Hard. Wide→tall after data exists means rewriting every query |
| 5b | Scoring weights | **In `pack.yaml`, not code** | Easy. Chosen for the live demo slider |
| 5c | Who ranks | **Arithmetic, not the model.** Gemini writes prose only | Hard, and it's the answer to the hardest Q&A question |
| 6 | Repo | **Public, Apache-2.0** | Public timestamps commits (rule 02 evidence); Apache has the patent grant MIT lacks |
| 7 | Dashboard | **React**, not Streamlit | "Could a ministry pilot this" is 20% of the score |

## Values

| # | Decision | Chosen | Reasoning |
|---|----------|--------|-----------|
| 8 | Scoring posture | **Balanced** — demand 0.35 · deficit 0.30 · reach 0.15 · coverage −0.20 | Between "help the worst-off place" and "help the most people" |
| 8b | Stalled allocations | **Two separate lists** | "Fund this" and "send an inspector" are different actions and must not compete on one ranking |
| 9 | Aggregation floor | **5 distinct reporters to display** — but small clusters still *count* toward scoring | Protects complainants without silencing small villages |
| 10 | Retention | **Redacted text indefinite · raw audio/photo 90 days** | Voice is biometric; once embedded, the audio is never needed again |

## Presentation

| # | Decision | Chosen |
|---|----------|--------|
| 11 | Synthetic data | **Volunteer it before being asked**, with the exact partition (see below) |
| 12 | Demo opening | Open on a **ranked recommendation with a stalled-allocation verdict**, then reveal it came from 412 voice notes. Never open on the chatbot |
| 13 | Judge access | **Open read-only link.** A login is one more thing to fail live |
| 14 | Seeded volume | **~4,000 requests** across both countries |
| 15 | WhatsApp | **Twilio sandbox only.** Join code + QR on a slide |

### The synthetic-data sentence — say this before anyone asks

> "The citizen messages are synthetic, generated to mirror observed complaint
> patterns. Everything else — the maps, the population, the water coverage, the
> budget lines — is real government data, and every number links to its source."

| Data | Status |
|------|--------|
| Citizen requests | Synthetic |
| Admin units + boundaries | Real (LGD / IBGE) |
| Population + demographics | Real (census) |
| Infrastructure indicators | Real (government) |
| Sanctioned budget lines | Real (government) |

**Never** let a slide claim an unqualified "40,000 citizen requests".

Also: send 3–4 **real** voice notes live during the demo, so you can say
*"those were real, thirty seconds ago."*

## The deadline that isn't optional

**By end of day 3 (18 Aug), confirm that district-level sanctioned budget data
actually exists for water in Karnataka.** Sangam's whole claim is the join. If
that data isn't real and obtainable, retreat to whatever sector in whatever state
does have it — one proven sector beats five imagined ones.

Do not build against that data until you have seen it with your own eyes.
