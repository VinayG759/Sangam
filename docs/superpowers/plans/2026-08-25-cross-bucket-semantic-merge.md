# Cross-Bucket Semantic Merge (F5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the real gap in F5 (cross-lingual clustering): today `clustering_engine.py` only *splits* an already-matched `(region_id, sector)` bucket when embeddings disagree; it never *merges* two buckets that resolution noise (a different sector tag, a neighboring ward, or a GPS-path vs. gazetteer-path split) kept apart even though they're the same real-world report.

**Architecture:** After the existing split step produces `final_cluster_map` (cluster index → report ids), add a merge pass: build a lightweight per-cluster region hint from member reports' `region_id`, then for every pair of clusters whose region hint is the same or parent/child, compare their centroid embeddings via pgvector cosine distance (`<=>`). Pairs within a threshold get merged before `IssueCluster` rows are created. Geographic locality is a hard gate, not a tiebreaker — two clusters must already be in the same or a directly-related administrative unit before their embeddings are even compared, so this can never merge two distant, unrelated real-world events just because their text reads similarly.

**Tech Stack:** Python 3.11, SQLAlchemy (sync `Session`), PostgreSQL + pgvector (`<=>` cosine distance operator), pytest with `unittest.mock.MagicMock`.

**Spec:** Sangam System Design Document §7 (AI pipeline, Call 2 — embeddings), §17 "Cross-lingual clustering, for real" (`https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db`), and `docs/IMPLEMENTATION_PLAN.md` Phase 12.

## Global Constraints

- $0 running cost: no new external service, no new paid dependency — everything here is existing Postgres/pgvector.
- Stage explicit file paths when committing (`git add <path>`), never `git add -A`.
- No `Co-Authored-By` trailer on commits.
- Before committing, run `git diff --cached --stat` and confirm it matches what you intended to stage — a past session in this repo once committed only unrelated file renames while believing the real code fix was included.
- `clustering_engine.py` runs on a sync SQLAlchemy `Session`, not `AsyncSession` — match the surrounding code's style exactly (no `await`).
- All new/changed backend code must keep `pytest backend/tests/` fully green, not just the tests this plan adds.

---

### Task 1: Add the cross-bucket merge pass

**Files:**
- Modify: `backend/app/services/clustering_engine.py:198` (immediately after `cluster_map = final_cluster_map`, before `# 3. Create Issue Clusters`)
- Test: `backend/tests/test_clustering_engine.py`

**Interfaces:**
- Consumes: `cluster_map: dict[int, list[int]]` (produced by the existing split step), `AdminRegion` model (`id`, `parent_id` columns — already defined in `backend/app/models/models.py:18-43`), `CitizenReport` model (`id`, `region_id` columns).
- Produces: a mutated `cluster_map` with related, near-duplicate clusters merged, consumed unchanged by the existing `# 3. Create Issue Clusters` loop below it — no signature or contract changes to anything downstream.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_clustering_engine.py` and add this helper and three tests at the end of the file (after the existing `test_clustering_engine_retries_pending_reports`):

```python
def _make_mock_db_for_merge(merge_distance: float, region2_parent_id, will_merge: bool) -> MagicMock:
    db = MagicMock()

    # No GPS-based spatial clusters -- both groups arrive via the gazetteer
    # (region_id, sector) path instead, which is where the merge gap lives.
    mock_cluster_result = MagicMock()
    mock_cluster_result.fetchall.return_value = []

    mock_centroid = MagicMock()
    mock_centroid.scalar.return_value = "POINT(0 0)"

    def execute_side_effect(stmt, params=None, *args, **kwargs):
        stmt_str = str(stmt)
        if "ST_ClusterDBSCAN" in stmt_str:
            return mock_cluster_result
        if "centroid c" in stmt_str:
            # Split-query: keep every report inside its own group (small
            # distance), so the merge step is what's under test here, not
            # the pre-existing split step.
            ids = params["report_ids"]
            result = MagicMock()
            result.fetchall.return_value = [MagicMock(id=i, distance=0.05) for i in ids]
            return result
        if "WITH a AS" in stmt_str:
            result = MagicMock()
            result.scalar.return_value = merge_distance
            return result
        if "ST_Centroid" in stmt_str:
            return mock_centroid
        return MagicMock()

    db.execute.side_effect = execute_side_effect

    report1 = CitizenReport(id=1, sector="water",      region_id=1, urgency_score=5)
    report2 = CitizenReport(id=2, sector="water",      region_id=1, urgency_score=5)
    report3 = CitizenReport(id=3, sector="sanitation", region_id=2, urgency_score=5)
    report4 = CitizenReport(id=4, sector="sanitation", region_id=2, urgency_score=5)

    tail = (
        [[report1, report2, report3, report4]]       # merged: one final cluster
        if will_merge else
        [[report1, report2], [report3, report4]]     # not merged: two final clusters
    )

    citizen_report_query_mock = MagicMock()
    citizen_report_query_mock.filter.return_value.all.side_effect = [
        [],                                     # pending_reports
        [report1, report2, report3, report4],   # gazetteer_reports
        [report1, report2],                     # merge region-hint: cluster 0
        [report3, report4],                     # merge region-hint: cluster 1
        *tail,                                  # "Create Issue Clusters" loop
    ]

    region1 = MagicMock(id=1, parent_id=None,             population=1000.0, centroid=None)
    region2 = MagicMock(id=2, parent_id=region2_parent_id, population=1000.0, centroid=None)
    region_by_id = {1: region1, 2: region2}

    def query_side_effect(model):
        if model is CitizenReport:
            return citizen_report_query_mock
        q = MagicMock()
        if model is AdminRegion:
            q.get.side_effect = lambda rid: region_by_id.get(rid)
            q.filter.return_value.first.return_value = region1
        return q
    db.query.side_effect = query_side_effect

    db.added_objects = []
    def add_side_effect(obj):
        if isinstance(obj, AnalysisRun) and obj.id is None:
            obj.id = 99
        if obj not in db.added_objects:
            db.added_objects.append(obj)
    db.add.side_effect = add_side_effect

    return db


def _patch_gemini_and_verifier(monkeypatch):
    class MockGemini:
        def generate_policy_brief(self, data):
            return {"summary": "S", "why_prioritized": "W", "fiscal_gap_analysis": "F", "recommended_action": "R"}
    monkeypatch.setattr("app.services.clustering_engine.gemini_service", MockGemini())

    class MockVerifier:
        def verify_brief(self, text, bundle):
            return {"verified": True, "unverified_numbers": []}
    monkeypatch.setattr("app.services.clustering_engine.verification_engine", MockVerifier())


@pytest.fixture
def mock_db_for_merge(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.05, region2_parent_id=1, will_merge=True)
    _patch_gemini_and_verifier(monkeypatch)
    return db


@pytest.fixture
def mock_db_for_merge_too_distant(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.5, region2_parent_id=1, will_merge=False)
    _patch_gemini_and_verifier(monkeypatch)
    return db


@pytest.fixture
def mock_db_for_merge_unrelated_region(monkeypatch):
    db = _make_mock_db_for_merge(merge_distance=0.05, region2_parent_id=999, will_merge=False)
    _patch_gemini_and_verifier(monkeypatch)
    return db


def test_cross_bucket_merge_joins_related_regions_within_threshold(mock_db_for_merge):
    clustering_engine.process_and_prioritize(mock_db_for_merge)

    clusters = [obj for obj in mock_db_for_merge.added_objects if isinstance(obj, IssueCluster)]

    # Two gazetteer buckets -- (region 1, water) and (region 2, sanitation)
    # -- start out separate. Region 2 is a child of region 1, and their
    # embeddings are near-identical (0.05, under the 0.15 merge threshold),
    # so they should end up as ONE cluster covering all 4 reports.
    assert len(clusters) == 1
    assert clusters[0].report_count == 4


def test_cross_bucket_merge_skips_when_distance_exceeds_threshold(mock_db_for_merge_too_distant):
    clustering_engine.process_and_prioritize(mock_db_for_merge_too_distant)

    clusters = [obj for obj in mock_db_for_merge_too_distant.added_objects if isinstance(obj, IssueCluster)]

    # Same related regions as the merge case, but the embeddings are 0.5
    # apart -- well over the threshold. Must stay two separate clusters.
    assert len(clusters) == 2
    assert sorted(c.report_count for c in clusters) == [2, 2]


def test_cross_bucket_merge_skips_when_regions_unrelated(mock_db_for_merge_unrelated_region):
    clustering_engine.process_and_prioritize(mock_db_for_merge_unrelated_region)

    clusters = [obj for obj in mock_db_for_merge_unrelated_region.added_objects if isinstance(obj, IssueCluster)]

    # Same near-identical embeddings as the merge case, but region 2's
    # parent is 999, not region 1 -- geographically unrelated. Must NOT
    # merge just because the text reads similarly; two clusters expected.
    assert len(clusters) == 2
    assert sorted(c.report_count for c in clusters) == [2, 2]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_clustering_engine.py -v`
Expected: the three new tests FAIL (the merge pass doesn't exist yet, so the first two gazetteer buckets never merge and `test_cross_bucket_merge_joins_related_regions_within_threshold` sees 2 clusters instead of 1). The two pre-existing tests (`test_semantic_clustering_split`, `test_clustering_engine_retries_pending_reports`) must still PASS — if either breaks, stop and fix the test setup before continuing.

- [ ] **Step 3: Implement the merge pass**

In `backend/app/services/clustering_engine.py`, find this line (currently line 198):

```python
            cluster_map = final_cluster_map
```

Replace it with:

```python
            cluster_map = final_cluster_map

            # Phase 2 (F5, continued): cross-bucket semantic merge. The split
            # loop above only prevents *over*-merging inside a bucket that
            # bucketing already put together; it never lets two buckets that
            # got separated by resolution noise -- a different sector tag, a
            # neighboring ward, or one path via GPS DBSCAN and the other via
            # the gazetteer -- rejoin, even when they're the same real-world
            # report. Threshold calibrated against real Karnataka data in
            # backend/scripts/calibrate_merge_threshold.py.
            logger.info("Applying cross-bucket semantic merge...")
            MERGE_DISTANCE_THRESHOLD = 0.15

            cluster_region_hint: dict[int, int] = {}
            for c_idx, report_ids in cluster_map.items():
                reports_for_hint = db.query(CitizenReport).filter(CitizenReport.id.in_(report_ids)).all()
                region_ids = [r.region_id for r in reports_for_hint if r.region_id]
                if region_ids:
                    cluster_region_hint[c_idx] = max(set(region_ids), key=region_ids.count)

            def _regions_are_related(region_a: int, region_b: int) -> bool:
                if region_a == region_b:
                    return True
                ra = db.query(AdminRegion).get(region_a)
                rb = db.query(AdminRegion).get(region_b)
                if ra is None or rb is None:
                    return False
                return ra.parent_id == region_b or rb.parent_id == region_a

            def _cluster_pair_distance(ids_a: list[int], ids_b: list[int]):
                row = db.execute(text("""
                    WITH a AS (SELECT avg(embedding) AS c FROM citizen_reports WHERE id IN :a AND embedding IS NOT NULL),
                         b AS (SELECT avg(embedding) AS c FROM citizen_reports WHERE id IN :b AND embedding IS NOT NULL)
                    SELECT (a.c <=> b.c) FROM a, b WHERE a.c IS NOT NULL AND b.c IS NOT NULL;
                """), {"a": tuple(ids_a), "b": tuple(ids_b)}).scalar()
                return row

            merged_away = set()
            cluster_indices = list(cluster_map.keys())
            for i, idx_a in enumerate(cluster_indices):
                if idx_a in merged_away or idx_a not in cluster_region_hint:
                    continue
                for idx_b in cluster_indices[i + 1:]:
                    if idx_b in merged_away or idx_b not in cluster_region_hint:
                        continue
                    if not _regions_are_related(cluster_region_hint[idx_a], cluster_region_hint[idx_b]):
                        continue
                    distance = _cluster_pair_distance(cluster_map[idx_a], cluster_map[idx_b])
                    if distance is not None and distance <= MERGE_DISTANCE_THRESHOLD:
                        cluster_map[idx_a] = cluster_map[idx_a] + cluster_map[idx_b]
                        merged_away.add(idx_b)

            for idx in merged_away:
                del cluster_map[idx]
```

Clusters with no region hint at all (no member report has a resolved `region_id`) are simply skipped by the merge pass — locality can't be established safely for them, so they pass through exactly as the split step produced them.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_clustering_engine.py -v`
Expected: all 5 tests PASS (the 2 pre-existing tests plus the 3 new ones).

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes. This change touches a shared pipeline function — a regression anywhere else in clustering, scoring, or the routes that read `IssueCluster`/`Priority` would show up here.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/clustering_engine.py backend/tests/test_clustering_engine.py
git commit -m "feat: merge semantically near-duplicate clusters across related regions"
```

---

### Task 2: Calibrate the merge threshold against real data

**Files:**
- Create: `backend/scripts/calibrate_merge_threshold.py`
- Modify (conditionally): `backend/app/services/clustering_engine.py` (only the `MERGE_DISTANCE_THRESHOLD` value and its comment, if calibration suggests 0.15 is wrong)

**Interfaces:**
- Consumes: the real database configured via `DATABASE_URL` (same settings object as the rest of the app, `app.config.settings` indirectly via `app.db.SessionLocal`), `IssueCluster`/`AdminRegion`/`CitizenReport` rows produced by a real `process_and_prioritize()` run.
- Produces: no code interface — this is a one-off diagnostic script, not something other tasks import.

This task has no automated pass/fail — the "test" is a human reading real numbers, the same way the existing 0.35 split threshold's comment (`"a genuine same-issue multilingual pair yielded ~0.12 ... unrelated issue ... ~0.42"`) was arrived at.

- [ ] **Step 1: Write the calibration script**

Create `backend/scripts/calibrate_merge_threshold.py`:

```python
"""
One-off calibration script for clustering_engine.py's cross-bucket semantic
merge threshold (MERGE_DISTANCE_THRESHOLD). Run against a real database with
real Gemini embeddings -- a guessed constant that feeds directly into what a
policymaker sees in an evidence bundle should be checked against real data,
not shipped on intuition alone.

Usage (from the backend/ directory, with DATABASE_URL pointing at a database
that already has at least one completed process_and_prioritize() run):
    python scripts/calibrate_merge_threshold.py

Prints every pair of region-related clusters, sorted by embedding distance,
so a human can inspect where a natural gap falls between "same issue" and
"different issue" pairs, and pick MERGE_DISTANCE_THRESHOLD accordingly.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from app.db import SessionLocal
from app.models.models import IssueCluster, AdminRegion
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = SessionLocal()
    try:
        clusters = db.query(IssueCluster).all()
        regions_by_id = {r.id: r for r in db.query(AdminRegion).all()}

        pairs = []
        for i, a in enumerate(clusters):
            for b in clusters[i + 1:]:
                region_a, region_b = regions_by_id.get(a.region_id), regions_by_id.get(b.region_id)
                if region_a is None or region_b is None:
                    continue
                related = (
                    a.region_id == b.region_id
                    or region_a.parent_id == b.region_id
                    or region_b.parent_id == a.region_id
                )
                if not related:
                    continue

                report_ids_a = [r.id for r in a.reports]
                report_ids_b = [r.id for r in b.reports]
                if not report_ids_a or not report_ids_b:
                    continue

                distance = db.execute(text("""
                    WITH a AS (SELECT avg(embedding) AS c FROM citizen_reports WHERE id IN :a AND embedding IS NOT NULL),
                         b AS (SELECT avg(embedding) AS c FROM citizen_reports WHERE id IN :b AND embedding IS NOT NULL)
                    SELECT (a.c <=> b.c) FROM a, b WHERE a.c IS NOT NULL AND b.c IS NOT NULL;
                """), {"a": tuple(report_ids_a), "b": tuple(report_ids_b)}).scalar()

                if distance is not None:
                    pairs.append((distance, a.id, a.title, b.id, b.title))

        pairs.sort()
        for distance, id_a, title_a, id_b, title_b in pairs:
            print(f"{distance:.4f}  cluster {id_a} ({title_a!r})  <->  cluster {id_b} ({title_b!r})")

        if not pairs:
            print("No region-related cluster pairs found -- run process_and_prioritize on real data first.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against real data**

Run: `cd backend && python scripts/calibrate_merge_threshold.py` (with `DATABASE_URL` pointing at the real Supabase database — same value already used for local testing against production earlier this project).

Read the printed distances. Look for a natural gap in the sorted list — pairs clearly describing the same real-world issue should cluster together at the low end; pairs describing genuinely different issues should sit clearly above them. This mirrors exactly how the existing 0.35 split threshold was chosen (see the comment at the top of `test_semantic_clustering_split`).

- [ ] **Step 3: Update the threshold if the real data disagrees with 0.15**

If the observed gap sits somewhere other than 0.15, edit `MERGE_DISTANCE_THRESHOLD` in `backend/app/services/clustering_engine.py` (added in Task 1) and update its comment to cite the real observed numbers, e.g.:

```python
            # ... Threshold calibrated against real Karnataka data in
            # backend/scripts/calibrate_merge_threshold.py: a genuine
            # cross-bucket duplicate pair measured ~0.09, the closest
            # genuinely-different pair measured ~0.24.
            MERGE_DISTANCE_THRESHOLD = 0.15
```

If 0.15 already sits cleanly in the gap, leave it as-is but still update the comment to record the real numbers observed, not just the provisional reasoning.

- [ ] **Step 4: Re-run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: still fully green — the synthetic fixtures in Task 1's tests use fixed distances (0.05 / 0.5) chosen to sit unambiguously on either side of any reasonable threshold near 0.15, so a small calibration adjustment should not flip them. If it does, the threshold moved into a range where the synthetic test fixtures are no longer clearly separated — treat that as a signal to also widen the gap between the fixtures' distances in Task 1's tests, not just the threshold.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/calibrate_merge_threshold.py backend/app/services/clustering_engine.py
git commit -m "chore: calibrate cross-bucket merge threshold against real data"
```
