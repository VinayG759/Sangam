from sqlalchemy import select

from app.features.analysis.run import run_analysis
from app.models import AnalysisRun, Priority, Report
from tests.helpers import add_quiet_background, add_reports


def priorities(db, run) -> dict[tuple[str, str], Priority]:
    return {(p.region_id, p.sector): p for p in db.scalars(select(Priority).where(Priority.run_id == run.id))}


def seed(db):
    add_quiet_background(db)
    add_reports(db, "TL-A-SOUTH", "water", 12)  # low coverage (30%), high demand → UNSERVED_GAP
    add_reports(db, "TL-A-NORTH", "water", 12)  # 90% "served" on paper, high demand → DELIVERY_GAP
    add_reports(db, "TL-A-EAST", "water", 12)  # money in progress, high demand → STALLED_ALLOCATION
    for region in ("TL-A-NORTH-RIVERTON", "TL-A-NORTH-HILLVIEW", "TL-A-SOUTH-LAKESIDE"):
        add_reports(db, region, "water", 3)
    add_reports(db, "TL-A-SOUTH", "road", 4)
    add_reports(db, "TL-A-NORTH", "road", 4)
    add_reports(db, "TL-A-EAST", "road", 2)  # below the privacy floor of 3


def test_the_join_produces_each_verdict(db, ai, loaded):
    seed(db)
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    assert run.status == "complete"
    got = priorities(db, run)
    assert got[("TL-A-SOUTH", "water")].verdict == "UNSERVED_GAP"
    assert got[("TL-A-NORTH", "water")].verdict == "DELIVERY_GAP"
    assert got[("TL-A-EAST", "water")].verdict == "STALLED_ALLOCATION"


def test_unserved_gap_gets_a_sourced_cost_estimate(db, ai, loaded):
    seed(db)
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    south = priorities(db, run)[("TL-A-SOUTH", "water")]
    assert south.beneficiaries == 700 and south.estimated_cost == 700_000  # 1000 households × 70% unserved
    facts = {f["id"]: f for f in south.evidence}
    assert facts["F1"]["value"] == 12
    assert facts["F5"]["value"] == 30 and facts["F5"]["source_name"] == "Test statistics office"
    assert facts["F6"]["period"] == "2019"
    assert "planning assumption" in facts["F8"]["label"]


def test_groups_below_the_privacy_floor_are_scored_but_hidden(db, ai, loaded):
    seed(db)
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    small = priorities(db, run)[("TL-A-EAST", "road")]
    assert small.displayable is False and small.rank == 0
    ranks = sorted(p.rank for p in priorities(db, run).values() if p.displayable)
    assert ranks == list(range(1, len(ranks) + 1))


def test_flagged_and_unlocated_reports_are_left_out(db, ai, loaded):
    add_reports(db, "TL-A-SOUTH", "water", 5)
    db.query(Report).update({Report.flagged_coordinated: True})
    db.commit()
    add_reports(db, "TL-A-NORTH", "water", 5, prefix="ok")
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    assert set(priorities(db, run)) == {("TL-A-NORTH", "water")}


def test_model_summary_with_invented_number_falls_back_to_template(db, ai, loaded):
    seed(db)
    ai.summary_text = "12 residents report problems and 37 wells have failed."
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    south = priorities(db, run)[("TL-A-SOUTH", "water")]
    assert south.summary_source == "template" and "37" not in south.summary
    assert "consider for allocation" in south.summary


def test_model_summary_that_passes_verification_is_used(db, ai, loaded):
    add_reports(db, "TL-A-SOUTH", "water", 12)
    add_reports(db, "TL-A-NORTH", "water", 3)
    ai.summary_text = "12 residents of Southmere report water problems; only 30% of households are connected."
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    assert priorities(db, run)[("TL-A-SOUTH", "water")].summary_source == "model"


def test_gemini_outage_still_completes_with_templates(db, ai, loaded):
    seed(db)
    ai.down = True
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    assert run.status == "complete"
    assert {p.summary_source for p in priorities(db, run).values()} == {"template"}


def test_a_failed_run_does_not_replace_the_last_complete_one(db, ai, loaded, monkeypatch):
    seed(db)
    good = run_analysis(db, ai, loaded, pause_seconds=0)

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.features.analysis.run.score_clusters", explode)
    bad = run_analysis(db, ai, loaded, pause_seconds=0)
    assert bad.status == "failed" and "disk full" in bad.error
    from app.core.runs import latest_complete_run
    assert latest_complete_run(db, "TL").id == good.id
    assert db.scalar(select(AnalysisRun).where(AnalysisRun.id == bad.id)).status == "failed"


def test_accelerating_demand_is_flagged_emerging(db, ai, loaded):
    add_reports(db, "TL-A-SOUTH", "water", 6, days_ago=2, prefix="new")
    add_reports(db, "TL-A-SOUTH", "water", 1, days_ago=20, prefix="old")
    add_reports(db, "TL-A-NORTH", "water", 6, days_ago=40)
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    from app.models import Cluster
    clusters = {c.region_id: c for c in db.scalars(select(Cluster).where(Cluster.run_id == run.id))}
    assert clusters["TL-A-SOUTH"].is_emerging is True
    assert clusters["TL-A-NORTH"].is_emerging is False


def test_places_to_monitor_rank_below_places_needing_action(db, ai, loaded):
    seed(db)
    run = run_analysis(db, ai, loaded, pause_seconds=0)
    shown = sorted((p for p in priorities(db, run).values() if p.displayable), key=lambda p: p.rank)
    verdicts = [p.verdict for p in shown]
    assert "MONITOR" in verdicts
    assert verdicts.index("MONITOR") > max(i for i, v in enumerate(verdicts) if v != "MONITOR")
