"""
report_generator.py — PDF report generation for evaluation records.

Uses reportlab (pure Python, no system deps) to produce a structured,
single-page evaluation report that matches the analyst-tool aesthetic:
near-black on warm-off-white, monospace data, serif headings, flat ruled
sections, no decorative gradients or rounded elements.

Public API:
    generate_pdf_report(record: dict) -> bytes
        Returns the PDF as raw bytes for streaming to the client.
"""
import io
from datetime import datetime, timezone
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ── Palette (matches CSS design tokens) ──────────────────────────────────────

INK        = colors.HexColor("#1A1A18")   # --ink
INK2       = colors.HexColor("#4A4843")   # --ink-2
INK3       = colors.HexColor("#7A7570")   # --ink-3
BG         = colors.HexColor("#F5F3EE")   # --bg
SURFACE    = colors.HexColor("#EFEDE7")   # --surface
BORDER     = colors.HexColor("#C8C4BB")   # --border
ACCENT     = colors.HexColor("#C17A2A")   # --accent
OK_TEXT    = colors.HexColor("#2C5F3A")   # --ok-text
ERR_TEXT   = colors.HexColor("#7A2020")   # --err-text


# ── Paragraph styles ──────────────────────────────────────────────────────────

def _styles() -> Dict[str, ParagraphStyle]:
    base = dict(
        fontName      = "Helvetica",
        fontSize      = 9,
        leading       = 13,
        textColor     = INK,
        spaceAfter    = 0,
        spaceBefore   = 0,
    )
    return {
        "report_title": ParagraphStyle("report_title",
            fontName="Helvetica-Bold", fontSize=16,
            leading=20, textColor=INK, spaceAfter=2),

        "subtitle": ParagraphStyle("subtitle",
            fontName="Helvetica", fontSize=9,
            leading=13, textColor=INK3, spaceAfter=0),

        "section_label": ParagraphStyle("section_label",
            fontName="Helvetica-Bold", fontSize=7,
            leading=10, textColor=INK3,
            spaceBefore=14, spaceAfter=5,
            wordWrap="CJK",
            # uppercase simulated via text transform in content
        ),

        "body": ParagraphStyle("body",
            **{**base, "leading": 14, "spaceAfter": 0}),

        "mono": ParagraphStyle("mono",
            fontName="Courier", fontSize=8,
            leading=12, textColor=INK2),

        "mono_accent": ParagraphStyle("mono_accent",
            fontName="Courier-Bold", fontSize=8,
            leading=12, textColor=ACCENT),

        "field_value": ParagraphStyle("field_value",
            fontName="Helvetica", fontSize=9,
            leading=14, textColor=INK, spaceAfter=0),

        "footer_text": ParagraphStyle("footer_text",
            fontName="Courier", fontSize=7,
            leading=10, textColor=INK3),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_from_record(record: Dict[str, Any]) -> int:
    s = 0
    if record.get("title_or_topic"):    s += 25
    if record.get("main_idea"):         s += 25
    if record.get("main_problem"):      s += 25
    if record.get("proposed_solution"): s += 25
    return s


def _risk_label(record: Dict[str, Any]) -> tuple:
    """Returns (label_str, color)."""
    if record.get("truncated"):
        return "HIGH", ERR_TEXT
    score = _score_from_record(record)
    if score < 75:
        return "MEDIUM", ACCENT
    return "LOW", OK_TEXT


def _fmt_ts(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y  %H:%M UTC")
    except ValueError:
        return iso[:19]


def _wrap(text: str, style: ParagraphStyle) -> Paragraph:
    """Safely wrap text in a Paragraph, escaping XML special chars."""
    safe = (text or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


# ── Page template ─────────────────────────────────────────────────────────────

def _make_doc(buf: io.BytesIO) -> BaseDocTemplate:
    """Create a BaseDocTemplate with a single A4 frame with margins."""
    margin_h = 2.0 * cm
    margin_v = 2.2 * cm
    w, h     = A4

    frame = Frame(
        x1=margin_h, y1=margin_v,
        width=w - 2 * margin_h,
        height=h - 2 * margin_v,
        leftPadding=0, rightPadding=0,
        topPadding=0,  bottomPadding=0,
    )

    def _page_cb(canvas, doc):
        """Draw page border line and page number."""
        canvas.saveState()
        # Thin top rule
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(margin_h, h - margin_v + 4*mm, w - margin_h, h - margin_v + 4*mm)
        # Bottom rule + page number
        canvas.line(margin_h, margin_v - 4*mm, w - margin_h, margin_v - 4*mm)
        canvas.setFont("Courier", 7)
        canvas.setFillColor(INK3)
        canvas.drawRightString(
            w - margin_h,
            margin_v - 8*mm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    pt = PageTemplate(id="main", frames=[frame], onPage=_page_cb)
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        pageTemplates=[pt],
        title="R&D Proposal Evaluation Report",
        author="RnD Platform",
        leftMargin=margin_h, rightMargin=margin_h,
        topMargin=margin_v,  bottomMargin=margin_v,
    )
    return doc


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pdf_report(record: Dict[str, Any]) -> bytes:
    """
    Build and return a PDF report for one evaluation record.
    """
    buf    = io.BytesIO()
    doc    = _make_doc(buf)
    S      = _styles()
    story  = []
    W      = A4[0] - 4.0 * cm   # usable content width

    score         = _score_from_record(record)
    risk_lbl, risk_color = _risk_label(record)
    result_json   = record.get("result_json") or {}
    full_text     = ""
    if isinstance(result_json, dict):
        full_text = result_json.get("full_text", "")

    # ── Report header ──────────────────────────────────────────────────────
    title_text = record.get("title_or_topic") or record.get("filename") or "Untitled Proposal"
    story.append(_wrap(title_text, S["report_title"]))
    story.append(Spacer(1, 2*mm))
    story.append(_wrap(record.get("filename", ""), S["subtitle"]))
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width=W, thickness=1, color=BORDER, spaceAfter=4*mm))

    # ── Metadata row ──────────────────────────────────────────────────────
    meta_data = [
        ["Record ID",   record.get("id", "—")[:36]],
        ["Evaluated",   _fmt_ts(record.get("created_at", ""))],
        ["Model",       record.get("model_used", "—")],
        ["Pages",       str(record.get("page_count", "—"))],
        ["Characters",  f"{record.get('char_count', 0):,}"],
        ["Output score",f"{score} / 100"],
        ["Input risk",  risk_lbl],
        ["Truncated",   "Yes" if record.get("truncated") else "No"],
    ]

    meta_table_data = []
    for label, value in meta_data:
        meta_table_data.append([
            Paragraph(label.upper(), S["section_label"]),
            Paragraph(value, S["mono"] if label == "Record ID" else S["field_value"]),
        ])

    meta_table = Table(
        meta_table_data,
        colWidths=[4.5 * cm, W - 4.5 * cm],
        hAlign="LEFT",
    )
    meta_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, BORDER),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5*mm))

    # ── LLM analysis sections ──────────────────────────────────────────────
    sections = [
        ("01  TITLE / TOPIC",        record.get("title_or_topic")),
        ("02  MAIN IDEA & SUMMARY",   record.get("main_idea")),
        ("03  MAIN PROBLEM",          record.get("main_problem")),
        ("04  PROPOSED SOLUTION",     record.get("proposed_solution")),
    ]

    for sec_label, sec_text in sections:
        story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=2*mm))
        story.append(_wrap(sec_label, S["section_label"]))
        story.append(_wrap(sec_text or "Not stated in proposal", S["body"]))
        story.append(Spacer(1, 2*mm))

    # ── Extracted text (first 1500 chars) ──────────────────────────────────
    if full_text:
        story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=2*mm))
        story.append(_wrap("EXTRACTED TEXT PREVIEW  (first 1,500 characters)", S["section_label"]))
        preview = full_text[:1500]
        if len(full_text) > 1500:
            preview += f"\n\n… [{len(full_text):,} characters total — truncated in report]"
        story.append(_wrap(preview, S["mono"]))
        story.append(Spacer(1, 3*mm))

    # ── Footer note ────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=2*mm))
    story.append(_wrap(
        f"Generated by RnD Platform · {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}  "
        f"· Output score is a structural completeness proxy (0–100), not a peer-review judgement.",
        S["footer_text"],
    ))

    doc.build(story)
    return buf.getvalue()
