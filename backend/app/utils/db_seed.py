import logging
import os
from sqlalchemy.orm import Session
from app.db import SessionLocal, engine
from app.models.models import (
    AdminRegion, AnalysisRun, CitizenReport, EvidenceBundle, Expenditure,
    Indicator, IssueCluster, NarrativeBrief, Priority,
)
from app.services.gemini_service import gemini_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealDataPresentError(RuntimeError):
    """Refusing to overwrite real citizen data with the demo seed."""


def seed_data():
    logger.info("Seeding database...")
    db = SessionLocal()
    try:
        # 0. Refuse to clobber real citizen data. tracking_id is only ever
        # set by ingestion_service.ingest_citizen_message (the real web/
        # Telegram/WhatsApp intake path) -- this script never sets it. Its
        # presence means at least one row is a real citizen's report, not
        # demo data, and the delete-everything step below would destroy it
        # permanently. The documented flow (docker-entrypoint.sh) runs this
        # seed BEFORE load_real_data.py on a fresh database, so no real
        # reports exist yet and this check passes through silently; it only
        # ever fires on a database that already has real citizen activity.
        real_report_count = db.query(CitizenReport).filter(
            CitizenReport.tracking_id.isnot(None)
        ).count()
        if real_report_count > 0 and os.environ.get("FORCE_RESEED") != "true":
            raise RealDataPresentError(
                f"Refusing to seed: {real_report_count} citizen_reports row(s) already have "
                "a tracking_id, meaning they came from a real citizen, not this demo script. "
                "Seeding deletes every row in citizen_reports, expenditures, indicators, and "
                "admin_regions -- that would permanently destroy real citizen submissions. "
                "If this is a demo environment you are intentionally resetting, set "
                "FORCE_RESEED=true and re-run."
            )

        # 1. Clean existing data, children before parents (FK order). A prior
        # /reprocess run leaves issue_clusters/priorities/etc. referencing
        # admin_regions -- deleting admin_regions first, as this used to do,
        # hits a ForeignKeyViolation on any database that has ever run the
        # clustering pipeline once. Reseeding raw data while leaving that
        # derived data behind is incoherent anyway (it would reference
        # regions that no longer exist post-reseed), so clear all of it.
        logger.info("Clearing old tables...")
        db.query(NarrativeBrief).delete()
        db.query(EvidenceBundle).delete()
        db.query(Priority).delete()
        db.query(IssueCluster).delete()
        db.query(AnalysisRun).delete()
        db.query(Indicator).delete()
        db.query(Expenditure).delete()
        db.query(CitizenReport).delete()
        db.query(AdminRegion).delete()
        db.commit()

        # 2. Seed Admin Regions (Karnataka Hierarchy)
        logger.info("Seeding Admin Regions...")
        karnataka = AdminRegion(
            country_code="IND",
            name="Karnataka",
            level="state",
            population=61_095_297,  # Census 2011, illustrative for this seed path
            geom="SRID=4326;POLYGON((74.0 11.5, 78.5 11.5, 78.5 18.5, 74.0 18.5, 74.0 11.5))"
        )
        db.add(karnataka)
        db.flush()  # to get karnataka.id

        bengaluru = AdminRegion(
            country_code="IND",
            name="Bengaluru",
            level="district",
            population=9_621_551,  # illustrative
            parent_id=karnataka.id,
            geom="SRID=4326;POLYGON((77.3 12.8, 77.8 12.8, 77.8 13.2, 77.3 13.2, 77.3 12.8))"
        )
        db.add(bengaluru)
        db.flush()

        # Seed 3 Wards
        koramangala = AdminRegion(
            country_code="IND",
            name="Koramangala Ward",
            level="ward",
            population=45_000,  # illustrative demo figure
            parent_id=bengaluru.id,
            geom="SRID=4326;POLYGON((77.61 12.92, 77.64 12.92, 77.64 12.95, 77.61 12.95, 77.61 12.92))"
        )
        indiranagar = AdminRegion(
            country_code="IND",
            name="Indiranagar Ward",
            level="ward",
            population=38_000,  # illustrative demo figure
            parent_id=bengaluru.id,
            geom="SRID=4326;POLYGON((77.62 12.96, 77.66 12.96, 77.66 12.99, 77.62 12.99, 77.62 12.96))"
        )
        hsr_layout = AdminRegion(
            country_code="IND",
            name="HSR Layout Ward",
            level="ward",
            population=52_000,  # illustrative demo figure
            parent_id=bengaluru.id,
            geom="SRID=4326;POLYGON((77.62 12.88, 77.66 12.88, 77.66 12.92, 77.62 12.92, 77.62 12.88))"
        )
        db.add_all([koramangala, indiranagar, hsr_layout])
        db.flush()

        # 3. Seed Indicators (Tall Table Schema)
        logger.info("Seeding region socio-economic indicators...")
        indicators_data = [
            # Koramangala
            Indicator(region_id=koramangala.id, indicator_key="vulnerability_index", numeric_value=0.25, source_year=2025),
            Indicator(region_id=koramangala.id, indicator_key="population_density", numeric_value=8500.0, source_year=2025),
            # Indiranagar
            Indicator(region_id=indiranagar.id, indicator_key="vulnerability_index", numeric_value=0.30, source_year=2025),
            Indicator(region_id=indiranagar.id, indicator_key="population_density", numeric_value=9200.0, source_year=2025),
            # HSR Layout
            Indicator(region_id=hsr_layout.id, indicator_key="vulnerability_index", numeric_value=0.45, source_year=2025), # higher vulnerability
            Indicator(region_id=hsr_layout.id, indicator_key="population_density", numeric_value=11000.0, source_year=2025),
        ]
        db.add_all(indicators_data)

        # 4. Seed Public Expenditure Records
        logger.info("Seeding Public Expenditures...")
        expenditures_data = [
            # Koramangala: Sanctioned road potholes filling but execution is stalled
            Expenditure(
                title="Pothole Remediation & Asphalt Overlays - Koramangala 80 Feet Rd",
                description="Sanctioned budget for patching potholes and laying fresh asphalt overlay on the main arterial corridor.",
                sector="roads",
                amount=4500000.0,  # 45 Lakhs INR
                allocated_year=2025,
                status="stalled",  # STALLED ALLOCATION
                location="SRID=4326;POINT(77.6234 12.9351)",
                region_id=koramangala.id
            ),
            # HSR Layout: Completed sanitation project
            Expenditure(
                title="Borewell Water Treatment & RO Plant Setup Sector 3",
                description="Installation and commissioning of RO water plant to provide clean drinking water to low income areas.",
                sector="water",
                amount=2500000.0,  # 25 Lakhs
                allocated_year=2025,
                status="completed",
                location="SRID=4326;POINT(77.6385 12.9056)",
                region_id=hsr_layout.id
            ),
            # Indiranagar: Underfunded road work
            Expenditure(
                title="Arterial Street Lighting & Drainage Repair - Indiranagar 100 Feet Rd",
                description="Small allocation for street lights; does not cover major water main repairs or roads.",
                sector="roads",
                amount=1200000.0,  # 12 Lakhs (highly underfunded compared to road damage)
                allocated_year=2025,
                status="in_progress",
                location="SRID=4326;POINT(77.6412 12.9784)",
                region_id=indiranagar.id
            )
        ]
        db.add_all(expenditures_data)

        # 5. Seed Multilingual Citizen Reports
        logger.info("Seeding Citizen Reports...")
        reports_data = [
            # Koramangala: Potholes (Stalled allocation because budget was allocated but potholes are still reported!)
            CitizenReport(
                raw_text="ಕೋರಮಂಗಲ ೮೦ ಅಡಿ ರಸ್ತೆಯಲ್ಲಿ ಭಾರಿ ಗುಂಡಿಗಳಿವೆ. ದ್ವಿಚಕ್ರ ವಾಹನ ಸವಾರರು ಬಿದ್ದು ಗಾಯಗೊಳ್ಳುತ್ತಿದ್ದಾರೆ. ಯಾರೂ ಗಮನಹರಿಸುತ್ತಿಲ್ಲ.",
                detected_language="kn",
                english_translation="There are huge potholes on Koramangala 80 Feet Road. Two-wheeler riders are falling and getting injured. No one is paying attention.",
                sector="roads",
                specific_issue="Dangerous potholes on main road",
                urgency_score=4.5,
                sentiment="negative",
                location="SRID=4326;POINT(77.6241 12.9358)",
                reporter_hash="seed-citizen-001"),
            CitizenReport(
                raw_text="The potholes on Koramangala 80 feet road are getting worse everyday. Commuting has become a nightmare.",
                detected_language="en",
                english_translation="The potholes on Koramangala 80 feet road are getting worse everyday. Commuting has become a nightmare.",
                sector="roads",
                specific_issue="Severe road damage and potholes",
                urgency_score=4.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6228 12.9345)",
                reporter_hash="seed-citizen-002"),

            # Indiranagar: Water crisis (Unserved gap because there is zero budget for water sector in Indiranagar)
            CitizenReport(
                raw_text="इन्दिरानगर में पिछले 10 दिनों से पीने का पानी नहीं आ रहा है। कृपया पानी की समस्या को हल करें।",
                detected_language="hi",
                english_translation="There is no drinking water in Indiranagar for the last 10 days. Please resolve the water issue.",
                sector="water",
                specific_issue="Total lack of drinking water supply",
                urgency_score=5.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6405 12.9792)",
                reporter_hash="seed-citizen-003"),
            CitizenReport(
                raw_text="Drinking water pipe leakage has resulted in zero water pressure. No water for our daily chores in Indiranagar.",
                detected_language="en",
                english_translation="Drinking water pipe leakage has resulted in zero water pressure. No water for our daily chores in Indiranagar.",
                sector="water",
                specific_issue="Pipeline leak causing supply failure",
                urgency_score=3.5,
                sentiment="negative",
                location="SRID=4326;POINT(77.6421 12.9770)",
                reporter_hash="seed-citizen-004"),

            # HSR Layout: Waste pile reports
            CitizenReport(
                raw_text="HSR layout sector 3 garbage pile is not cleared. Very bad smell and mosquito breeding.",
                detected_language="en",
                english_translation="HSR layout sector 3 garbage pile is not cleared. Very bad smell and mosquito breeding.",
                sector="sanitation",
                specific_issue="Uncleared waste heap and disease vector risk",
                urgency_score=3.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6391 12.9062)",
                reporter_hash="seed-citizen-005"),

            # ── Additional reporters per cluster ──────────────────────────
            # scoring_engine.py's aggregation floor (docs/DECISIONS.md #9)
            # hides any cluster with fewer than min_distinct_reporters (5 by
            # default) behind a WELL_SERVED verdict, regardless of the real
            # gap -- a real privacy protection, not a bug. The two reports
            # per scenario above predate that floor and can never clear it,
            # so no demo cluster could ever show its real verdict. These
            # extra distinct reporters (still just 2 issues, more people
            # experiencing each) bring every scenario up to 5+ so the floor
            # passes them through instead of suppressing them.
            CitizenReport(
                raw_text="Same pothole issue on Koramangala 80 feet road, my scooter got damaged again this week.",
                detected_language="en",
                english_translation="Same pothole issue on Koramangala 80 feet road, my scooter got damaged again this week.",
                sector="roads",
                specific_issue="Vehicle damage from unrepaired potholes",
                urgency_score=4.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6236 12.9349)",
                reporter_hash="seed-citizen-006"),
            CitizenReport(
                raw_text="ಕೋರಮಂಗಲದಲ್ಲಿ ರಸ್ತೆ ದುರಸ್ತಿ ಕೆಲಸ ಪ್ರಾರಂಭವಾಗಿಲ್ಲ. ಗುಂಡಿಗಳು ಹಾಗೆಯೇ ಇವೆ.",
                detected_language="kn",
                english_translation="Road repair work has not started in Koramangala. The potholes are still there.",
                sector="roads",
                specific_issue="Sanctioned repair work never began",
                urgency_score=4.2,
                sentiment="negative",
                location="SRID=4326;POINT(77.6245 12.9362)",
                reporter_hash="seed-citizen-007"),
            CitizenReport(
                raw_text="It has been months and the Koramangala road contractor has not returned to finish the asphalt work.",
                detected_language="en",
                english_translation="It has been months and the Koramangala road contractor has not returned to finish the asphalt work.",
                sector="roads",
                specific_issue="Stalled contractor work on sanctioned repair",
                urgency_score=3.8,
                sentiment="negative",
                location="SRID=4326;POINT(77.6220 12.9340)",
                reporter_hash="seed-citizen-008"),

            CitizenReport(
                raw_text="इंदिरानगर में पानी की सप्लाई अब भी बंद है। बच्चों के लिए पानी लाना मुश्किल हो गया है।",
                detected_language="hi",
                english_translation="Water supply in Indiranagar is still cut off. It has become difficult to fetch water for the children.",
                sector="water",
                specific_issue="Continued lack of drinking water supply",
                urgency_score=4.8,
                sentiment="negative",
                location="SRID=4326;POINT(77.6398 12.9788)",
                reporter_hash="seed-citizen-009"),
            CitizenReport(
                raw_text="No municipal water tanker has come to Indiranagar in over a week. We are buying bottled water for cooking.",
                detected_language="en",
                english_translation="No municipal water tanker has come to Indiranagar in over a week. We are buying bottled water for cooking.",
                sector="water",
                specific_issue="No tanker supply, no piped water",
                urgency_score=4.6,
                sentiment="negative",
                location="SRID=4326;POINT(77.6415 12.9779)",
                reporter_hash="seed-citizen-010"),
            CitizenReport(
                raw_text="Elderly residents in Indiranagar are struggling without any water connection for daily use.",
                detected_language="en",
                english_translation="Elderly residents in Indiranagar are struggling without any water connection for daily use.",
                sector="water",
                specific_issue="Vulnerable residents affected by water shortage",
                urgency_score=4.9,
                sentiment="negative",
                location="SRID=4326;POINT(77.6409 12.9765)",
                reporter_hash="seed-citizen-011"),

            CitizenReport(
                raw_text="HSR ಲೇಔಟ್ ಸೆಕ್ಟರ್ 3ರಲ್ಲಿ ಕಸ ಇನ್ನೂ ತೆಗೆದಿಲ್ಲ, ಸೊಳ್ಳೆ ಕಾಟ ಜಾಸ್ತಿಯಾಗಿದೆ.",
                detected_language="kn",
                english_translation="The garbage in HSR Layout sector 3 still hasn't been cleared, mosquito problems have increased.",
                sector="sanitation",
                specific_issue="Uncleared waste heap, rising mosquito risk",
                urgency_score=3.2,
                sentiment="negative",
                location="SRID=4326;POINT(77.6388 12.9058)",
                reporter_hash="seed-citizen-012"),
            CitizenReport(
                raw_text="The garbage collection truck has skipped HSR Layout sector 3 for the third time this month.",
                detected_language="en",
                english_translation="The garbage collection truck has skipped HSR Layout sector 3 for the third time this month.",
                sector="sanitation",
                specific_issue="Missed garbage collection rounds",
                urgency_score=2.8,
                sentiment="negative",
                location="SRID=4326;POINT(77.6395 12.9070)",
                reporter_hash="seed-citizen-013"),
            CitizenReport(
                raw_text="Children playing near the uncleared garbage pile in HSR sector 3 is a genuine health hazard now.",
                detected_language="en",
                english_translation="Children playing near the uncleared garbage pile in HSR sector 3 is a genuine health hazard now.",
                sector="sanitation",
                specific_issue="Health hazard from uncleared waste near children",
                urgency_score=3.6,
                sentiment="negative",
                location="SRID=4326;POINT(77.6383 12.9068)",
                reporter_hash="seed-citizen-014"),
            CitizenReport(
                raw_text="ಈ ಕಸದ ರಾಶಿ ಒಂದು ತಿಂಗಳಿಂದ ಹಾಗೆಯೇ ಇದೆ, ಪಾಲಿಕೆಗೆ ದೂರು ಕೊಟ್ಟರೂ ಪ್ರಯೋಜನವಿಲ್ಲ.",
                detected_language="kn",
                english_translation="This garbage heap has been sitting here for a month, complaining to the municipal corporation hasn't helped.",
                sector="sanitation",
                specific_issue="Complaint filed with no municipal response",
                urgency_score=3.4,
                sentiment="negative",
                location="SRID=4326;POINT(77.6392 12.9055)",
                reporter_hash="seed-citizen-015")
        ]
        
        # Populate embeddings asynchronously using GeminiService if API key is provided
        logger.info("Generating semantic embeddings for reports and expenditures...")
        for r in reports_data:
            r.embedding = gemini_service.get_embedding(r.english_translation)
            db.add(r)
        
        db.commit()
        
        # Update expenditure embeddings as well
        logger.info("Generating embeddings for expenditures...")
        for exp in db.query(Expenditure).all():
            exp.embedding = gemini_service.get_embedding(f"{exp.title}. {exp.description}")
            db.add(exp)
        
        db.commit()
        logger.info("Database seeded successfully with realistic multilingual data!")

    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
