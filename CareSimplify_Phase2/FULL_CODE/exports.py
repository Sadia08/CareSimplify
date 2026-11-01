from __future__ import annotations

from io import BytesIO, StringIO
import csv
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
    PageBreak, HRFlowable
)
from care_plan import TE_PHRASES, TE_LABELS, translate_telugu_conservative, timing_from_frequency

# Consistent design tokens used in both downloadable PDFs.
NAVY = colors.HexColor("#12304A")
BLUE = colors.HexColor("#1769AA")
TEAL = colors.HexColor("#087E8B")
GREEN = colors.HexColor("#287D4F")
PURPLE = colors.HexColor("#6D4BA1")
RED = colors.HexColor("#B42332")
INK = colors.HexColor("#263746")
MUTED = colors.HexColor("#5B6B78")
PALE_BLUE = colors.HexColor("#EAF4FC")
PALE_TEAL = colors.HexColor("#E7F5F4")
PALE_GREEN = colors.HexColor("#EAF6EE")
PALE_PURPLE = colors.HexColor("#F2EDFA")
PALE_RED = colors.HexColor("#FDECEC")
PALE_GREY = colors.HexColor("#F4F7F9")
WHITE = colors.white

_FONT_PATH = Path(__file__).parent / "assets" / "NotoSansTelugu-Regular.ttf"
try:
    if _FONT_PATH.exists() and "TeluguCare" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("TeluguCare", str(_FONT_PATH)))
    TELUGU_FONT_AVAILABLE = _FONT_PATH.exists()
except Exception:
    TELUGU_FONT_AVAILABLE = False


def _p(value, style):
    """Escape source content before placing it in ReportLab paragraph markup."""
    return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), style)


def _mixed_markup(value, telugu=False):
    """Use the embedded Telugu font only for Telugu glyphs; preserve Latin drug names."""
    value = str(value or "")
    if not telugu or not TELUGU_FONT_AVAILABLE:
        return escape(value)
    chunks, current, current_font = [], [], None
    for char in value:
        font = "TeluguCare" if 0x0C00 <= ord(char) <= 0x0C7F else "Helvetica"
        if current_font is not None and font != current_font:
            chunks.append(f'<font name="{current_font}">{escape("".join(current))}</font>')
            current = []
        current_font = font
        current.append(char)
    if current:
        chunks.append(f'<font name="{current_font}">{escape("".join(current))}</font>')
    return "".join(chunks)


def _safe_list(values, fallback):
    values = [str(v).strip() for v in (values or []) if str(v).strip()]
    return values or [fallback]


def _footer(canvas, doc):
    canvas.saveState()
    page_w, _ = doc.pagesize
    canvas.setStrokeColor(colors.HexColor("#D8E2E9"))
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, 10 * mm, page_w - doc.rightMargin, 10 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 6.5 * mm,
        "CARESIMPLIFY • DRAFT ONLY • Verify against the original discharge summary")
    canvas.drawRightString(page_w - doc.rightMargin, 6.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _section_bar(title, fill, text_color=WHITE, width=None, font_size=10):
    style = ParagraphStyle(
        "section_" + re.sub(r"\W+", "_", title)[:20],
        fontName="Helvetica-Bold", fontSize=font_size, leading=font_size + 3,
        textColor=text_color, spaceAfter=0, spaceBefore=0
    )
    t = Table([[Paragraph(escape(title), style)]], colWidths=[width] if width else None)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.5, fill),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _medicine_table(plan, compact=False):
    body = getSampleStyleSheet()["BodyText"]
    name_style = ParagraphStyle("MedicineName", parent=body, fontName="Helvetica-Bold",
                                fontSize=9 if not compact else 7.8, leading=11 if not compact else 9)
    cell_style = ParagraphStyle("MedicineCell", parent=body, fontSize=8.5 if not compact else 7.1,
                                leading=10 if not compact else 8.4, textColor=INK)
    header_style = ParagraphStyle("MedicineHeader", parent=body, fontName="Helvetica-Bold",
                                  fontSize=7.7 if compact else 8, leading=9, textColor=WHITE)
    rows = [[Paragraph(x, header_style) for x in ["MEDICINE", "DOSE", "FREQUENCY", "TIMING", "DURATION", "SOURCE INSTRUCTION"]]]
    medicines = plan.get("medicines", []) or []
    for med in medicines:
        rows.append([
            Paragraph(escape(str(med.get("name") or "Medicine not identified")), name_style),
            Paragraph(escape(str(med.get("dose") or "Check source")), cell_style),
            Paragraph(escape(str(med.get("frequency") or "Check source")), cell_style),
            Paragraph(escape(str(timing_from_frequency(med.get("frequency", ""), med.get("timing", "")))), cell_style),
            Paragraph(escape(str(med.get("duration") or "Check source")), cell_style),
            Paragraph(escape(str(med.get("how_to_take_plain") or "Check original instruction")), cell_style),
        ])
    widths = ([31, 20, 22, 27, 21, 52] if compact else [34, 22, 25, 31, 24, 54])
    widths = [w * mm for w in widths]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5E0E7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4 if compact else 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if compact else 5),
    ]
    for row_idx in range(1, len(rows)):
        commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx),
                         WHITE if row_idx % 2 else PALE_BLUE))
    table.setStyle(TableStyle(commands))
    return table


def _list_panel(title, values, heading_color, background, body_style, fallback, prefix="• "):
    title_style = ParagraphStyle("panel_" + re.sub(r"\W+", "_", title)[:18],
        fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=heading_color)
    items = [Paragraph(escape(prefix + str(v)), body_style) for v in _safe_list(values, fallback)]
    content = [[Paragraph(escape(title), title_style)], *[[item] for item in items]]
    table = Table(content, colWidths=[None], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.7, heading_color),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, heading_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _plan_sections(plan, compact=False):
    styles = getSampleStyleSheet()
    body = ParagraphStyle("CareBody", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=8.7 if compact else 9.2,
        leading=11 if compact else 12.5, textColor=INK, spaceAfter=1)
    story = []
    story.append(_section_bar("MY CARE PLAN", NAVY, font_size=10 if compact else 11))
    story.append(Spacer(1, 2 * mm))
    story.append(_section_bar("YOUR MEDICINES", BLUE, font_size=9.5 if compact else 10))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_medicine_table(plan, compact=compact))
    story.append(Spacer(1, 2 * mm))

    stops = plan.get("stop_medicines", [])
    stop_values = [f"STOP — {x}" for x in stops] if stops else [
        "No stop instruction was confidently extracted. Check the original discharge summary."
    ]
    story.append(_list_panel("MEDICINES TO STOP", stop_values, RED, PALE_RED, body,
                             "Check the original discharge summary.", prefix="⛔ " if not compact else "STOP — "))
    story.append(Spacer(1, 2 * mm))
    story.append(_list_panel("WARNING SIGNS — SEEK URGENT CARE AS WRITTEN IN YOUR SUMMARY",
        plan.get("warning_signs", []), RED, PALE_RED, body,
        "No warning signs confidently extracted. Check the original summary.", prefix="⚠ " if not compact else "• "))
    story.append(Spacer(1, 2 * mm))

    # Two-column presentation keeps related lifestyle sections visually grouped.
    panels = [
        ("FOOD / DIET", plan.get("diet", []), GREEN, PALE_GREEN),
        ("ACTIVITY", plan.get("activity", []), PURPLE, PALE_PURPLE),
        ("OTHER ADVICE", plan.get("other_advice", []), TEAL, PALE_TEAL),
        ("FOLLOW-UP", [
            " — ".join(str(f.get(k, "")).strip() for k in ("date", "with_whom", "purpose") if str(f.get(k, "")).strip())
            for f in plan.get("follow_ups", [])
        ], BLUE, PALE_BLUE),
    ]
    panel_tables = []
    for title, values, colour, pale in panels:
        panel_tables.append(_list_panel(title, values, colour, pale, body,
            "No instruction confidently extracted. Check the original summary."))
    col_w = 88 * mm if compact else 88 * mm
    for idx in range(0, len(panel_tables), 2):
        pair = [panel_tables[idx], panel_tables[idx + 1]]
        t = Table([[pair[0], pair[1]]], colWidths=[col_w, col_w], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.extend([t, Spacer(1, 2 * mm)])
    safety = ParagraphStyle("SafetyNote", fontName="Helvetica-Bold", fontSize=7.8 if compact else 8.3,
                            leading=9.5 if compact else 10.5, textColor=RED)
    safety_box = Table([[Paragraph(
        "IMPORTANT SAFETY NOTE: Draft generated from extracted text. Confirm every medicine, dose, timing, duration, warning and follow-up against the original discharge summary and treating team. Do not use this draft to start, stop or change treatment.",
        safety)]], colWidths=[176 * mm])
    safety_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_RED),
        ("BOX", (0, 0), (-1, -1), 0.8, RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(safety_box)
    return story


def make_full_pdf(plan, english, telugu=""):
    """Create a structured, styled care-plan PDF; source instructions remain unchanged."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm,
                            topMargin=13*mm, bottomMargin=15*mm, title="CareSimplify Patient Care Plan")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CareTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=21, leading=25, alignment=TA_LEFT, textColor=NAVY, spaceAfter=2*mm)
    subtitle = ParagraphStyle("CareSubtitle", parent=styles["Normal"], fontSize=9,
        leading=12, textColor=MUTED, spaceAfter=4*mm)
    story = [
        Paragraph("CareSimplify", title_style),
        Paragraph("PATIENT CARE PLAN", ParagraphStyle("SubTitleNavy", parent=title_style, fontSize=13, leading=16, textColor=TEAL)),
        Paragraph("A patient-friendly draft • Always verify with the original discharge summary", subtitle),
        HRFlowable(width="100%", thickness=1.2, color=TEAL, spaceAfter=4*mm),
    ]
    story.extend(_plan_sections(plan, compact=False))
    if telugu:
        story.append(PageBreak())
        story.append(Paragraph("Telugu-labelled draft", title_style))
        story.append(Paragraph("Translation is conservative; unknown clinical wording may remain in English.", subtitle))
        telugu_style = ParagraphStyle("TeluguSmall", fontName="TeluguCare" if TELUGU_FONT_AVAILABLE else "Helvetica",
                                      fontSize=9, leading=13, textColor=INK)
        for line in telugu.splitlines():
            if line.strip().isupper() and len(line.strip()) < 90:
                story.extend([Spacer(1, 2*mm), _section_bar(line.strip(), TEAL), Spacer(1, 1*mm)])
            elif line.strip():
                story.append(Paragraph(escape(line), telugu_style))
            else:
                story.append(Spacer(1, 1.5*mm))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def make_fridge_pdf(plan, language="English only"):
    """Create a colourful, one-page printable fridge sheet."""
    telugu = str(language).lower().startswith("telugu")
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=8*mm, leftMargin=8*mm,
                            topMargin=6*mm, bottomMargin=7*mm, title="CareSimplify Home Care Fridge Sheet")
    styles = getSampleStyleSheet()
    title_font = "TeluguCare" if telugu and TELUGU_FONT_AVAILABLE else "Helvetica-Bold"
    title_style = ParagraphStyle("FridgeTitle", fontName=title_font, fontSize=17, leading=20,
        alignment=TA_CENTER, textColor=NAVY, spaceAfter=2)
    subtitle_style = ParagraphStyle("FridgeSubtitle", fontName="Helvetica", fontSize=7.5,
        leading=9, alignment=TA_CENTER, textColor=MUTED, spaceAfter=3)
    story = [
        Paragraph("ఇంటి సంరక్షణ — ఫ్రిజ్‌పై ఉంచే సూచనల పత్రం" if telugu else "HOME CARE — FRIDGE SHEET", title_style),
        Paragraph("Keep with the original discharge summary • Draft only: verify before use", subtitle_style),
        HRFlowable(width="100%", thickness=1.4, color=TEAL, spaceAfter=2*mm),
    ]
    # Compact body style and a two-column grid help retain all sections on one A4 page.
    body = ParagraphStyle("FridgeBody", fontName="Helvetica", fontSize=7.4, leading=8.6,
                          textColor=INK, spaceAfter=0)
    if telugu and TELUGU_FONT_AVAILABLE:
        body = ParagraphStyle("FridgeBodyTe", fontName="TeluguCare", fontSize=7.1, leading=8.3,
                              textColor=INK, spaceAfter=0)

    def translated(v):
        v = str(v or "")
        if not telugu:
            return v
        return TE_PHRASES.get(v, v)

    def panel(title, values, heading, pale, fallback, prefix="• "):
        head = ParagraphStyle("fr_" + re.sub(r"\W+", "_", title)[:16], fontName=title_font,
                              fontSize=8.2, leading=9.5, textColor=heading)
        rows = [[Paragraph(_mixed_markup(title, telugu), head)]]
        for item in _safe_list(values, fallback):
            rows.append([Paragraph(_mixed_markup(prefix + translated(item), telugu), body)])
        t = Table(rows, colWidths=[89*mm], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), pale),
            ("BOX", (0, 0), (-1, -1), 0.55, heading),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, heading),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3),
        ]))
        return t

    med_values = []
    for m in plan.get("medicines", []) or []:
        med_values.append(
            f"{m.get('name') or 'Medicine not identified'} | Dose: {m.get('dose') or 'Check source'} | "
            f"Frequency: {m.get('frequency') or 'Check source'} | "
            f"Timing: {timing_from_frequency(m.get('frequency', ''), m.get('timing', ''))} | "
            f"Duration: {m.get('duration') or 'Check source'}"
        )
    stop_values = [f"STOP — {x}" for x in plan.get("stop_medicines", [])]
    follow_values = [
        " — ".join(str(f.get(k, "")).strip() for k in ("date", "with_whom", "purpose") if str(f.get(k, "")).strip())
        for f in plan.get("follow_ups", [])
    ]
    left = [
        panel("MEDICINES" if not telugu else "మందులు", med_values, BLUE, PALE_BLUE,
              "No medicine confidently extracted. Check source."),
        Spacer(1, 1.5*mm),
        panel("STOP MEDICINES" if not telugu else "ఆపాల్సిన మందులు", stop_values, RED, PALE_RED,
              "No stop instruction confidently extracted. Check source.", prefix="STOP: "),
        Spacer(1, 1.5*mm),
        panel("DIET" if not telugu else "ఆహారం / ఆహార నియమాలు", plan.get("diet", []), GREEN, PALE_GREEN,
              "Check the original discharge summary."),
        Spacer(1, 1.5*mm),
        panel("ACTIVITY" if not telugu else "శారీరక కార్యకలాపాలు", plan.get("activity", []), PURPLE, PALE_PURPLE,
              "Check the original discharge summary."),
    ]
    right = [
        panel("WARNING SIGNS" if not telugu else "హెచ్చరిక లక్షణాలు", plan.get("warning_signs", []), RED, PALE_RED,
              "Check the original discharge summary."),
        Spacer(1, 1.5*mm),
        panel("OTHER ADVICE" if not telugu else "ఇతర సూచనలు", plan.get("other_advice", []), TEAL, PALE_TEAL,
              "Check the original discharge summary."),
        Spacer(1, 1.5*mm),
        panel("FOLLOW-UP" if not telugu else "తదుపరి వైద్య పరీక్షలు", follow_values, BLUE, PALE_BLUE,
              "No follow-up confidently extracted. Check source."),
    ]
    grid = Table([[left, right]], colWidths=[91*mm, 91*mm], hAlign="CENTER")
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(grid)
    story.append(Spacer(1, 2*mm))
    safety_style = ParagraphStyle("FridgeSafety", fontName="Helvetica-Bold", fontSize=7.1,
                                  leading=8.5, textColor=RED, alignment=TA_LEFT)
    safety = Table([[Paragraph(
        "SAFETY: This is a draft, not a prescription. Confirm every medicine and instruction with the original discharge summary and care team. Never start, stop or change a medicine based only on this sheet.",
        safety_style)]], colWidths=[181*mm])
    safety.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_RED), ("BOX", (0, 0), (-1, -1), 0.7, RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(safety)
    try:
        doc.build(story)
    except Exception:
        # Keep long input printable: use the same one-page design with a smaller type scale.
        # The normal layout already uses compact styles; this fallback is a defensive retry.
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=6*mm, leftMargin=6*mm,
                                topMargin=4*mm, bottomMargin=5*mm, title="CareSimplify Home Care Fridge Sheet")
        doc.build(story)
    return buf.getvalue()


def make_csv(rows):
    """Create the medicine timetable CSV in UTF-8 with a spreadsheet-friendly BOM."""
    buf = StringIO()
    fields = ["Medicine", "Dose", "Frequency", "Timing", "Duration", "Instruction Copied from Source"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalized = dict(row)
        if "Instruction Copied from Source" not in normalized:
            normalized["Instruction Copied from Source"] = normalized.get("Instruction copied from source", "")
        writer.writerow({field: normalized.get(field, "") for field in fields})
    return buf.getvalue().encode("utf-8-sig")
