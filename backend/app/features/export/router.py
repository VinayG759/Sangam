"""One recommendation as a briefing PDF suitable for a ministry file."""

import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.limiter import limiter
from app.core.pack import Pack, get_pack
from app.core.signing import key_id, server_public_key, sign_pdf, signing_enabled, verify_pdf
from app.models import Priority, Region, Report

router = APIRouter(prefix="/api/v1", tags=["export"])
MAX_BRIEF_BYTES = 5 * 1024 * 1024

VERDICT_TITLES = {"UNSERVED_GAP": "Unserved gap — consider for allocation",
                  "STALLED_ALLOCATION": "Stalled allocation — audit delivery",
                  "DELIVERY_GAP": "Delivery gap — records say served, residents disagree",
                  "PLANNED_NOT_STARTED": "Planned, not started — audit why the planned work has not begun",
                  "DEMAND_HOTSPOT": "Demand hotspot — verify; no official data to compare yet",
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
        if fact.get("synthetic") and "Synthetic" not in source:
            source = "<b>Demo data.</b> " + source
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
    if synthetic_reports or any(f.get("synthetic") for f in priority.evidence):
        story.append(Paragraph("Prototype demonstration: evidence marked as synthetic or demo data is made up to "
                               "show how Sangam works. The ranking, verdict and arithmetic above were computed by "
                               "the real engine from it. Facts citing a government source are real.", small))
    if signing_enabled():
        where = f" at {get_settings().PUBLIC_APP_URL.rstrip('/')}/verify" if get_settings().PUBLIC_APP_URL else ""
        story.append(Paragraph(f"This file is digitally signed. Check that it has not been altered{where}.", small))
    else:
        story.append(Paragraph("This file is not signed: no signing key is configured on this server.", small))
    doc.build(story)
    return sign_pdf(buffer.getvalue())


@router.get("/verify/public-key")
def public_key():
    """The key that signs this server's briefs. The same key is published in docs/brief-signing-key.pub."""
    key = server_public_key()
    if key is None:
        raise HTTPException(status_code=404, detail="This server does not sign briefs")
    return {"algorithm": "Ed25519", "public_key": key, "key_id": key_id(key)}


@router.post("/verify")
@limiter.limit("20/minute")
async def verify_brief(request: Request, file: UploadFile = File(...)):
    """Is this PDF exactly as this server exported it? Nothing is stored."""
    data = await file.read(MAX_BRIEF_BYTES + 1)
    if len(data) > MAX_BRIEF_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 5 MB")
    key = server_public_key()
    if key is None:
        raise HTTPException(status_code=404, detail="This server does not sign briefs")
    result = verify_pdf(data, key)
    return {"status": result.status, "key_id": result.key_id, "server_key_id": key_id(key)}


@router.get("/priorities/{priority_id}/brief.pdf")
@limiter.limit("20/minute")  # each brief is rendered and signed on request
def export_brief(request: Request, priority_id: int, db: Session = Depends(get_db),
                 pack: Pack = Depends(get_pack)):
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
