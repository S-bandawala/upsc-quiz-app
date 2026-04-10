"""
Exports the 100 pre-generated AI-insight questions to a clean PDF.
One question per section: question + options + AI analysis.

Usage: python scripts/export_insights_pdf.py
Output: scripts/upsc_ai_insights_100.pdf
"""

import sqlite3, json, re, os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "upsc_beta.db"
OUT_PATH = Path(__file__).resolve().parent / "upsc_ai_insights_100.pdf"

# ── Palette ────────────────────────────────────────────────────────────────────
C_DARK   = HexColor("#1a1a2e")   # deep navy
C_ACCENT = HexColor("#16213e")   # darker blue for headers
C_GREEN  = HexColor("#0a6e4a")   # correct answer green
C_ORANGE = HexColor("#c25c00")   # trap/warning
C_PURPLE = HexColor("#4a2070")   # UPSC Pattern
C_TEAL   = HexColor("#005f73")   # Lock It In
C_CREAM  = HexColor("#fdf6e3")   # soft background for Q block
C_LIGHT  = HexColor("#e8f4f8")   # light blue tint for answer block
C_RULE   = HexColor("#cccccc")   # horizontal rule
C_GRAY   = HexColor("#555555")   # body text
C_YEAR   = HexColor("#2c5f8a")   # year badge

W, H = A4
MARGIN = 18 * mm

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    """Remove control chars, fix common Unicode issues, escape XML for ReportLab."""
    if not text:
        return ""
    # Replace common problematic chars
    text = text.replace("\u2713", "✓").replace("\u2717", "✗")
    text = text.replace("━", "─").replace("●", "•")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("→", "->").replace("←", "<-")
    # Bold (**text**) → <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Escape XML special chars (but preserve our tags)
    # We need to escape & < > that are NOT part of our tags
    # Simple approach: escape first, then restore our tags
    text = text.replace("&", "&amp;")
    text = text.replace("<b>", "§BOLD§").replace("</b>", "§/BOLD§")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("§BOLD§", "<b>").replace("§/BOLD§", "</b>")
    return text


def section_color(header: str) -> tuple:
    """Return (bg_color, label_color) for a section header."""
    h = header.upper()
    if "CORRECT" in h or "RIGHT" in h:
        return C_GREEN, colors.white
    if "TRAP" in h:
        return C_ORANGE, colors.white
    if "UPSC PATTERN" in h or "PATTERN" in h:
        return C_PURPLE, colors.white
    if "LOCK" in h:
        return C_TEAL, colors.white
    return C_DARK, colors.white


def parse_sections(raw: str) -> list[tuple[str, str]]:
    """
    Parse AI insight into (header, body) pairs.
    Handles both emoji-header and plain-text header styles.
    """
    raw = raw.strip()
    # Try to split on lines that look like section headers
    # Headers: lines that are ALL CAPS or start with emoji + caps
    lines = raw.split("\n")
    sections = []
    cur_header = ""
    cur_body   = []

    header_pat = re.compile(
        r'^(CORRECT ANSWER.*|TRAP ANALYSIS.*|UPSC PATTERN.*|LOCK IT IN.*|'
        r'[✅🎯🧠⚠️🔒].*|WHY \([A-D]\).*)',
        re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if cur_body:
                cur_body.append("")
            continue
        if header_pat.match(stripped):
            if cur_header or cur_body:
                sections.append((cur_header, "\n".join(cur_body).strip()))
            cur_header = stripped
            cur_body = []
        else:
            cur_body.append(stripped)

    if cur_header or cur_body:
        sections.append((cur_header, "\n".join(cur_body).strip()))

    # Fallback: if no sections found, treat whole thing as one block
    if not sections:
        sections = [("AI MENTOR ANALYSIS", raw)]

    return sections


# ── Styles ─────────────────────────────────────────────────────────────────────
def make_styles():
    base = dict(fontName="Helvetica", fontSize=10, leading=15,
                textColor=C_GRAY, spaceAfter=4)

    title_style = ParagraphStyle("Title", fontName="Helvetica-Bold",
        fontSize=22, leading=28, textColor=C_DARK, spaceAfter=4, alignment=TA_CENTER)
    sub_style   = ParagraphStyle("Sub", fontName="Helvetica",
        fontSize=11, leading=16, textColor=C_GRAY, spaceAfter=2, alignment=TA_CENTER)
    year_style  = ParagraphStyle("Year", fontName="Helvetica-Bold",
        fontSize=13, leading=18, textColor=C_YEAR, spaceAfter=6)
    q_meta      = ParagraphStyle("QMeta", fontName="Helvetica-Bold",
        fontSize=9, leading=13, textColor=C_GRAY, spaceAfter=2)
    q_text      = ParagraphStyle("QText", fontName="Helvetica",
        fontSize=10.5, leading=16, textColor=C_DARK, spaceAfter=6,
        firstLineIndent=0, alignment=TA_JUSTIFY)
    opt_style   = ParagraphStyle("Opt", fontName="Helvetica",
        fontSize=10, leading=15, textColor=C_GRAY,
        leftIndent=8, spaceAfter=2)
    opt_correct = ParagraphStyle("OptC", fontName="Helvetica-Bold",
        fontSize=10, leading=15, textColor=C_GREEN,
        leftIndent=8, spaceAfter=2)
    sec_hdr     = ParagraphStyle("SecHdr", fontName="Helvetica-Bold",
        fontSize=9.5, leading=14, textColor=colors.white, spaceAfter=0)
    sec_body    = ParagraphStyle("SecBody", fontName="Helvetica",
        fontSize=10, leading=15, textColor=C_DARK, spaceAfter=0,
        leftIndent=4, alignment=TA_JUSTIFY)

    return dict(title=title_style, sub=sub_style, year=year_style,
                q_meta=q_meta, q_text=q_text, opt=opt_style,
                opt_correct=opt_correct, sec_hdr=sec_hdr, sec_body=sec_body)


# ── Load data ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT id, q_num, year_first, year_tags, topic, subtopic,
           question, option_a, option_b, option_c, option_d,
           correct_option, difficulty, ai_explanation
    FROM questions
    WHERE ai_explanation IS NOT NULL AND ai_explanation != ''
    ORDER BY year_first, q_num
""").fetchall()
conn.close()
qs = [dict(r) for r in rows]
print(f"Loaded {len(qs)} questions with AI insights")

# ── Build PDF ──────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    str(OUT_PATH),
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=16*mm, bottomMargin=16*mm,
    title="UPSC AI Mentor — 100 Questions with Insights",
    author="UPSC Quiz App"
)

S = make_styles()
story = []
PW = W - 2 * MARGIN   # printable width

# Cover page elements
story.append(Spacer(1, 20*mm))
story.append(Paragraph("UPSC CSE Prelims", S["title"]))
story.append(Paragraph("AI Mentor Analysis — 100 Selected Questions", S["sub"]))
story.append(Spacer(1, 4*mm))
story.append(HRFlowable(width=PW, thickness=2, color=C_DARK))
story.append(Spacer(1, 4*mm))
story.append(Paragraph(f"10 Questions × 10 Years (2015–2024)", S["sub"]))
story.append(Paragraph("Each entry: Full Question · Correct Answer · Trap Analysis · UPSC Pattern · Memory Lock", S["sub"]))
story.append(Spacer(1, 6*mm))
story.append(HRFlowable(width=PW, thickness=1, color=C_RULE))
story.append(Spacer(1, 20*mm))

cur_year = None
q_serial = 0

for q in qs:
    year = q["year_first"]
    q_serial += 1

    # Year separator
    if year != cur_year:
        if cur_year is not None:
            story.append(Spacer(1, 6*mm))
        cur_year = year
        story.append(HRFlowable(width=PW, thickness=2, color=C_YEAR))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(f"UPSC CSE {year}", S["year"]))
        story.append(Spacer(1, 2*mm))

    correct = (q.get("correct_option") or "").strip().lower()
    diff    = (q.get("difficulty") or "medium").capitalize()
    topic   = q.get("topic","")
    subtopic= q.get("subtopic","")
    topic_str = f"{topic} > {subtopic}" if subtopic else topic

    # ── Question block ─────────────────────────────────────────────────────
    block = []

    # Meta line
    meta = f"Q{q['q_num']}  ·  {topic_str}  ·  {diff}"
    block.append(Paragraph(clean(meta), S["q_meta"]))
    block.append(Spacer(1, 2*mm))

    # Question text
    block.append(Paragraph(clean(q["question"]), S["q_text"]))
    block.append(Spacer(1, 1*mm))

    # Options
    for ltr in ["a", "b", "c", "d"]:
        opt_text = q.get(f"option_{ltr}", "") or ""
        prefix = f"({ltr.upper()})  "
        if ltr == correct:
            block.append(Paragraph(
                f'<b>{clean(prefix + opt_text)} ✓</b>',
                S["opt_correct"]
            ))
        else:
            block.append(Paragraph(clean(prefix + opt_text), S["opt"]))

    block.append(Spacer(1, 3*mm))

    # ── AI sections ────────────────────────────────────────────────────────
    sections = parse_sections(q.get("ai_explanation",""))
    for hdr, body in sections:
        if not hdr and not body:
            continue
        bg, fg = section_color(hdr)

        # Section header pill
        hdr_para = Paragraph(clean(hdr), S["sec_hdr"])
        hdr_table = Table([[hdr_para]], colWidths=[PW])
        hdr_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("ROUNDEDCORNERS", [3,3,3,3]),
        ]))
        block.append(hdr_table)

        # Body text
        for para_text in body.split("\n\n"):
            para_text = para_text.strip()
            if not para_text:
                continue
            block.append(Paragraph(clean(para_text), S["sec_body"]))
            block.append(Spacer(1, 1.5*mm))

        block.append(Spacer(1, 2*mm))

    block.append(HRFlowable(width=PW, thickness=0.5, color=C_RULE))
    block.append(Spacer(1, 4*mm))

    story.append(KeepTogether(block[:10]))   # keep Q+first section together
    for item in block[10:]:
        story.append(item)

# Build
doc.build(story)
print(f"PDF saved: {OUT_PATH}")
print(f"Pages estimated: ~{len(qs)*2} (2 pages per question avg)")
