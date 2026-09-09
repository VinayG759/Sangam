# Pending — Action Needed From Vinay

Kept current as we go. Each item says what's blocked and what unblocks it.

## 1. Hand the GPS/confirmation plan to Gemini in Antigravity

Plan is written and ready: `docs/superpowers/plans/2026-09-09-gps-and-location-confirmation.md`
(4 tasks — location resolver, ingestion service, Telegram adapter, WhatsApp adapter).
Have Gemini read and implement it, then tell me it's done so I can test/debug/review.

## 2. Clerk account for auth

Plan already written: `docs/superpowers/plans/2026-08-25-clerk-auth-foundation.md`.
Create a free app at `dashboard.clerk.com`, then give me (or Gemini) the three values
from its API Keys page: **Publishable key**, **JWKS URL**, **Issuer**. Nothing can start
on that plan until these exist.

## 3. Decide: chase the zero-norm embedding bug now, or later?

16 of 24 real `citizen_reports.embedding` rows in production are zero-norm vectors,
which silently breaks cosine-distance comparisons for both the semantic split and
merge clustering logic (fails safe — no crash, just inert). Found during F5's
calibration, never investigated. Your call on priority.

## 4. Decide: is F16 (second state, proven live) worth the time?

Checked — the `india` pack only has real Karnataka data; the `brazil` pack is a stub
(no `pack.yaml`, can't even load). Proving this properly needs *real* government data
for a second state (same JJM/LGD sources as Karnataka), which is a research task, not
a code task, and eats real time against the 30 Sep deadline. Worth it, or drop it from
scope?

## 5. Confirm WhatsApp actually works end-to-end

Code's been live a while; never confirmed tested against a real phone number.

## 6. Work through the rest of the test-plan artifact

Dashboard checklist, privacy verification, remaining sector-coverage messages —
partially done, not finished. (Artifact: "Sangam Test Plan", published earlier.)

---

## Done, no action needed

- F5 — cross-lingual clustering merge (real cross-bucket duplicate collapsing)
- F14 — Emerging Hotspot Detection
- Design doc + `docs/ARCHITECTURE.md` kept current through both
