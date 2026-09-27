"""
One analysis run: group reports by place × need, join each group to official
statistics and recorded spending, score, give a verdict, explain.

Runs are versioned. Results are written under a new run id and the run is
marked complete only at the very end, so a crash leaves the previous run
serving the dashboard.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.ai import AIClient, AIUnavailable
from app.core.pack import Pack
from app.features.analysis.scoring import (
    DELIVERY_GAP,
    DEMAND_HOTSPOT,
    MONITOR,
    PLANNED_NOT_STARTED,
    STALLED_ALLOCATION,
    UNSERVED_GAP,
    ClusterInput,
    ProjectFact,
    Scored,
    score_clusters,
)
from app.features.analysis.verify import unsupported_numbers
from app.models import AnalysisRun, Cluster, Indicator, Priority, Project, Region, Report, ReportMedia

log = logging.getLogger(__name__)
CITIZEN_SOURCE = "Citizen reports received by Sangam"


def run_analysis(db: Session, ai: AIClient, pack: Pack, run_id: int | None = None, summaries: int = 15,
                 pause_seconds: float = 4.5, now: datetime | None = None) -> AnalysisRun:
    now = now or datetime.now(timezone.utc)
    run = db.get(AnalysisRun, run_id) if run_id else None
    if run is None:
        run = AnalysisRun(country_code=pack.country_code, status="running", started_at=now)
        db.add(run)
        db.commit()
    try:
        stats = _run(db, ai, pack, run, summaries, pause_seconds, now)
        run.status, run.completed_at, run.stats = "complete", datetime.now(timezone.utc), stats
        db.commit()
    except Exception as exc:
        log.exception("Analysis run %s failed", run.id)
        db.rollback()
        run = db.get(AnalysisRun, run.id)
        run.status, run.error, run.completed_at = "failed", str(exc)[:2000], datetime.now(timezone.utc)
        db.commit()
    return run


def _run(db: Session, ai: AIClient, pack: Pack, run: AnalysisRun, summaries: int, pause: float,
         now: datetime) -> dict:
    # Retention: raw media is never kept longer than the pack allows.
    cutoff = now - timedelta(days=pack.privacy.media_retention_days)
    db.execute(delete(ReportMedia).where(ReportMedia.created_at < cutoff))

    reports = list(db.scalars(select(Report).where(
        Report.country_code == pack.country_code, Report.status == "located",
        Report.flagged_coordinated.is_(False), Report.sector.in_(pack.need_keys))))

    groups: dict[tuple[str, str], list[Report]] = defaultdict(list)
    for report in reports:
        groups[(report.region_id, report.sector)].append(report)

    regions = {r.id: r for r in db.scalars(select(Region).where(Region.country_code == pack.country_code))}
    indicators: dict[tuple[str, str], Indicator] = {}
    for ind in db.scalars(select(Indicator).where(Indicator.region_id.in_(regions)).order_by(Indicator.period)):
        indicators[(ind.region_id, ind.key)] = ind  # latest period wins
    projects: dict[tuple[str, str], list[Project]] = defaultdict(list)
    for project in db.scalars(select(Project).where(Project.region_id.in_(regions))):
        projects[(project.region_id, project.sector)].append(project)

    def population(region: Region) -> float | None:
        if region.population:
            return float(region.population)
        ind = indicators.get((region.id, pack.population.indicator)) if pack.population.indicator else None
        return ind.value if ind else None

    level_values: dict[tuple[str, int], list[float]] = defaultdict(list)
    for (region_id, key), ind in indicators.items():
        level_values[(key, regions[region_id].level)].append(ind.value)

    inputs, members = [], {}
    for (region_id, sector), group in groups.items():
        region = regions[region_id]
        rule = pack.indicators.get(sector)
        ind = indicators.get((region_id, rule.key)) if rule else None
        cost = pack.costs.get(sector)
        item = ClusterInput(
            region_id=region_id, level=region.level, sector=sector,
            distinct_reporters=len({r.reporter_hash for r in group}), population=population(region),
            indicator_value=ind.value if ind else None,
            higher_is_better=rule.higher_is_better if rule else True,
            served_threshold=rule.served_threshold if rule else None,
            level_values=level_values.get((rule.key, region.level), []) if rule else [],
            projects=[ProjectFact(p.status, float(p.amount) if p.amount is not None else None)
                      for p in projects[(region_id, sector)]],
            cost_per_unit=cost.per_unit if cost else None,
            indicator_is_percent=bool(rule and rule.unit == "percent"),
        )
        inputs.append(item)
        members[id(item)] = group

    w = pack.weights
    scored = score_clusters(inputs, {"demand": w.demand, "deficit": w.deficit, "reach": w.reach,
                                     "coverage": w.coverage}, pack.thresholds.high_demand_ratio)
    floor = pack.privacy.min_distinct_reporters
    # Evidence-backed actions (fund / audit) first, then hotspots to verify, then places to monitor;
    # the score orders places within each tier.
    tier = {DEMAND_HOTSPOT: 1, MONITOR: 0}
    scored.sort(key=lambda s: (s.input.distinct_reporters >= floor, tier.get(s.verdict, 2), s.score), reverse=True)

    window = timedelta(days=pack.thresholds.emerging_window_days)
    rank = 0
    written: list[tuple[Priority, Scored, list[dict]]] = []
    for s in scored:
        group = members[id(s.input)]
        recent = {r.reporter_hash for r in group if r.created_at >= now - window}
        before = {r.reporter_hash for r in group if now - 2 * window <= r.created_at < now - window}
        cluster = Cluster(
            run_id=run.id, region_id=s.input.region_id, sector=s.input.sector, report_count=len(group),
            distinct_reporters=s.input.distinct_reporters, per_1000=s.per_1000, baseline_ratio=s.baseline_ratio,
            avg_urgency=_mean([r.urgency for r in group if r.urgency]),
            is_emerging=len(recent) >= 3 and len(recent) >= 2 * max(len(before), 1),
            first_seen=min(r.created_at for r in group), last_seen=max(r.created_at for r in group))
        db.add(cluster)
        db.flush()

        displayable = s.input.distinct_reporters >= floor
        rank = rank + 1 if displayable else rank
        facts = _evidence(pack, regions[s.input.region_id], s, indicators, projects, population, len(recent))
        priority = Priority(
            run_id=run.id, cluster_id=cluster.id, region_id=s.input.region_id, sector=s.input.sector,
            rank=rank if displayable else 0, verdict=s.verdict, score=s.score, components=s.components,
            evidence=facts, estimated_cost=s.estimated_cost, beneficiaries=s.beneficiaries,
            summary=_template(pack, regions[s.input.region_id], s, facts), summary_source="template",
            displayable=displayable)
        db.add(priority)
        written.append((priority, s, facts))
    db.flush()

    explained = 0
    for priority, s, facts in written:
        if explained >= summaries or not priority.displayable:
            continue
        try:
            text = _explain(ai, pack, regions[s.input.region_id], s, facts)
        except AIUnavailable:
            break  # Gemini is down: keep the templates, don't wait on further calls
        explained += 1
        if text:
            priority.summary, priority.summary_source = text, "model"
        if pause:
            time.sleep(pause)  # stay inside the free-tier requests-per-minute limit

    verdicts = defaultdict(int)
    for priority, _, _ in written:
        if priority.displayable:
            verdicts[priority.verdict] += 1
    return {"reports_used": len(reports), "clusters": len(written),
            "displayable": sum(1 for p, _, _ in written if p.displayable), "verdicts": dict(verdicts),
            "model_summaries": sum(1 for p, _, _ in written if p.summary_source == "model")}


def _mean(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _fmt(value: float, decimals: int = 1) -> float | int:
    rounded = round(value, decimals)
    return int(rounded) if rounded == int(rounded) else rounded


def _evidence(pack: Pack, region: Region, s: Scored, indicators, projects, population, recent: int) -> list[dict]:
    """The closed set of facts a summary may use. Every one carries its source."""
    need = pack.need(s.input.sector)
    facts = [
        {"id": "F1", "label": f"Distinct residents reporting {need.label_en.lower()} problems",
         "value": s.input.distinct_reporters, "unit": "people", "source_name": CITIZEN_SOURCE, "source_url": None},
        {"id": "F2", "label": "Demand compared with the median place for this need", "value": _fmt(s.baseline_ratio),
         "unit": "times", "source_name": "Computed by Sangam from F1 and F4", "source_url": None},
    ]
    if s.per_1000 is not None:
        facts.append({"id": "F3", "label": f"Residents reporting per 1,000 {pack.population.label}",
                      "value": _fmt(s.per_1000, 2), "unit": f"per 1,000 {pack.population.label}",
                      "source_name": "Computed by Sangam from F1 and F4", "source_url": None})
    pop = population(region)
    pop_ind = indicators.get((region.id, pack.population.indicator)) if pack.population.indicator else None
    if pop:
        facts.append({"id": "F4", "label": pack.population.label.capitalize(), "value": int(pop), "unit": pack.population.label,
                      "period": pop_ind.period if pop_ind else None,
                      "source_name": (pop_ind.source_name if pop_ind else region.source_name),
                      "source_url": (pop_ind.source_url if pop_ind else region.source_url)})
    rule = pack.indicators.get(s.input.sector)
    if rule:
        for fact_id, key in (("F5", rule.key), ("F6", rule.baseline_key)):
            ind = indicators.get((region.id, key)) if key else None
            if ind:
                label = f"{rule.label or key} ({ind.period})"
                facts.append({"id": fact_id, "label": label, "value": _fmt(ind.value), "unit": ind.unit,
                              "period": ind.period, "source_name": ind.source_name, "source_url": ind.source_url})
    for i, project in enumerate(projects[(region.id, s.input.sector)][:3], start=1):
        facts.append({"id": f"P{i}", "label": f"{project.title} ({project.status.replace('_', ' ')})",
                      "value": float(project.amount) if project.amount is not None else None, "unit": project.currency,
                      "period": project.sanctioned_date.isoformat() if project.sanctioned_date else None,
                      "source_name": project.source_name, "source_url": project.source_url})
    if recent:
        facts.append({"id": "F7", "label": f"Residents reporting in the last {pack.thresholds.emerging_window_days} days",
                      "value": recent, "unit": "people", "source_name": CITIZEN_SOURCE, "source_url": None})
    if s.estimated_cost is not None:
        cost = pack.costs[s.input.sector]
        facts.append({"id": "F8", "label": f"Estimated cost to connect the unserved (planning assumption: "
                      f"{pack.currency_symbol}{cost.per_unit:,.0f} per {cost.unit_label})",
                      "value": round(s.estimated_cost), "unit": pack.currency, "source_name": cost.note,
                      "source_url": cost.source_url})
    return facts


def _fact(facts: list[dict], fact_id: str) -> dict | None:
    return next((f for f in facts if f["id"] == fact_id), None)


def _template(pack: Pack, region: Region, s: Scored, facts: list[dict]) -> str:
    """Deterministic explanation, used whenever the model's version is unavailable or fails verification."""
    need = pack.need(s.input.sector).label_en.lower()
    reporters, ratio = s.input.distinct_reporters, _fmt(s.baseline_ratio)
    official = _fact(facts, "F5")
    rule = pack.indicators.get(s.input.sector)
    official_text = (f" Official data ({official['source_name']}, {official['period']}) shows "
                     f"{(rule.label or rule.key).lower()} at {official['value']}"
                     f"{'%' if official['unit'] == 'percent' else ' ' + (official['unit'] or '')}.") if official else ""
    if s.verdict == DELIVERY_GAP:
        return (f"{reporters} residents of {region.name} report {need} problems, {ratio} times the median place."
                f"{official_text} Records say this place is served; residents say otherwise. "
                "Recommended action: audit delivery on the ground.")
    if s.verdict == STALLED_ALLOCATION:
        return (f"Public money is already committed to {need} in {region.name}, yet {reporters} residents still "
                f"report problems, {ratio} times the median place.{official_text} "
                "Recommended action: audit why the allocation has not reached people.")
    if s.verdict == PLANNED_NOT_STARTED:
        return (f"Public money for {need} in {region.name} is planned but no work has started, while "
                f"{reporters} residents report problems, {ratio} times the median place.{official_text} "
                "Recommended action: audit why the planned work has not begun.")
    if s.verdict == UNSERVED_GAP:
        return (f"{reporters} residents of {region.name} report {need} problems, {ratio} times the median place."
                f"{official_text} That is below the level counted as served. "
                "Recommended action: consider for allocation.")
    if s.verdict == DEMAND_HOTSPOT:
        return (f"{reporters} residents of {region.name} report {need} problems, {ratio} times the median place. "
                "No official statistic or spending record for this need is loaded yet, so the gap cannot be "
                "confirmed. Recommended action: verify on the ground and add the missing data.")
    return (f"{reporters} residents of {region.name} report {need} problems, close to the norm "
            f"({ratio} times the median place).{official_text} Recommended action: monitor.")


VERDICT_CONTEXT = {
    UNSERVED_GAP: "high citizen demand and the official statistic is below the level counted as served; the recommendation is to consider funding. Do not claim anything about projects or budgets that is not in the facts",
    STALLED_ALLOCATION: "high citizen demand although money is already committed; the recommendation is a delivery audit",
    DELIVERY_GAP: "high citizen demand although official statistics say the place is served; the recommendation is a delivery audit",
    PLANNED_NOT_STARTED: "high citizen demand; money is planned for this place but no work has started; the recommendation is to audit why the plan has not begun",
    DEMAND_HOTSPOT: "high citizen demand but no official statistic or spending data to compare against; the recommendation is to verify on the ground",
    MONITOR: "demand close to the norm; the recommendation is to monitor",
}


def _explain(ai: AIClient, pack: Pack, region: Region, s: Scored, facts: list[dict]) -> str | None:
    """Model-written summary, accepted only if every number in it is in the evidence. One retry.
    Raises AIUnavailable if Gemini cannot be reached, so the caller stops trying."""
    context = (f"Place: {region.name}. Need: {pack.need(s.input.sector).label_en}. "
               f"Verdict: {VERDICT_CONTEXT[s.verdict]}.")
    for _ in range(2):
        result = ai.write_summary(facts, context)
        bad = unsupported_numbers(result.summary, facts)
        if not bad and result.summary.strip():
            return result.summary.strip()
        log.info("Rejected summary for %s/%s — unsupported numbers %s", region.id, s.input.sector, bad)
    return None
