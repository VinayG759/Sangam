"""
Synthetic citizen reports for the demo, clearly marked is_synthetic=True.

Everything else the dashboard shows — places, households, water coverage — is
real government data from the loaded pack. The synthetic messages are placed
to mirror plausible patterns against that real data:

  • heavy "no water" demand in blocks where JJM reports LOW tap coverage
  • heavy "tap installed but no water comes" demand in some blocks where JJM
    reports 95%+ coverage (the paper-vs-reality case)
  • lighter background demand everywhere, across six needs and six languages
  • a few recent surges, so emerging-hotspot detection has something to find

    python -m scripts.seed_demo            # add ~4,000 synthetic reports
    python -m scripts.seed_demo --reset    # delete synthetic reports first

Never touches real (non-synthetic) reports.
"""

import argparse
import hashlib
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.db import new_session
from app.core.pack import get_pack
from app.features.intake.service import new_tracking_id
from app.models import Indicator, Region, Report

SEED = 2026
DAYS = 75

# (language, original text, English) per need. {n} = a number of days.
MESSAGES = {
    "water": [
        ("en", "No drinking water supply in our village for {n} days.", "No drinking water supply in our village for {n} days."),
        ("kn", "ನಮ್ಮ ಊರಿನಲ್ಲಿ {n} ದಿನಗಳಿಂದ ಕುಡಿಯುವ ನೀರು ಬರುತ್ತಿಲ್ಲ.", "Drinking water has not come to our village for {n} days."),
        ("kn", "ಬೋರ್‌ವೆಲ್ ಬತ್ತಿಹೋಗಿದೆ, ನೀರಿಗಾಗಿ ಎರಡು ಕಿಲೋಮೀಟರ್ ನಡೆಯಬೇಕು.", "The borewell has dried up; we have to walk two kilometres for water."),
        ("hi", "हमारे गाँव में {n} दिनों से पीने का पानी नहीं आया।", "Drinking water has not come to our village for {n} days."),
        ("te", "మా ఊరిలో {n} రోజులుగా తాగునీరు రావడం లేదు.", "Drinking water has not been coming to our village for {n} days."),
        ("ta", "எங்கள் ஊரில் {n} நாட்களாக குடிநீர் வரவில்லை.", "Drinking water has not come to our village for {n} days."),
        ("ur", "ہمارے گاؤں میں {n} دن سے پینے کا پانی نہیں آیا۔", "Drinking water has not come to our village for {n} days."),
    ],
    "water_paper": [  # tap connection exists on paper, no water in practice
        ("en", "The tap was installed last year but water never comes.", "The tap was installed last year but water never comes."),
        ("kn", "ನಲ್ಲಿ ಹಾಕಿದ್ದಾರೆ ಆದರೆ ನೀರು ಬರುವುದೇ ಇಲ್ಲ.", "They installed a tap but water never comes."),
        ("kn", "ಮನೆಗೆ ನಲ್ಲಿ ಸಂಪರ್ಕ ಇದೆ, {n} ದಿನಗಳಿಂದ ಒಂದು ಹನಿ ನೀರೂ ಬಂದಿಲ್ಲ.", "We have a tap connection at home but not a drop of water for {n} days."),
        ("hi", "नल तो लगा दिया पर पानी कभी नहीं आता।", "They fitted a tap but water never comes."),
        ("te", "కుళాయి పెట్టారు కానీ నీళ్లు రావడం లేదు.", "They installed a tap but water does not come."),
        ("ta", "குழாய் போட்டார்கள், ஆனால் தண்ணீர் வருவதில்லை.", "They installed a tap, but water does not come."),
    ],
    "road": [
        ("en", "The main road is full of potholes and buses have stopped coming.", "The main road is full of potholes and buses have stopped coming."),
        ("kn", "ಮುಖ್ಯ ರಸ್ತೆ ಗುಂಡಿಗಳಿಂದ ತುಂಬಿದೆ, ಬಸ್ ಬರುವುದು ನಿಂತಿದೆ.", "The main road is full of potholes; the bus has stopped coming."),
        ("kn", "ಪ್ರತಿ ಮಳೆಗಾಲದಲ್ಲಿ ನಮ್ಮ ಊರಿನ ರಸ್ತೆ ಕೊಚ್ಚಿಹೋಗುತ್ತದೆ.", "Our village road washes away every monsoon."),
        ("hi", "मुख्य सड़क गड्ढों से भरी है, बसें आना बंद हो गई हैं।", "The main road is full of potholes; buses have stopped coming."),
        ("te", "ప్రధాన రహదారి గుంతలతో నిండిపోయింది.", "The main road is full of potholes."),
    ],
    "electricity": [
        ("en", "Power cuts for 8 hours every day, the transformer keeps failing.", "Power cuts for 8 hours every day, the transformer keeps failing."),
        ("kn", "ಪ್ರತಿದಿನ ಎಂಟು ಗಂಟೆ ವಿದ್ಯುತ್ ಕಡಿತ, ಟ್ರಾನ್ಸ್‌ಫಾರ್ಮರ್ ಪದೇ ಪದೇ ಕೆಡುತ್ತದೆ.", "Eight hours of power cuts every day; the transformer keeps breaking down."),
        ("hi", "रोज़ आठ घंटे बिजली कटौती होती है, ट्रांसफार्मर बार-बार खराब होता है।", "Eight hours of power cuts every day; the transformer keeps failing."),
    ],
    "health": [
        ("en", "No doctor at the primary health centre for weeks.", "No doctor at the primary health centre for weeks."),
        ("kn", "ಪ್ರಾಥಮಿಕ ಆರೋಗ್ಯ ಕೇಂದ್ರದಲ್ಲಿ ವಾರಗಳಿಂದ ವೈದ್ಯರಿಲ್ಲ.", "There has been no doctor at the primary health centre for weeks."),
        ("hi", "प्राथमिक स्वास्थ्य केंद्र में हफ्तों से डॉक्टर नहीं है।", "There has been no doctor at the primary health centre for weeks."),
    ],
    "sanitation": [
        ("en", "Open drain overflowing next to houses, mosquitoes everywhere.", "Open drain overflowing next to houses, mosquitoes everywhere."),
        ("kn", "ಮನೆಗಳ ಪಕ್ಕದಲ್ಲಿ ತೆರೆದ ಚರಂಡಿ ತುಂಬಿ ಹರಿಯುತ್ತಿದೆ.", "An open drain is overflowing next to the houses."),
        ("hi", "घरों के पास खुली नाली बह रही है, हर जगह मच्छर हैं।", "An open drain is flowing next to the houses; there are mosquitoes everywhere."),
    ],
    "education": [
        ("en", "The school roof leaks and children sit outside.", "The school roof leaks and children sit outside."),
        ("kn", "ಶಾಲೆಯ ಛಾವಣಿ ಸೋರುತ್ತಿದೆ, ಮಕ್ಕಳು ಹೊರಗೆ ಕುಳಿತುಕೊಳ್ಳುತ್ತಾರೆ.", "The school roof is leaking; the children sit outside."),
        ("hi", "स्कूल की छत टपकती है, बच्चे बाहर बैठते हैं।", "The school roof leaks; the children sit outside."),
    ],
}
LANGUAGE_WEIGHT = {"kn": 5, "en": 2, "hi": 2, "te": 1, "ta": 1, "ur": 1}
CHANNELS = [("whatsapp", 5), ("telegram", 3), ("web", 2)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete existing synthetic reports first")
    args = parser.parse_args()

    rng = random.Random(SEED)
    pack = get_pack()
    now = datetime.now(timezone.utc)

    with new_session() as db:
        if args.reset:
            removed = db.execute(delete(Report).where(Report.is_synthetic.is_(True))).rowcount
            db.commit()
            print(f"removed {removed} synthetic reports")

        regions = list(db.scalars(select(Region).where(Region.country_code == pack.country_code, Region.level >= 2)))
        if not regions:
            raise SystemExit("No regions loaded. Run: python -m app.features.packs load " + pack.name)
        deepest = max(r.level for r in regions)
        blocks = [r for r in regions if r.level == deepest]
        districts = [r for r in regions if r.level == deepest - 1]
        coverage = {i.region_id: i.value for i in db.scalars(select(Indicator).where(
            Indicator.key == pack.indicators["water"].key))} if "water" in pack.indicators else {}

        plan: list[tuple[Region, str, int, bool]] = []  # (place, need, reports, recent surge)
        covered = sorted((b for b in blocks if b.id in coverage), key=lambda b: coverage[b.id])
        low, high = covered[:14], [b for b in covered if coverage[b.id] >= 95]
        for block in low:
            plan.append((block, "water", rng.randint(35, 75), rng.random() < 0.25))
        for block in rng.sample(high, min(8, len(high))):
            plan.append((block, "water_paper", rng.randint(30, 55), rng.random() < 0.25))
        for block in rng.sample(blocks, 100):
            plan.append((block, "water", rng.randint(1, 9), False))
        for district in districts:
            plan.append((district, "water", rng.randint(3, 18), False))
        for need in ("road", "electricity", "health", "sanitation", "education"):
            for block in rng.sample(blocks, 22):
                plan.append((block, need, rng.randint(6, 30), rng.random() < 0.1))
            for block in rng.sample(blocks, 60):
                plan.append((block, need, rng.randint(1, 4), False))

        total, person = 0, 0
        for region, need, count, surge in plan:
            sector = "water" if need == "water_paper" else need
            people: list[str] = []
            for _ in range(count):
                if people and rng.random() < 0.1:
                    who = rng.choice(people)  # the same resident reporting again
                else:
                    person += 1
                    who = hashlib.sha256(f"synthetic:{SEED}:{person}".encode()).hexdigest()
                    people.append(who)
                options = MESSAGES[need]
                weights = [LANGUAGE_WEIGHT[lang] for lang, _, _ in options]
                language, original, english = rng.choices(options, weights)[0]
                days = rng.randint(2, 20)
                age = rng.uniform(0, 10) if surge and rng.random() < 0.75 else rng.uniform(0, DAYS)
                db.add(Report(
                    tracking_id=new_tracking_id(), country_code=pack.country_code,
                    channel=rng.choices([c for c, _ in CHANNELS], [w for _, w in CHANNELS])[0],
                    reporter_hash=who, status="located", language=language,
                    text_original=original.format(n=days), text_en=english.format(n=days), sector=sector,
                    urgency=rng.choices([2, 3, 4, 5], [2, 4, 3, 1])[0], region_id=region.id,
                    location_method=rng.choice(["text", "gps", "picker"]), location_confidence=100.0,
                    is_synthetic=True, created_at=now - timedelta(days=age), processed_at=now - timedelta(days=age)))
                total += 1
        db.commit()
        print(f"added {total} synthetic reports across {len({p[0].id for p in plan})} places")


if __name__ == "__main__":
    main()
