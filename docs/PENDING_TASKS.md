# Pending — Action Needed From Vinay

Kept current as we go. Each item says what's blocked and what unblocks it.

## 1. Set `ADMIN_TOKEN` on Render

New required env var — Phase 17/20's admin routes (`/api/v1/admin/runs`,
`/api/v1/admin/flagged`) return 401 for everyone until this is set. Pick
any strong random value and set it in Render's environment settings.

## 2. Redeploy soon — a critical bug is fixed and waiting

Phase 20 added a new `CitizenReport.flagged_coordinated` column that, un-fixed,
would have broken every citizen report insert in production (no migration
framework, and `citizen_reports` already holds real data). It's fixed
locally (idempotent `ALTER TABLE` in `db_init.py`, runs automatically on
next deploy) — worth pushing and redeploying promptly rather than letting
it sit.

## 3. Clerk account for auth

Plan already written: `docs/superpowers/plans/2026-08-25-clerk-auth-foundation.md`.
Create a free app at `dashboard.clerk.com`, then give me (or Gemini) the three values
from its API Keys page: **Publishable key**, **JWKS URL**, **Issuer**. Nothing can start
on that plan until these exist. Note: that plan creates `backend/app/routes/admin.py`,
which now already exists (Phase 17) — the plan needs a quick update to extend it
instead of creating it fresh, before that work starts.

## 5. Decide: chase the zero-norm embedding bug now, or later?

16 of 24 real `citizen_reports.embedding` rows in production are zero-norm vectors,
which silently breaks cosine-distance comparisons for both the semantic split and
merge clustering logic (fails safe — no crash, just inert). Found during F5's
calibration, never investigated. Your call on priority.

## 6. Decide: is F16 (second state, proven live) worth the time?

Checked — the `india` pack only has real Karnataka data; the `brazil` pack is a stub
(no `pack.yaml`, can't even load). Proving this properly needs *real* government data
for a second state (same JJM/LGD sources as Karnataka), which is a research task, not
a code task, and eats real time against the 30 Sep deadline. Worth it, or drop it from
scope?

## 7. Confirm WhatsApp actually works end-to-end

Code's been live a while; never confirmed tested against a real phone number.

## 8. Work through the rest of the test-plan artifact

Dashboard checklist, privacy verification, remaining sector-coverage messages —
partially done, not finished. (Artifact: "Sangam Test Plan", published earlier.)

---

## Done, no action needed

- F5 — cross-lingual clustering merge (real cross-bucket duplicate collapsing)
- F14 — Emerging Hotspot Detection
- Phase 23 — GPS location capture + confidence-gated location confirmation
- Phase 17 — PDF briefing export + admin runs endpoint
- Phase 20 — abuse resistance (per-reporter cap + coordinated-flood flag)
- Phase 22 — media size limit + pack validator CLI
- Design doc + `docs/ARCHITECTURE.md` kept current throughout
