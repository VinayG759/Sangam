# Emerging Hotspot Detection (F14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flag clusters whose complaint *rate* is accelerating, not just clusters that are large — a time-windowed comparison on report timestamps already collected, so a problem surfaces before it has accumulated enough total volume to already rank highly on score alone.

**Architecture:** Compute the flag as a pure function of a cluster's member reports' `reported_at` timestamps (last N days vs. the prior N days), inside `clustering_engine.py`'s existing per-cluster loop, and merge it directly into the `score_details` dict that already becomes `Priority.details` — a JSON column already returned in full by the existing `/api/v1/priorities` route. **No database migration, no new column, no new API endpoint** — the project has no migration framework (schema changes go through `Base.metadata.create_all`, which only creates missing tables, never alters existing ones), so anything requiring `ALTER TABLE` against the real production database is out of scope for this plan. This keeps the change entirely inside JSON columns that already exist.

**Tech Stack:** Python 3.11 (`datetime`/`timedelta`, stdlib only), pytest. React 19 / TypeScript on the frontend, no new dependency.

**Spec:** Sangam System Design Document §17 "New capabilities" (F14) (`https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db`).

## Global Constraints

- No new database column or migration — this project has no Alembic/migration tooling, and the real production database already holds real citizen data that must not be touched by a schema change outside this plan's scope.
- $0 running cost: no new dependency, backend or frontend.
- Stage explicit file paths when committing (`git add <path>`), never `git add -A`.
- No `Co-Authored-By` trailer on commits.
- `clustering_engine.py` runs on a sync SQLAlchemy `Session` — no `await` in that file.
- Full backend suite (`pytest backend/tests/`) must stay green. Frontend has no test runner installed — verify via `npm run build` (type-check) plus manual browser check, matching how every other frontend feature in this repo has been verified.

---

### Task 1: Backend — compute and persist the hotspot flag

**Files:**
- Modify: `backend/app/services/clustering_engine.py`
- Test: `backend/tests/test_clustering_engine.py`

**Interfaces:**
- Produces: `_is_emerging_hotspot(reports: list[CitizenReport]) -> bool`, a pure function taking a list of `CitizenReport` ORM objects (or anything with a `.reported_at` attribute) and returning whether that cluster's report rate is accelerating. Also produces the side effect that every `Priority.details` dict gains an `"is_emerging_hotspot"` key — this is what Task 2's frontend reads.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_clustering_engine.py`. Add this import near the top of the file (with the other imports):

```python
from datetime import datetime, timedelta
from app.services.clustering_engine import clustering_engine, _is_emerging_hotspot
```

(This replaces the existing `from app.services.clustering_engine import clustering_engine` import line — just add `_is_emerging_hotspot` to it.)

Then add these tests at the end of the file:

```python
def _report_at(days_ago: float) -> MagicMock:
    return MagicMock(reported_at=datetime.utcnow() - timedelta(days=days_ago))


def test_is_emerging_hotspot_true_when_recent_rate_accelerates():
    # 3 reports in the last 7 days, 1 report 7-14 days ago -> ratio 3.0, >= 2.0.
    reports = [_report_at(1), _report_at(2), _report_at(3), _report_at(9)]
    assert _is_emerging_hotspot(reports) is True


def test_is_emerging_hotspot_false_when_below_minimum_recent_count():
    # Only 2 recent reports -- below the minimum of 3, regardless of ratio.
    reports = [_report_at(1), _report_at(2)]
    assert _is_emerging_hotspot(reports) is False


def test_is_emerging_hotspot_false_when_rate_not_accelerating():
    # 3 recent, 3 prior -> ratio 1.0, below the 2.0 threshold.
    reports = [_report_at(1), _report_at(2), _report_at(3), _report_at(8), _report_at(9), _report_at(10)]
    assert _is_emerging_hotspot(reports) is False


def test_is_emerging_hotspot_true_when_all_new_with_no_prior_activity():
    # 3 recent, 0 prior -- brand-new activity is itself the strongest signal
    # (and avoids a division by zero).
    reports = [_report_at(1), _report_at(2), _report_at(3)]
    assert _is_emerging_hotspot(reports) is True


def test_is_emerging_hotspot_false_when_reports_missing_timestamp():
    reports = [MagicMock(reported_at=None), MagicMock(reported_at=None), MagicMock(reported_at=None)]
    assert _is_emerging_hotspot(reports) is False


def test_priority_details_include_emerging_hotspot_flag(mock_db_for_split):
    clustering_engine.process_and_prioritize(mock_db_for_split)

    priorities = [obj for obj in mock_db_for_split.added_objects if isinstance(obj, Priority)]

    assert priorities
    for p in priorities:
        assert "is_emerging_hotspot" in p.details
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_clustering_engine.py -v`
Expected: FAIL with `ImportError: cannot import name '_is_emerging_hotspot'` (the function doesn't exist yet).

- [ ] **Step 3: Implement the hotspot detection**

In `backend/app/services/clustering_engine.py`, add this import at the top of the file, alongside the existing imports:

```python
from datetime import datetime, timedelta
```

Add these constants and function after the existing `SECTOR_DELIVERY_INDICATOR` dict (near the top of the file, before `class ClusteringEngine:`):

```python
# Time-windowed velocity thresholds for emerging-hotspot detection (F14,
# docs/superpowers/plans/2026-09-07-emerging-hotspot-detection.md). Flags a
# RATE change, not a total-volume threshold -- a cluster with 3 reports this
# week and 0 last week is worth surfacing even if a 40-report cluster still
# outranks it on raw score.
HOTSPOT_WINDOW_DAYS = 7
HOTSPOT_MIN_RECENT_REPORTS = 3
HOTSPOT_ACCELERATION_RATIO = 2.0


def _is_emerging_hotspot(reports) -> bool:
    """
    Flags a cluster whose complaint RATE is accelerating, not just large --
    a time-windowed comparison on report timestamps already collected, so a
    problem surfaces before it has accumulated enough total volume to
    already rank highly on score alone. Deterministic arithmetic, no model
    call, consistent with this project's model-free scoring philosophy.
    """
    now = datetime.utcnow()
    recent_cutoff = now - timedelta(days=HOTSPOT_WINDOW_DAYS)
    prior_cutoff = now - timedelta(days=HOTSPOT_WINDOW_DAYS * 2)

    recent_count = sum(1 for r in reports if r.reported_at and r.reported_at >= recent_cutoff)
    prior_count = sum(
        1 for r in reports
        if r.reported_at and prior_cutoff <= r.reported_at < recent_cutoff
    )

    if recent_count < HOTSPOT_MIN_RECENT_REPORTS:
        return False
    if prior_count == 0:
        return True
    return (recent_count / prior_count) >= HOTSPOT_ACCELERATION_RATIO
```

Find the line that calls `scoring_engine.calculate_priority_score(...)` and assigns its result to `score_details`. Immediately after that call (after the closing `)` of the `calculate_priority_score(...)` call, before the line `fully_funded = allocated_budget >= estimated_cost`), add:

```python
                score_details["is_emerging_hotspot"] = _is_emerging_hotspot(reports)
```

(`reports` is already in scope at this point in the loop — it's the same list used to compute `avg_urgency` a few lines above.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_clustering_engine.py -v`
Expected: all tests PASS (5 new unit tests for `_is_emerging_hotspot`, 1 new integration test, plus every pre-existing test in this file).

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/clustering_engine.py backend/tests/test_clustering_engine.py
git commit -m "feat: flag clusters with accelerating complaint rate as emerging hotspots"
```

---

### Task 2: Frontend — surface the hotspot badge

**Files:**
- Modify: `frontend/src/components/PriorityList.tsx`

**Interfaces:**
- Consumes: `priority.details.is_emerging_hotspot` (boolean), from the existing `Priority.details: Record<string, unknown> | null` field already typed in `frontend/src/api.ts` — no type changes needed, `Boolean(p.details?.is_emerging_hotspot)` follows the exact same pattern already used in `PriorityCard.tsx` for `partial_evidence`.

- [ ] **Step 1: Add the badge**

Open `frontend/src/components/PriorityList.tsx`. Find this line inside the `.map((p, i) => { ... })` block:

```tsx
                <span className={`badge ${meta.cls}`}>{meta.label}</span>
```

Replace it with:

```tsx
                <span className={`badge ${meta.cls}`}>{meta.label}</span>
                {Boolean(p.details?.is_emerging_hotspot) && (
                  <span style={{
                    fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
                    background: 'rgba(249,115,22,0.12)', color: '#f97316',
                    border: '1px solid rgba(249,115,22,0.35)',
                  }}>
                    🔥 Emerging
                  </span>
                )}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run build`
Expected: builds cleanly with no TypeScript errors.

- [ ] **Step 3: Manual verification**

Run: `cd frontend && npm run dev`, open the dashboard, go to the Priorities tab. If no priority in the current data has `is_emerging_hotspot: true` (likely, since it depends on real report timing), this is expected — confirm instead that the existing verdict badges and layout are visually unaffected (no broken spacing, no console errors). If you want to see the badge render, temporarily hardcode `Boolean(p.details?.is_emerging_hotspot) || true` in a local-only edit, check the badge looks right, then revert before committing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PriorityList.tsx
git commit -m "feat: show an Emerging badge on priorities with an accelerating report rate"
```
