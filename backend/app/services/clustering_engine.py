import logging
from datetime import datetime, timedelta
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from app.models.models import CitizenReport, Expenditure, AdminRegion, IssueCluster, Priority, EvidenceBundle, NarrativeBrief, Indicator, AnalysisRun
from app.services.scoring_engine import scoring_engine
from app.services.gemini_service import gemini_service
from app.services.verifier import verification_engine
import json

logger = logging.getLogger(__name__)

# Sector -> the delivery-rate indicator_key that stands in for expenditure
# data when no Expenditure rows exist at all (Phase 13,
# docs/IMPLEMENTATION_PLAN.md). Real Karnataka data only carries this for
# water (docs/DECISIONS.md #1/#2 -- the pack deliberately went deep on one
# sector rather than wide across six); a sector with no entry here simply
# never triggers DELIVERY_GAP and falls through to the existing behavior.
SECTOR_DELIVERY_INDICATOR = {
    "water": "water.piped_household_pct",
}

# Time-windowed velocity thresholds for emerging-hotspot detection (F14,
# docs/superpowers/plans/2026-09-07-emerging-hotspot-detection.md). Flags a
# RATE change, not a total-volume threshold -- a cluster with 3 reports this
# week and 0 last week is worth surfacing even if a 40-report cluster still
# outranks it on raw score.
HOTSPOT_WINDOW_DAYS = 7
HOTSPOT_MIN_RECENT_REPORTS = 3
HOTSPOT_ACCELERATION_RATIO = 2.0


def _is_emerging_hotspot(reports: list, now: datetime, oldest_report_at) -> bool:
    """
    Flags a cluster whose complaint RATE is accelerating, not just large --
    a time-windowed comparison on report timestamps already collected, so a
    problem surfaces before it has accumulated enough total volume to
    already rank highly on score alone. Deterministic arithmetic, no model
    call, consistent with this project's model-free scoring philosophy.

    `now` and `oldest_report_at` are sourced from the database's own clock
    (Postgres `now()`/`MIN(reported_at)`), not the app process's
    datetime.utcnow() -- reported_at is written by Postgres via func.now(),
    and comparing it against a Python-clock timestamp is only safe if the
    two processes agree on timezone, which nothing in this deployment
    currently pins.

    `oldest_report_at` gates the zero-prior-reports branch: a cluster with
    no prior reports because the WHOLE DATASET has no history predating the
    window (a fresh deployment, a newly imported region) must not be
    indistinguishable from a genuinely new hotspot -- otherwise every
    cluster in a young dataset reads as "emerging."
    """
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
        # Only a real signal if the dataset itself has history predating the
        # window -- otherwise "no prior reports" just means "no data yet."
        return oldest_report_at is not None and oldest_report_at < recent_cutoff
    return (recent_count / prior_count) >= HOTSPOT_ACCELERATION_RATIO


class ClusteringEngine:
    """
    Handles PostGIS spatial clustering and pgvector semantic join logic to
    surface issue clusters, prioritize them, compile evidence, and generate briefs.
    """

    @staticmethod
    def process_and_prioritize(db: Session) -> None:
        logger.info("Starting spatial and semantic clustering pipeline...")
        try:
            # 1. Create a new AnalysisRun
            run = AnalysisRun(status="running")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id

            # Sourced from the database's own clock, once per run -- see
            # _is_emerging_hotspot's docstring for why this can't be
            # datetime.utcnow(). One query regardless of cluster count.
            hotspot_now, oldest_report_at = db.execute(
                text("SELECT now(), MIN(reported_at) FROM citizen_reports")
            ).first()

            # Phase 18: Re-attempt Gemini for pending_analysis reports
            logger.info("Retrying Gemini analysis for pending reports...")
            pending_reports = db.query(CitizenReport).filter(CitizenReport.status == "pending_analysis").all()
            for rep in pending_reports:
                try:
                    analysis = gemini_service.analyze_citizen_report(
                        text_content=rep.raw_text,
                        audio_bytes=None,
                        mime_type=None
                    )
                    english_translation = analysis.get("english_translation") or rep.raw_text or ""
                    embedding = gemini_service.get_embedding(english_translation)
                    
                    rep.english_translation = english_translation
                    rep.sector = analysis.get("sector", "unknown")
                    rep.specific_issue = analysis.get("specific_issue", "")
                    rep.urgency_score = analysis.get("urgency_score", 1.0)
                    rep.sentiment = analysis.get("sentiment", "neutral")
                    rep.detected_language = analysis.get("original_language", "unknown")
                    rep.embedding = embedding
                    
                    pii_redacted = analysis.get("pii_redacted_text", "")
                    if pii_redacted and pii_redacted != "[Audio - Failed to process]" and "Failed to analyze" not in analysis.get("specific_issue", ""):
                        rep.pii_redacted_text = pii_redacted
                        rep.raw_text = "Redacted"

                    location_text_latin = analysis.get("location_text_latin", "")
                    if location_text_latin and not rep.region_id:
                        from rapidfuzz import process, fuzz
                        from app.services.pack_loader import pack_loader
                        query = location_text_latin.strip().lower()
                        regions = db.query(AdminRegion).filter(AdminRegion.country_code == pack_loader.load_active_pack().country_code).all()
                        
                        match_region = None
                        for r in regions:
                            if r.name.strip().lower() == query:
                                match_region = r
                                break
                            if r.name_variants:
                                variants = [v.strip().lower() for v in r.name_variants.split('|')]
                                if query in variants:
                                    match_region = r
                                    break
                                    
                        if not match_region:
                            # Both sides lowercased before scoring -- see the
                            # matching fix and comment in location_resolver.py;
                            # this loop duplicates that logic (a sync Session
                            # here, an AsyncSession there) and had the same bug.
                            choices = []
                            region_map = {}
                            for r in regions:
                                names_to_match = [r.name]
                                if r.name_variants:
                                    names_to_match.extend(r.name_variants.split('|'))
                                for name in names_to_match:
                                    clean_name = name.strip()
                                    if clean_name:
                                        lowered = clean_name.lower()
                                        choices.append(lowered)
                                        region_map[lowered] = r

                            if choices:
                                match = process.extractOne(query, choices, scorer=fuzz.WRatio)
                                if match:
                                    best_str, score, index = match
                                    if score >= 85:
                                        match_region = region_map[best_str]
                                        
                        if match_region:
                            rep.region_id = match_region.id

                    rep.status = "complete"
                    db.add(rep)
                    db.commit()
                    logger.info(f"Successfully processed pending report {rep.id}")
                except Exception as e:
                    logger.error(f"Failed to process pending report {rep.id}: {e}")
                    db.rollback()

            # 2. Perform Spatial DBSCAN Clustering in PostGIS (eps = ~500m or 0.005 degrees)
            logger.info("Executing spatial clustering...")
            query = text("""
                SELECT id, ST_ClusterDBSCAN(location, eps := 0.005, minpoints := 1) OVER() as cluster_idx
                FROM citizen_reports
                WHERE location IS NOT NULL;
            """)
            result = db.execute(query).fetchall()

            cluster_map = {}
            for r_id, c_idx in result:
                if c_idx is not None:
                    cluster_map.setdefault(c_idx, []).append(r_id)

            # 2b. Reports resolved via the gazetteer (location_resolver.py sets
            # region_id from a place name) but with no raw GPS point never
            # enter the spatial DBSCAN query above -- it only looks at rows
            # WHERE location IS NOT NULL. Left as-is, every citizen who
            # reports by naming a place instead of sharing GPS (the normal
            # case for a Telegram/WhatsApp text or voice message) would be
            # correctly geocoded by Phase 9.3 and then silently vanish from
            # every cluster, priority, and dashboard entry. Group these by
            # (region_id, sector) instead -- the same key already used below
            # to match demand against expenditure records, so a cluster
            # formed this way still joins correctly with no further changes.
            next_cluster_idx = (max(cluster_map.keys()) + 1) if cluster_map else 0
            gazetteer_reports = db.query(CitizenReport).filter(
                CitizenReport.location.is_(None),
                CitizenReport.region_id.isnot(None),
            ).all()

            gazetteer_groups: dict[tuple, list[int]] = {}
            for r in gazetteer_reports:
                key = (r.region_id, r.sector)
                gazetteer_groups.setdefault(key, []).append(r.id)

            for report_ids in gazetteer_groups.values():
                cluster_map[next_cluster_idx] = report_ids
                next_cluster_idx += 1

            # Phase 12: Cross-Lingual Semantic Clustering (Split Logic Only)
            logger.info("Applying semantic split logic...")
            final_cluster_map = {}
            for c_idx, report_ids in cluster_map.items():
                if len(report_ids) < 2:
                    final_cluster_map[c_idx] = report_ids
                    continue
                
                split_query = text("""
                    WITH group_reports AS (
                        SELECT id, embedding
                        FROM citizen_reports
                        WHERE id IN :report_ids AND embedding IS NOT NULL
                    ),
                    centroid AS (
                        SELECT avg(embedding) as center
                        FROM group_reports
                    )
                    SELECT g.id, (g.embedding <=> c.center) as distance
                    FROM group_reports g, centroid c;
                """)
                
                rows = db.execute(split_query, {"report_ids": tuple(report_ids)}).fetchall()
                
                dist_map = {row.id: row.distance for row in rows if row.distance is not None}
                
                main_cluster_ids = []
                for r_id in report_ids:
                    dist = dist_map.get(r_id)
                    if dist is not None and dist > 0.35:
                        # Split out due to semantic distance
                        final_cluster_map[next_cluster_idx] = [r_id]
                        next_cluster_idx += 1
                    else:
                        main_cluster_ids.append(r_id)
                        
                if main_cluster_ids:
                    final_cluster_map[c_idx] = main_cluster_ids
                    
            cluster_map = final_cluster_map

            # Phase 2 (F5, continued): cross-bucket semantic merge. The split
            # loop above only prevents *over*-merging inside a bucket that
            # bucketing already put together; it never lets two buckets that
            # got separated by resolution noise -- a different sector tag, a
            # neighboring ward, or one path via GPS DBSCAN and the other via
            # the gazetteer -- rejoin, even when they're the same real-world
            # report. Provisional threshold -- run against the real database
            # via backend/scripts/calibrate_merge_threshold.py on 2026-08-30:
            # of 56 clusters, only the most recent process_and_prioritize run's
            # 7 clusters still had reports attached, yielding 4 region-related
            # pairs, and 16 of the 24 embedded reports in this database turned
            # out to have zero-norm (broken/placeholder) embedding vectors,
            # which makes cosine distance undefined (NaN) for any pair
            # touching them -- 3 of the 4 pairs were unusable for that reason.
            # The one usable pair (water vs. electricity, same region) measured
            # 0.1669 -- a different-sector pair, not a genuine duplicate -- only
            # 0.017 above the previous 0.15 threshold. That margin is too thin
            # to trust: this merge pass compares centroid-averaged embeddings
            # (avg(embedding) per cluster), and averaging cancels per-report
            # variance that would otherwise push distances further apart, so
            # centroid distances are compressed relative to the report-level
            # distances (~0.12 same-issue / ~0.42 unrelated) that originally
            # justified numbers in this range. A false non-merge just leaves
            # two clusters instead of one -- the pre-merge status quo. A false
            # merge combines two distinct real issues into one evidence bundle
            # and one policy brief a policymaker reads -- the wrong direction
            # to be wrong in. Tightened to 0.10 as the conservative choice
            # until a genuine same-issue duplicate pair exists in real data to
            # anchor the low end; re-run the script once region-related
            # duplicate reports exist in production.
            logger.info("Applying cross-bucket semantic merge...")
            MERGE_DISTANCE_THRESHOLD = 0.10

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

            # 3. Create Issue Clusters
            for c_idx, report_ids in cluster_map.items():
                reports = db.query(CitizenReport).filter(CitizenReport.id.in_(report_ids)).all()
                if not reports:
                    continue

                # Determine dominant sector and average coordinates
                sectors = [r.sector for r in reports]
                # Tie-break alphabetically: the cross-bucket merge pass above
                # makes exact sector-count ties routine (it specifically joins
                # buckets with different sector tags), and plain `set`
                # iteration order over strings is not guaranteed stable across
                # process runs. dominant_sector drives the expenditure join and
                # the DELIVERY_GAP indicator lookup below, so an unstable tie
                # could flip a fiscal-gap figure between two runs of identical
                # data -- deterministic tie-break keeps every figure traceable
                # to a single, reproducible source.
                dominant_sector = max(set(sectors), key=lambda s: (sectors.count(s), s))
                
                # Fetch spatial centroid
                centroid_query = text("""
                    SELECT ST_AsText(ST_Centroid(ST_Collect(location)))
                    FROM citizen_reports
                    WHERE id IN :ids;
                """)
                centroid_wkt = db.execute(centroid_query, {"ids": tuple(report_ids)}).scalar()

                # Find the admin region this cluster actually belongs to.
                #
                # The previous query was unreachable: it nested a bare SELECT
                # inside ST_Collect(...), which is not valid SQL and would
                # raise if it ever ran. Because it never ran, execution always
                # fell through to ".filter(level=='ward').first()' -- so every
                # cluster, in every sector, everywhere in the state, was
                # attributed to the same single ward. Expenditures are matched
                # by region_id + sector below, so this did not just mislabel
                # the map -- it broke the join itself for all but one region.
                #
                # Fixed as a real spatial query: prefer the ward whose polygon
                # contains the cluster centroid, and fall back to the nearest
                # ward by distance when no polygon contains it (a centroid can
                # legitimately sit outside every seeded boundary).
                # clustering_engine.py's region-attribution step now prefers
                # citizen_reports.region_id when the resolver already set it, and
                # only falls back to the spatial query for reports that arrived
                # with a raw GPS point and no resolvable place name.
                region_ids = [r.region_id for r in reports if r.region_id]
                region = None
                
                if region_ids:
                    dominant_region_id = max(set(region_ids), key=region_ids.count)
                    region = db.query(AdminRegion).get(dominant_region_id)

                if region is None and centroid_wkt:
                    region_query = text("""
                        SELECT id FROM admin_regions
                        WHERE level = 'ward' AND geom IS NOT NULL
                        ORDER BY
                            ST_Contains(geom, ST_GeomFromText(:centroid, 4326)) DESC,
                            ST_Distance(geom, ST_GeomFromText(:centroid, 4326)) ASC
                        LIMIT 1;
                    """)
                    row = db.execute(region_query, {"centroid": centroid_wkt}).first()
                    if row:
                        region = db.query(AdminRegion).get(row[0])

                if region is None:
                    logger.warning(
                        "Cluster %s: no ward geometry matched centroid %r; "
                        "falling back to the first ward. Region attribution "
                        "for this cluster is unreliable.", c_idx, centroid_wkt,
                    )
                    region = db.query(AdminRegion).filter(AdminRegion.level == "ward").first()
                region_id = region.id if region else 1

                final_centroid = centroid_wkt
                is_approximate = False
                
                if not final_centroid and region:
                    if region.centroid is not None:
                        final_centroid = region.centroid
                        is_approximate = True
                    elif region.parent_id is not None:
                        parent = db.query(AdminRegion).get(region.parent_id)
                        if parent and parent.centroid is not None:
                            final_centroid = parent.centroid
                            is_approximate = True

                cluster = IssueCluster(
                    title=f"Cluster of {len(reports)} {dominant_sector} reports",
                    sector=dominant_sector,
                    region_id=region_id,
                    centroid=final_centroid,
                    is_approximate_location=is_approximate,
                    report_count=len(reports),
                    run_id=run_id
                )
                db.add(cluster)
                db.flush()

                # Link reports to cluster
                for r in reports:
                    r.cluster_id = cluster.id
                    db.add(r)
                db.commit()

                # 4. Semantic Join: Find related expenditures (same sector, same region)
                # We can also use pgvector cosine distance: embedding <=> query_embedding
                # Let's find expenditures in the same region & sector
                expenditures = db.query(Expenditure).filter(
                    Expenditure.region_id == region_id,
                    Expenditure.sector == dominant_sector
                ).all()

                allocated_budget = sum([e.amount for e in expenditures])
                stalled_status = any([e.status == "stalled" for e in expenditures])
                estimated_cost = len(reports) * 1500000.0  # Assumed cost factor per report (15 Lakhs INR)
                avg_urgency = sum([r.urgency_score for r in reports]) / len(reports)

                # Fetch regional vulnerability index indicator
                vuln_ind = db.query(Indicator).filter(
                    Indicator.region_id == region_id,
                    Indicator.indicator_key == "vulnerability_index"
                ).first()
                vulnerability_val = vuln_ind.numeric_value if vuln_ind else None

                # Delivery-rate signal for DELIVERY_GAP (Phase 13): only
                # meaningful when both this region and its own parent have a
                # value for the same indicator -- e.g. a block's own % piped
                # households vs. its district's. Absent for any sector not in
                # SECTOR_DELIVERY_INDICATOR, or when either row is missing.
                delivery_rate = None
                delivery_reference = None
                delivery_indicator_key = SECTOR_DELIVERY_INDICATOR.get(dominant_sector)
                if delivery_indicator_key and region and region.parent_id:
                    region_ind = db.query(Indicator).filter(
                        Indicator.region_id == region.id,
                        Indicator.indicator_key == delivery_indicator_key
                    ).first()
                    parent_ind = db.query(Indicator).filter(
                        Indicator.region_id == region.parent_id,
                        Indicator.indicator_key == delivery_indicator_key
                    ).first()
                    if region_ind and parent_ind:
                        delivery_rate = region_ind.numeric_value
                        delivery_reference = parent_ind.numeric_value

                # Calculate max reports count in region for normalization
                max_reports_in_region = db.query(func.max(IssueCluster.report_count)).scalar() or len(reports)

                # Distinct reporters: count each channel identity once, so 500
                # messages from one person cannot manufacture a hotspot.
                # reporter_hash is nullable during migration -- reports without
                # one fall back to being counted individually, same as before,
                # rather than silently vanishing from the total.
                distinct_reporters = len({
                    r.reporter_hash for r in reports if r.reporter_hash
                } | {
                    f"unhashed-{r.id}" for r in reports if not r.reporter_hash
                })

                # Calculate Priority Score & Verdict
                score_details = scoring_engine.calculate_priority_score(
                    report_count=len(reports),
                    max_reports_in_region=max_reports_in_region,
                    vulnerability_index=vulnerability_val,
                    allocated_budget=allocated_budget,
                    estimated_cost=estimated_cost,
                    stalled_status=stalled_status,
                    average_urgency=avg_urgency,
                    distinct_reporters=distinct_reporters,
                    population=region.population if region else None,
                    # No pack-wide reference intensity yet -- that needs a
                    # pass over every cluster in the run, which belongs in the
                    # nightly batch job, not per-cluster here. Until then the
                    # scoring engine's documented per-cluster fallback applies.
                    delivery_rate=delivery_rate,
                    delivery_reference=delivery_reference,
                )
                score_details["is_emerging_hotspot"] = _is_emerging_hotspot(reports, hotspot_now, oldest_report_at)

                fully_funded = allocated_budget >= estimated_cost
                if len(reports) < 3 and not stalled_status and not fully_funded:
                    list_type = "audit"
                else:
                    list_type = "fund"

                priority = Priority(
                    cluster_id=cluster.id,
                    score=score_details["score"],
                    verdict=score_details["verdict"],
                    list=list_type,
                    details=score_details,
                    run_id=run_id
                )
                db.add(priority)
                db.flush()

                # 6. Build Evidence Bundle JSON
                evidence = {
                    "cluster_id": cluster.id,
                    "title": cluster.title,
                    "sector": cluster.sector,
                    "report_count": len(reports),
                    "average_urgency": round(avg_urgency, 2),
                    "vulnerability_index": vulnerability_val,
                    "allocated_budget": allocated_budget,
                    "estimated_cost": estimated_cost,
                    "budget_stalled": stalled_status,
                    "delivery_rate": delivery_rate,
                    "delivery_reference": delivery_reference,
                    "delivery_indicator_key": delivery_indicator_key,
                    "expenditure_records": [
                        {"title": e.title, "amount": e.amount, "status": e.status}
                        for e in expenditures
                    ],
                    # pii_redacted_text, not english_translation -- the evidence
                    # bundle is persisted, shown directly in the frontend's
                    # evidence drawer, and fed into Gemini's Call 3 as source
                    # material for the policy brief. english_translation is
                    # Gemini's full, unredacted translation; quoting it here
                    # would let a citizen's name/phone/address flow straight
                    # into a document a policymaker reads and an AI model cites.
                    "citizen_quotes": [r.pii_redacted_text or r.english_translation for r in reports[:3]]
                }

                eb = EvidenceBundle(
                    priority_id=priority.id,
                    data=evidence,
                    run_id=run_id
                )
                db.add(eb)
                db.flush()

                # 7. Call Gemini for Grounded Policy Brief with Programmatic Verification
                logger.info(f"Generating policy brief for cluster {cluster.id}...")
                brief_data = gemini_service.generate_policy_brief(evidence)
                
                # Check verification
                verify_res = verification_engine.verify_brief(
                    f"{brief_data['summary']} {brief_data['why_prioritized']} {brief_data['fiscal_gap_analysis']} {brief_data['recommended_action']}",
                    evidence
                )
                
                if not verify_res["verified"]:
                    logger.warning(f"Brief failed verification (unverified numbers: {verify_res['unverified_numbers']}). Regenerating...")
                    # Redo once with strict instruction
                    evidence["STRICT_INSTRUCTION"] = "Only output numbers exactly present in this JSON."
                    brief_data = gemini_service.generate_policy_brief(evidence)

                nb = NarrativeBrief(
                    priority_id=priority.id,
                    summary=brief_data["summary"],
                    why_prioritized=brief_data["why_prioritized"],
                    fiscal_gap_analysis=brief_data["fiscal_gap_analysis"],
                    recommended_action=brief_data["recommended_action"],
                    run_id=run_id
                )
                db.add(nb)
                db.commit()

            # 8. Mark run as complete
            run.status = "complete"
            run.completed_at = func.now()
            db.add(run)
            db.commit()

            logger.info("Pipeline processing completed successfully!")
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            db.rollback()
            try:
                # Need to use a new transaction/session to update run if rollback happened, 
                # but run object might be detached. So we re-fetch or just execute an update.
                db.execute(text("UPDATE analysis_runs SET status = 'failed' WHERE id = :run_id"), {"run_id": run_id})
                db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to update run status to failed: {inner_e}")
            raise

clustering_engine = ClusteringEngine()
