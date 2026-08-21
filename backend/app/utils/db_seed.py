import logging
from sqlalchemy.orm import Session
from app.db import SessionLocal, engine
from app.models.models import AdminRegion, CitizenReport, Expenditure, Indicator
from app.services.gemini_service import gemini_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_data():
    logger.info("Seeding database...")
    db = SessionLocal()
    try:
        # 1. Clean existing data
        logger.info("Clearing old tables...")
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
            geom="SRID=4326;POLYGON((74.0 11.5, 78.5 11.5, 78.5 18.5, 74.0 18.5, 74.0 11.5))"
        )
        db.add(karnataka)
        db.flush()  # to get karnataka.id

        bengaluru = AdminRegion(
            country_code="IND",
            name="Bengaluru",
            level="district",
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
            parent_id=bengaluru.id,
            geom="SRID=4326;POLYGON((77.61 12.92, 77.64 12.92, 77.64 12.95, 77.61 12.95, 77.61 12.92))"
        )
        indiranagar = AdminRegion(
            country_code="IND",
            name="Indiranagar Ward",
            level="ward",
            parent_id=bengaluru.id,
            geom="SRID=4326;POLYGON((77.62 12.96, 77.66 12.96, 77.66 12.99, 77.62 12.99, 77.62 12.96))"
        )
        hsr_layout = AdminRegion(
            country_code="IND",
            name="HSR Layout Ward",
            level="ward",
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
                location="SRID=4326;POINT(77.6241 12.9358)"
            ),
            CitizenReport(
                raw_text="The potholes on Koramangala 80 feet road are getting worse everyday. Commuting has become a nightmare.",
                detected_language="en",
                english_translation="The potholes on Koramangala 80 feet road are getting worse everyday. Commuting has become a nightmare.",
                sector="roads",
                specific_issue="Severe road damage and potholes",
                urgency_score=4.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6228 12.9345)"
            ),

            # Indiranagar: Water crisis (Unserved gap because there is zero budget for water sector in Indiranagar)
            CitizenReport(
                raw_text="इन्दिरानगर में पिछले 10 दिनों से पीने का पानी नहीं आ रहा है। कृपया पानी की समस्या को हल करें।",
                detected_language="hi",
                english_translation="There is no drinking water in Indiranagar for the last 10 days. Please resolve the water issue.",
                sector="water",
                specific_issue="Total lack of drinking water supply",
                urgency_score=5.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6405 12.9792)"
            ),
            CitizenReport(
                raw_text="Drinking water pipe leakage has resulted in zero water pressure. No water for our daily chores in Indiranagar.",
                detected_language="en",
                english_translation="Drinking water pipe leakage has resulted in zero water pressure. No water for our daily chores in Indiranagar.",
                sector="water",
                specific_issue="Pipeline leak causing supply failure",
                urgency_score=3.5,
                sentiment="negative",
                location="SRID=4326;POINT(77.6421 12.9770)"
            ),

            # HSR Layout: Waste pile reports
            CitizenReport(
                raw_text="HSR layout sector 3 garbage pile is not cleared. Very bad smell and mosquito breeding.",
                detected_language="en",
                english_translation="HSR layout sector 3 garbage pile is not cleared. Very bad smell and mosquito breeding.",
                sector="sanitation",
                specific_issue="Uncleared waste heap and disease vector risk",
                urgency_score=3.0,
                sentiment="negative",
                location="SRID=4326;POINT(77.6391 12.9062)"
            )
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
