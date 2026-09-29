"""
Demonstration data for the prototype, every row marked is_synthetic=True.

Real (from the country pack): places, rural households, water tap coverage.
Synthetic (from this script): citizen reports, statistics for the five other
needs, and public projects (spending). The engine that groups, scores, gives
verdicts and ranks is the same code that runs on real data — only its inputs
are made up. The synthetic data is shaped so every verdict and view has
something to show:

  • heavy "no water" demand in blocks where JJM reports LOW tap coverage
  • heavy "tap installed but no water comes" demand in some blocks where JJM
    reports 95%+ coverage (the paper-vs-reality case)
  • lighter background demand everywhere, across six needs and six languages
  • a few recent surges, so emerging-hotspot detection has something to find
  • statistics for roads, power, health, sanitation and schools: low where
    demand is heavy in some blocks (unserved), high in others (served on paper)
  • projects: stalled / in progress / sanctioned and planned where demand is
    heavy, routine work elsewhere, and completed projects with complaints
    before and after, so the impact view can judge them
  • a few schools blocks with no statistic, so demand hotspots appear too
  • reports that could not be placed on the map, each with its reason

    python -m scripts.seed_demo            # add the demo data
    python -m scripts.seed_demo --reset    # delete all synthetic data first

Never touches real (non-synthetic) rows.
"""

import argparse
import hashlib
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.db import new_session
from app.core.pack import get_pack
from app.features.intake.service import new_tracking_id
from app.models import Indicator, Project, Region, Report

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

SYNTHETIC_SOURCE = "Synthetic demonstration data (not a government record)"
OTHER_NEEDS = ("road", "electricity", "health", "sanitation", "education")
PROJECT_TITLES = {
    "water": "Piped water supply scheme",
    "road": "All-weather road upgrade",
    "electricity": "Feeder line and transformer upgrade",
    "health": "Primary health centre staffing and equipment",
    "sanitation": "Household toilet and drainage programme",
    "education": "School classroom repair",
}
# Unplaced reports by why they could not be placed: (status, location_failure, how many)
UNPLACED = [("unlocated", "no_place_named", 12), ("unlocated", "place_not_recognised", 10),
            ("unlocated", "low_confidence_match", 6), ("unlocated", "gave_up_after_questions", 5),
            ("needs_location", None, 4), ("needs_confirmation", None, 3)]


class Seeder:
    """Everything it writes is marked synthetic, so --reset can remove exactly what it added."""

    def __init__(self, db, pack, rng: random.Random, now: datetime):
        self.db, self.pack, self.rng, self.now = db, pack, rng, now
        self.person = 0
        self.reports = 0

    # ── citizen reports ──────────────────────────────────────────────────────

    def resident(self, people: list[str]) -> str:
        if people and self.rng.random() < 0.1:
            return self.rng.choice(people)  # the same resident reporting again
        self.person += 1
        who = hashlib.sha256(f"synthetic:{SEED}:{self.person}".encode()).hexdigest()
        people.append(who)
        return who

    def message(self, need: str) -> tuple[str, str, str]:
        options = MESSAGES[need]
        language, original, english = self.rng.choices(options, [LANGUAGE_WEIGHT[o[0]] for o in options])[0]
        days = self.rng.randint(2, 20)
        return language, original.format(n=days), english.format(n=days)

    def report(self, who: str, need: str, when: datetime, region: Region | None, status: str = "located",
               failure: str | None = None) -> None:
        rng = self.rng
        language, original, english = self.message(need)
        self.db.add(Report(
            tracking_id=new_tracking_id(), country_code=self.pack.country_code,
            channel=rng.choices([c for c, _ in CHANNELS], [w for _, w in CHANNELS])[0],
            reporter_hash=who, status=status, location_failure=failure, language=language,
            text_original=original, text_en=english, sector="water" if need == "water_paper" else need,
            urgency=rng.choices([2, 3, 4, 5], [2, 4, 3, 1])[0], region_id=region.id if region else None,
            location_method=rng.choice(["text", "gps", "picker"]) if region else None,
            location_confidence=100.0 if region else None,
            is_synthetic=True, created_at=when, processed_at=when))
        self.reports += 1

    def demand(self, region: Region, need: str, count: int, surge: bool) -> None:
        people: list[str] = []
        for _ in range(count):
            age = self.rng.uniform(0, 10) if surge and self.rng.random() < 0.75 else self.rng.uniform(0, DAYS)
            self.report(self.resident(people), need, self.now - timedelta(days=age), region)

    def around(self, region: Region, need: str, done: datetime, before: int, after: int) -> None:
        """Reports in the windows the impact view compares: before completion, and after the grace period."""
        t = self.pack.thresholds
        for count, start in ((before, done - timedelta(days=t.impact_window_days)),
                             (after, done + timedelta(days=t.impact_grace_days))):
            people: list[str] = []
            for _ in range(count):
                when = start + timedelta(days=self.rng.uniform(1, t.impact_window_days - 1))
                self.report(self.resident(people), need, when, region)

    def unplaced(self) -> int:
        n = 0
        for status, failure, count in UNPLACED:
            for _ in range(count):
                need = self.rng.choice(list(MESSAGES))
                self.report(self.resident([]), need, self.now - timedelta(days=self.rng.uniform(0, DAYS)), None,
                            status, failure)
                n += 1
        return n

    # ── reference data ───────────────────────────────────────────────────────

    def statistic(self, region_id: str, need: str, value: float, baseline: float) -> None:
        rule = self.pack.indicators[need]
        for key, period, v in ((rule.key, "2026", value), (rule.baseline_key, "2019", baseline)):
            self.db.add(Indicator(region_id=region_id, key=key, value=round(v, 1), unit="percent", period=period,
                                  source_name=SYNTHETIC_SOURCE, is_synthetic=True))

    def project(self, n: int, region: Region, need: str, status: str, households: float | None,
                sanctioned: date | None, completed: date | None = None) -> None:
        sector = "water" if need == "water_paper" else need
        cost = self.pack.costs.get(sector)
        homes = households or 2000
        amount = round((cost.per_unit if cost else 10000) * homes * self.rng.uniform(0.05, 0.25), -4)
        self.db.add(Project(
            id=f"DEMO-{n:04d}", region_id=region.id, sector=sector,
            title=f"{PROJECT_TITLES[sector]}, {region.name}", amount=amount, currency=self.pack.currency,
            status=status, sanctioned_date=sanctioned, completion_date=completed,
            source_name=SYNTHETIC_SOURCE, is_synthetic=True))


def reset(db) -> None:
    removed = [db.execute(delete(model).where(model.is_synthetic.is_(True))).rowcount
               for model in (Report, Project, Indicator)]
    db.commit()
    print(f"removed synthetic data: {removed[0]} reports, {removed[1]} projects, {removed[2]} statistics")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete existing synthetic data first")
    args = parser.parse_args()

    rng = random.Random(SEED)
    pack = get_pack()
    now = datetime.now(timezone.utc)
    today = now.date()

    with new_session() as db:
        if args.reset:
            reset(db)

        regions = list(db.scalars(select(Region).where(Region.country_code == pack.country_code, Region.level >= 2)))
        if not regions:
            raise SystemExit("No regions loaded. Run: python -m app.features.packs load " + pack.name)
        deepest = max(r.level for r in regions)
        blocks = sorted((r for r in regions if r.level == deepest), key=lambda r: r.id)
        districts = sorted((r for r in regions if r.level == deepest - 1), key=lambda r: r.id)
        real = {(i.region_id, i.key): i.value for i in db.scalars(select(Indicator).where(
            Indicator.is_synthetic.is_(False)))}
        households = {rid: v for (rid, key), v in real.items() if key == pack.population.indicator}
        coverage = {rid: v for (rid, key), v in real.items() if key == pack.indicators["water"].key}

        seeder = Seeder(db, pack, rng, now)
        plan: list[tuple[Region, str, int, bool]] = []  # (place, need, reports, recent surge)
        projects: list[tuple[Region, str, str]] = []  # (place, need, status)

        # Water: real coverage decides who is unserved (low) and where records say served (95%+).
        covered = sorted((b for b in blocks if b.id in coverage), key=lambda b: coverage[b.id])
        low, high = covered[:14], [b for b in covered if coverage[b.id] >= 95]
        for i, block in enumerate(low):
            plan.append((block, "water", rng.randint(35, 75), rng.random() < 0.25))
            if i in (3, 7, 11):
                projects.append((block, "water", rng.choice(["stalled", "in_progress", "sanctioned"])))
            elif i in (5, 9):
                projects.append((block, "water", "planned"))
        for block in rng.sample(high, min(8, len(high))):
            plan.append((block, "water_paper", rng.randint(30, 55), rng.random() < 0.25))
        for block in rng.sample(blocks, 100):
            plan.append((block, "water", rng.randint(1, 9), False))
        for district in districts:
            plan.append((district, "water", rng.randint(3, 18), False))

        # Other needs: synthetic statistics, shaped against where demand is heavy.
        statistics = 0
        for need in OTHER_NEEDS:
            rule = pack.indicators[need]
            heavy = rng.sample(blocks, 22)
            heavy_ids = {b.id for b in heavy}
            values: dict[str, float] = {}
            for i, block in enumerate(heavy):
                plan.append((block, need, rng.randint(8, 30), rng.random() < 0.1))
                role = i % 7  # 0-2 unserved, 3-4 served on paper, 5 money stuck, 6 money only planned
                if role in (3, 4):
                    values[block.id] = rng.uniform(rule.served_threshold + 1, 99)
                else:
                    values[block.id] = rng.uniform(30, rule.served_threshold - 15)
                if role == 5:
                    projects.append((block, need, rng.choice(["stalled", "in_progress", "sanctioned"])))
                elif role == 6:
                    projects.append((block, need, "planned"))
            for block in rng.sample(blocks, 60):
                plan.append((block, need, rng.randint(1, 4), False))
            for block in blocks:
                if block.id not in heavy_ids:
                    values[block.id] = rng.triangular(55, 99, 92)
            for district in districts:
                inside = [values[b.id] for b in blocks if b.parent_id == district.id]
                values[district.id] = sum(inside) / len(inside) if inside else rng.uniform(60, 95)
            if need == "education":  # a few places with no statistic at all: demand hotspots to verify
                for block in heavy[2::7]:
                    values.pop(block.id, None)
            for region_id, value in values.items():
                seeder.statistic(region_id, need, value, max(5.0, value - rng.uniform(3, 35)))
                statistics += 1

        for region, need, count, surge in plan:
            seeder.demand(region, need, count, surge)

        # Money: stuck and planned where demand is heavy; routine work elsewhere.
        n = 0
        for region, need, status in projects:
            n += 1
            sanctioned = None if status == "planned" else today - timedelta(days=rng.randint(200, 700))
            seeder.project(n, region, need, status, households.get(region.id), sanctioned)
        heavy_places = {r.id for r, _, count, _ in plan if count >= 6}
        quiet = [b for b in blocks if b.id not in heavy_places]  # no heavy complaints about anything
        for block in rng.sample(quiet, min(30, len(quiet))):
            n += 1
            need = rng.choice(list(PROJECT_TITLES))
            status = rng.choice(["in_progress", "sanctioned", "completed"])
            sanctioned = today - timedelta(days=rng.randint(200, 900))
            done = sanctioned + timedelta(days=rng.randint(120, 180)) if status == "completed" else None
            seeder.project(n, block, need, status, households.get(block.id), sanctioned, done)

        # Completed projects with a before/after story for the impact view.
        stories = [(22, 5)] * 5 + [(14, 13)] * 3 + [(7, 16)] * 3  # improved, no change, worse
        for (before, after), block in zip(stories, rng.sample(quiet, len(stories)), strict=False):
            n += 1
            need = rng.choice(list(PROJECT_TITLES))
            done = today - timedelta(days=rng.randint(125, 200))
            seeder.project(n, block, need, "completed", households.get(block.id),
                           done - timedelta(days=rng.randint(300, 500)), done)
            seeder.around(block, need, datetime.combine(done, datetime.min.time(), tzinfo=timezone.utc),
                          before + rng.randint(-2, 2), after + rng.randint(-1, 2))
        for block in rng.sample(quiet, 2):  # finished too recently to judge
            n += 1
            done = today - timedelta(days=rng.randint(10, 40))
            seeder.project(n, block, rng.choice(list(PROJECT_TITLES)), "completed", households.get(block.id),
                           done - timedelta(days=400), done)

        unplaced = seeder.unplaced()
        db.commit()
        print(f"added {seeder.reports} synthetic reports ({unplaced} unplaced), {n} projects, "
              f"{statistics} statistics x2 periods")


if __name__ == "__main__":
    main()
