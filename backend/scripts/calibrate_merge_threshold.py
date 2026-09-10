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

        # Mirror clustering_engine.py's cluster_region_hint exactly: the
        # engine never uses IssueCluster.region_id (the cluster's final,
        # post-attribution region, which can come from an unreliable
        # "just take the first ward" fallback) to decide which cluster pairs
        # are region-related. It instead takes the majority region_id among
        # the cluster's own member CitizenReport rows, with no fallback --
        # a cluster with no report carrying a region_id is simply excluded.
        # Using IssueCluster.region_id here would let this script validate a
        # relatedness gate the engine doesn't actually use.
        cluster_region_hint: dict[int, int] = {}
        for c in clusters:
            region_ids = [r.region_id for r in c.reports if r.region_id]
            if region_ids:
                cluster_region_hint[c.id] = max(set(region_ids), key=region_ids.count)

        pairs = []
        nan_count = 0
        for i, a in enumerate(clusters):
            if a.id not in cluster_region_hint:
                continue
            for b in clusters[i + 1:]:
                if b.id not in cluster_region_hint:
                    continue
                region_a = regions_by_id.get(cluster_region_hint[a.id])
                region_b = regions_by_id.get(cluster_region_hint[b.id])
                if region_a is None or region_b is None:
                    continue
                related = (
                    cluster_region_hint[a.id] == cluster_region_hint[b.id]
                    or region_a.parent_id == cluster_region_hint[b.id]
                    or region_b.parent_id == cluster_region_hint[a.id]
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

                if distance is None:
                    continue
                if distance != distance:  # NaN check: a pgvector distance is
                    # NaN when either side's averaged embedding involves a
                    # zero-norm vector. list.sort() does not raise on NaN --
                    # it silently corrupts ordering (NaN comparisons are
                    # neither less-than nor greater-than), which can drag
                    # otherwise-valid entries out of order too. Drop these
                    # before sorting rather than let them through.
                    nan_count += 1
                    continue
                pairs.append((distance, a.id, a.title, b.id, b.title))

        pairs.sort()
        for distance, id_a, title_a, id_b, title_b in pairs:
            print(f"{distance:.4f}  cluster {id_a} ({title_a!r})  <->  cluster {id_b} ({title_b!r})")

        if nan_count:
            print(f"{nan_count} pairs skipped: NaN distance (likely zero-norm embeddings)")

        if not pairs:
            print("No region-related cluster pairs found -- run process_and_prioritize on real data first.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
