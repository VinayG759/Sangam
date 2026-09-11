import io
import html
from datetime import datetime
from typing import Dict, Any, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


def _escape(text: Any) -> str:
    """Safely escape text for ReportLab Paragraphs."""
    if text is None:
        return ""
    return html.escape(str(text))


def render_briefing_pdf(priority: Dict[str, Any], evidence: Dict[str, Any], brief: Dict[str, Any]) -> bytes:
    """
    Renders a 1-2 page government ministry briefing note PDF from priority, evidence, and narrative brief.
    Pure function: takes dictionary inputs and returns raw PDF bytes starting with %PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold",
        spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
        fontName="Helvetica"
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        "BriefBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        fontName="Helvetica"
    )
    label_style = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
        fontName="Helvetica-Bold"
    )
    value_style = ParagraphStyle(
        "MetaValue",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#0f172a"),
        fontName="Helvetica-Bold"
    )

    story = []

    # Title & Subtitle Header
    story.append(Paragraph("SANGAM | Infrastructure Priority Briefing", title_style))
    priority_id = priority.get("id", "N/A")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Official Briefing File &bull; Priority ID: #{priority_id} &bull; Generated: {timestamp}", subtitle_style))
    story.append(Spacer(1, 10))

    # Metric summary box
    verdict = priority.get("verdict", "UNSPECIFIED")
    score = priority.get("score", 0.0)
    region_name = priority.get("region_name") or evidence.get("region_name") or "Karnataka Region"
    sector = (priority.get("sector") or evidence.get("sector") or "General").capitalize()
    report_count = evidence.get("report_count", priority.get("report_count", 0))

    # Determine verdict color
    verdict_colors = {
        "UNSERVED_GAP": colors.HexColor("#ef4444"),
        "STALLED_ALLOCATION": colors.HexColor("#f59e0b"),
        "DELIVERY_GAP": colors.HexColor("#8b5cf6"),
        "WELL_SERVED": colors.HexColor("#10b981")
    }
    verdict_badge_color = verdict_colors.get(verdict, colors.HexColor("#3b82f6"))

    meta_table_data = [
        [
            Paragraph("VERDICT", label_style),
            Paragraph("PRIORITY SCORE", label_style),
            Paragraph("REGION / BLOCK", label_style),
            Paragraph("SECTOR", label_style),
            Paragraph("CITIZEN REPORTS", label_style),
        ],
        [
            Paragraph(f"<font color='{verdict_badge_color.hexval()}'><b>{_escape(verdict)}</b></font>", value_style),
            Paragraph(f"<b>{score:.1f}</b> / 100", value_style),
            Paragraph(f"<b>{_escape(region_name)}</b>", value_style),
            Paragraph(f"<b>{_escape(sector)}</b>", value_style),
            Paragraph(f"<b>{report_count}</b> verified reports", value_style),
        ]
    ]

    meta_table = Table(meta_table_data, colWidths=[120, 95, 125, 95, 95])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Section: Verified Narrative Brief
    story.append(Paragraph("Verified Narrative Brief", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=6))

    summary_text = brief.get("summary") or "No executive summary provided."
    why_text = brief.get("why_prioritized") or "Not analyzed."
    gap_text = brief.get("fiscal_gap_analysis") or "No fiscal gap analysis recorded."
    rec_text = brief.get("recommended_action") or "No recommended action specified."

    story.append(Paragraph(f"<b>Executive Summary:</b> {_escape(summary_text)}", body_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Why Prioritized:</b> {_escape(why_text)}", body_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Fiscal Gap Analysis:</b> {_escape(gap_text)}", body_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Recommended Action:</b> {_escape(rec_text)}", body_style))
    story.append(Spacer(1, 10))

    # Section: Evidence Bundle & Ground Truth
    story.append(Paragraph("Key Figures & Ground Truth Evidence", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=6))

    # Key figures row
    alloc_budget = evidence.get("allocated_budget")
    est_cost = evidence.get("estimated_cost")
    vuln_idx = evidence.get("vulnerability_index")
    avg_urgency = evidence.get("average_urgency")

    def _fmt_curr(val: Optional[float]) -> str:
        if val is None:
            return "None / Unspecified"
        if val >= 10000000:
            return f"₹{val / 10000000:.2f} Cr"
        if val >= 100000:
            return f"₹{val / 100000:.2f} Lakh"
        return f"₹{val:,.2f}"

    evidence_rows = [
        [
            Paragraph("Allocated Budget", label_style),
            Paragraph("Estimated Cost", label_style),
            Paragraph("Avg Citizen Urgency", label_style),
            Paragraph("Vulnerability Index", label_style)
        ],
        [
            Paragraph(_fmt_curr(alloc_budget), value_style),
            Paragraph(_fmt_curr(est_cost), value_style),
            Paragraph(f"{avg_urgency:.1f} / 5.0" if avg_urgency is not None else "N/A", value_style),
            Paragraph(f"{vuln_idx:.2f}" if vuln_idx is not None else "N/A", value_style)
        ]
    ]
    
    # Check for delivery rate indicators
    deliv_rate = evidence.get("delivery_rate")
    bench_rate = evidence.get("delivery_benchmark")
    if deliv_rate is not None or bench_rate is not None:
        evidence_rows[0].extend([Paragraph("Block Delivery", label_style), Paragraph("District Benchmark", label_style)])
        d_str = f"{deliv_rate * 100:.1f}%" if deliv_rate is not None else "N/A"
        b_str = f"{bench_rate * 100:.1f}%" if bench_rate is not None else "N/A"
        evidence_rows[1].extend([Paragraph(d_str, value_style), Paragraph(b_str, value_style)])

    num_cols = len(evidence_rows[0])
    col_w = 530 / num_cols
    ev_table = Table(evidence_rows, colWidths=[col_w] * num_cols)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ev_table)
    story.append(Spacer(1, 8))

    # Expenditure Records if any
    records = evidence.get("expenditure_records") or []
    if records:
        story.append(Paragraph("<b>Public Expenditure Records Matched:</b>", body_style))
        for r in records[:5]:
            title = r.get("title") or r.get("work_description") or "Expenditure entry"
            amt = _fmt_curr(r.get("amount"))
            status = r.get("status") or "recorded"
            story.append(Paragraph(f"&bull; <b>{_escape(title)}</b> — {amt} (Status: {_escape(status)})", body_style))
        story.append(Spacer(1, 6))

    # Citizen Quotes if any
    quotes = evidence.get("citizen_quotes") or []
    if quotes:
        story.append(Paragraph("<b>Direct Citizen Voices (PII-Redacted):</b>", body_style))
        for q in quotes[:4]:
            story.append(Paragraph(f'&ldquo;<i>{_escape(q)}</i>&rdquo;', body_style))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))
    # Footer Notice
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#94a3b8"), spaceBefore=4, spaceAfter=4))
    footer_text = (
        "Evidence-backed prioritization generated by Sangam Digital Public Good. "
        "Grounded against public records & citizen feedback. Number-verification enforced."
    )
    story.append(Paragraph(footer_text, subtitle_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
