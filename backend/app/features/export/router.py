"""One recommendation as a briefing PDF suitable for a ministry file."""

import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.pack import Pack, get_pack
from app.models import Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["export"])

VERDICT_TITLES = {"UNSERVED_GAP": "Unserved gap — consider for allocation",
                  "STALLED_ALLOCATION": "Stalled allocation — audit delivery",
                  "DELIVERY_GAP": "Delivery gap — records say served, residents disagree",
                  "MONITOR": "Monitor"}


def build_brief(priority: Priority, region: Region, pack: Pack, synthetic_reports: int) -> bytes:
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10, textColor=colors.grey)
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8.5, leading=11)
    need = pack.need(priority.sector)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Sangam brief — {region.name}")
    story = [
        Paragraph("SANGAM · PRIORITY BRIEF", small),
        Paragraph(f"{region.name}: {need.label_en if need else priority.sector}", styles["Title"]),
        Paragraph(f"<b>{VERDICT_TITLES.get(priority.verdict, priority.verdict)}</b> · Rank {priority.rank} · "
                  f"Score {priority.score:.1f} / 100", styles["BodyText"]),
        Spacer(1, 6),
        Paragraph(priority.summary, styles["BodyText"]),
        Paragraph("Summary written by AI and checked number-by-number against the evidence below."
                  if priority.summary_source == "model" else "Summary generated from a fixed template.", small),
        Spacer(1, 10),
        Paragraph("Evidence", styles["Heading3"]),
    ]
    rows = [["", "Fact", "Value", "Source"]]
    for fact in priority.evidence:
        value = fact.get("value")
        shown = f"{value:,}" if isinstance(value, (int, float)) else "—"
        unit = fact.get("unit") or ""
        period = f" ({fact['period']})" if fact.get("period") else ""
        source = fact.get("source_name") or ""
        if fact.get("source_url"):
            source += f"<br/><font size=7>{fact['source_url']}</font>"
        rows.append([fact["id"], Paragraph(fact["label"], cell), Paragraph(f"{shown} {unit}{period}", cell),
                     Paragraph(source, cell)])
    table = Table(rows, colWidths=[10 * mm, 62 * mm, 38 * mm, 64 * mm], repeatRows=1)
    table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, 0), 8), ("TEXTCOLOR", (0, 0), (-1, 0), colors.grey),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [table, Spacer(1, 10), Paragraph("How the score was computed", styles["Heading3"])]
    weights = {k: v for k, v in priority.components.items() if k != "missing"}
    score_rows = [["Term", "Value (0–1)", "Weight", "Points"]] + [
        [k, f"{v['value']:.3f}", f"{v['weight']:.2f}", f"{v['contribution']:+.1f}"] for k, v in weights.items()]
    score_table = Table(score_rows, colWidths=[40 * mm, 30 * mm, 25 * mm, 25 * mm])
    score_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5),
                                     ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey)]))
    story.append(score_table)
    missing = priority.components.get("missing") or []
    if missing:
        story.append(Paragraph(f"No data for: {', '.join(missing)} — remaining weights re-normalised.", small))
    story += [Spacer(1, 12), Paragraph(
        f"Analysis run {priority.run_id} · generated {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC · "
        "Ranking is arithmetic set by the weights in the country pack; the AI never decides the order.", small)]
    if synthetic_reports:
        story.append(Paragraph(f"{synthetic_reports} of the citizen reports behind this brief are synthetic "
                               "demonstration data. All statistics are real and sourced.", small))
    doc.build(story)
    return buffer.getvalue()


@router.get("/priorities/{priority_id}/brief.pdf")
def export_brief(priority_id: int, db: Session = Depends(get_db), pack: Pack = Depends(get_pack)):
    priority = db.scalar(select(Priority).where(Priority.id == priority_id, Priority.displayable.is_(True)))
    if not priority:
        raise HTTPException(status_code=404, detail="Priority not found")
    region = db.get(Region, priority.region_id)
    synthetic = db.scalar(select(func.count()).select_from(Report).where(
        Report.region_id == priority.region_id, Report.sector == priority.sector,
        Report.is_synthetic.is_(True))) or 0
    pdf = build_brief(priority, region, pack, synthetic)
    filename = f"sangam-{region.id}-{priority.sector}.pdf".lower()
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
