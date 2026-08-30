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
