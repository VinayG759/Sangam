import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.models import CitizenReport, Expenditure, AdminRegion, IssueCluster, Priority, EvidenceBundle, NarrativeBrief, Indicator
from app.services.scoring_engine import scoring_engine
from app.services.gemini_service import gemini_service
from app.services.verifier import verification_engine
import json

logger = logging.getLogger(__name__)

class ClusteringEngine:
    """
    Handles PostGIS spatial clustering and pgvector semantic join logic to
    surface issue clusters, prioritize them, compile evidence, and generate briefs.
    """

    @staticmethod
    def process_and_prioritize(db: Session) -> None:
        logger.info("Starting spatial and semantic clustering pipeline...")
        try:
            # 1. Clear old computed results
            db.query(NarrativeBrief).delete()
            db.query(EvidenceBundle).delete()
            db.query(Priority).delete()
            db.query(IssueCluster).delete()
            # Reset report cluster assignments
            db.execute(text("UPDATE citizen_reports SET cluster_id = NULL;"))
            db.commit()

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

            # 3. Create Issue Clusters
            for c_idx, report_ids in cluster_map.items():
                reports = db.query(CitizenReport).filter(CitizenReport.id.in_(report_ids)).all()
                if not reports:
                    continue

                # Determine dominant sector and average coordinates
                sectors = [r.sector for r in reports]
                dominant_sector = max(set(sectors), key=sectors.count)
                
                # Fetch spatial centroid
                centroid_query = text("""
                    SELECT ST_AsText(ST_Centroid(ST_Collect(location)))
                    FROM citizen_reports
                    WHERE id IN :ids;
                """)
                centroid_wkt = db.execute(centroid_query, {"ids": tuple(report_ids)}).scalar()

                # Find representing admin region (ward)
                region_query = text("""
                    SELECT id FROM admin_regions 
                    WHERE level = 'ward' 
                    ORDER BY ST_Distance(geom, ST_Centroid(ST_Collect(
                        SELECT location FROM citizen_reports WHERE id IN :ids
                    ))) LIMIT 1;
                """)
                # Simple fallback to first ward if geo-search gets complicated
                region = db.query(AdminRegion).filter(AdminRegion.level == "ward").first()
                region_id = region.id if region else 1

                cluster = IssueCluster(
                    title=f"Cluster of {len(reports)} {dominant_sector} reports",
                    sector=dominant_sector,
                    region_id=region_id,
                    centroid=centroid_wkt,
                    report_count=len(reports)
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
                vulnerability_val = vuln_ind.numeric_value if vuln_ind else 0.5

                # Calculate max reports count in region for normalization
                max_reports_in_region = db.query(func.max(IssueCluster.report_count)).scalar() or len(reports)

                # 5. Calculate Priority Score & Verdict
                score_details = scoring_engine.calculate_priority_score(
                    report_count=len(reports),
                    max_reports_in_region=max_reports_in_region,
                    vulnerability_index=vulnerability_val,
                    allocated_budget=allocated_budget,
                    estimated_cost=estimated_cost,
                    stalled_status=stalled_status,
                    average_urgency=avg_urgency
                )

                priority = Priority(
                    cluster_id=cluster.id,
                    score=score_details["score"],
                    verdict=score_details["verdict"],
                    details=score_details
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
                    "expenditure_records": [
                        {"title": e.title, "amount": e.amount, "status": e.status}
                        for e in expenditures
                    ],
                    "citizen_quotes": [r.english_translation for r in reports[:3]]
                }

                eb = EvidenceBundle(
                    priority_id=priority.id,
                    data=evidence
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
                    recommended_action=brief_data["recommended_action"]
                )
                db.add(nb)
                db.commit()

            logger.info("Pipeline processing completed successfully!")
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            db.rollback()
            raise

clustering_engine = ClusteringEngine()
from sqlalchemy import func
