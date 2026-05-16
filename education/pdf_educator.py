"""
Companion PDF generator — produces a 12-section guide + 40-term glossary.
Uses reportlab with Times New Roman. No API calls — receives pre-generated content.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Design constants ──────────────────────────────────────────────────────────
_NAVY  = colors.HexColor("#003366")
_STEEL = colors.HexColor("#1F4E79")
_GREY  = colors.HexColor("#595959")
_LIGHT = colors.HexColor("#D9E1F2")
_WHITE = colors.white
_UC_RED = colors.HexColor("#E00122")

# Sheet names after Bull vs Bear removal
_SHEET_RENAMES = {
    "Bull vs Bear": "Analysis",
    "Bull/Bear": "Analysis",
    "bull vs bear": "Analysis",
}


def _styles(audience: str) -> dict:
    def _p(name, **kw) -> ParagraphStyle:
        kw.setdefault("fontName", "Times-Roman")
        return ParagraphStyle(name, **kw)

    return {
        "cover_title":  _p("cover_title",  fontSize=28, leading=34,
                            textColor=_NAVY, fontName="Times-Bold", spaceAfter=8),
        "cover_sub":    _p("cover_sub",    fontSize=13, leading=17,
                            textColor=_STEEL, spaceAfter=4),
        "cover_meta":   _p("cover_meta",   fontSize=10, leading=14,
                            textColor=_GREY, spaceAfter=2),
        "section_hdr":  _p("section_hdr",  fontSize=13, leading=17,
                            textColor=_WHITE, fontName="Times-Bold",
                            backColor=_NAVY, leftIndent=0, rightIndent=0,
                            borderPadding=(5, 8, 5, 8), spaceAfter=6,
                            spaceBefore=12, keepWithNext=1),
        "body":         _p("body",         fontSize=10, leading=15,
                            textColor=colors.black, spaceAfter=8),
        "body_bullet":  _p("body_bullet",  fontSize=10, leading=14,
                            textColor=colors.black, leftIndent=14,
                            spaceAfter=4),
        "gloss_term":   _p("gloss_term",   fontSize=10, leading=13,
                            textColor=_NAVY, fontName="Times-Bold", spaceAfter=2),
        "gloss_def":    _p("gloss_def",    fontSize=9,  leading=13,
                            textColor=_GREY, leftIndent=12, spaceAfter=8),
        "toc_entry":    _p("toc_entry",    fontSize=10, leading=15,
                            textColor=colors.black),
        "toc_hdr":      _p("toc_hdr",      fontSize=11, leading=15,
                            textColor=_NAVY, fontName="Times-Bold"),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    canvas.setFont("Times-Italic", 8)
    canvas.setFillColor(_GREY)
    canvas.drawString(0.75 * inch, 0.5 * inch,
                      "University of Cincinnati | Lindner College of Business — Education Guide")
    canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _md_to_html(text: str) -> str:
    """Convert common markdown markers to reportlab-compatible XML tags."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__",     r"<b>\1</b>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*",     r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_",       r"<i>\1</i>", text)
    # Strip leading markdown heading markers
    text = re.sub(r"^#{1,4}\s+", "", text, flags=re.MULTILINE)
    # Inline code → bold
    text = re.sub(r"`(.+?)`",       r"<b>\1</b>", text)
    return text


def _clean_title(title: str) -> str:
    """Strip markdown decoration from section headers."""
    title = re.sub(r"^#+\s*", "", title)
    title = re.sub(r"\*+", "", title)
    title = title.replace("■", "").replace("•", "").strip()
    # Replace stale sheet names
    for old, new in _SHEET_RENAMES.items():
        title = title.replace(old, new)
    return title


def _fix_sheet_refs(text: str) -> str:
    """Replace removed 'Bull vs Bear' sheet references with correct names."""
    for old, new in _SHEET_RENAMES.items():
        text = text.replace(old, new)
    return text


def _parse_sections(pdf_content: str) -> tuple[list[tuple[str, str, list[str]]], list[tuple[str, str]]]:
    """
    Parse structured text into sections and glossary.
    Returns:
      sections: [(title, intro_para, [bullet_strings])]
      glossary: [(term, definition)]
    """
    sections: list[tuple[str, str, list[str]]] = []
    glossary: list[tuple[str, str]] = []

    in_glossary = False
    current_title = ""
    current_body: list[str] = []
    current_bullets: list[str] = []

    def _flush():
        nonlocal current_title, current_body, current_bullets
        if current_title:
            body_text = " ".join(current_body).strip()
            body_text = _fix_sheet_refs(body_text)
            sections.append((current_title, body_text, list(current_bullets)))
        current_title = ""
        current_body = []
        current_bullets = []

    for line in pdf_content.splitlines():
        stripped = line.strip()

        # Detect glossary section
        if re.match(r"^GLOSSARY\s*$", stripped, re.IGNORECASE):
            _flush()
            in_glossary = True
            continue

        if in_glossary:
            # Match: "**Term**:" or "Term:" (supports title-case, mixed-case)
            m = re.match(r"^\**([A-Za-z][A-Za-z0-9 /()&,.-]{1,50})\**\s*:\s*(.+)$", stripped)
            if m:
                glossary.append((m.group(1).strip(), m.group(2).strip()))
            continue

        # Detect numbered section headers: "1. Title", "## 1. Title", "**1. Title**"
        m = re.match(r"^(?:#{1,3}\s*)?(?:\*+)?(\d{1,2})\.\s+(.+?)(?:\*+)?$", stripped)
        if m:
            _flush()
            raw_title = f"{m.group(1)}. {m.group(2)}"
            current_title = _clean_title(raw_title)
            continue

        if not current_title:
            continue

        # Bullet lines
        if re.match(r"^[-•*]\s+", stripped):
            bullet_text = re.sub(r"^[-•*]\s+", "", stripped)
            current_bullets.append(_fix_sheet_refs(bullet_text))
        elif stripped:
            current_body.append(stripped)

    _flush()
    return sections, glossary


def _render_body_paragraphs(body_text: str, bullets: list[str], styles: dict) -> list:
    """Convert section body + bullets to reportlab flowables."""
    flowables = []
    if body_text:
        safe = _md_to_html(body_text)
        flowables.append(Paragraph(safe, styles["body"]))
    for b in bullets:
        safe_b = _md_to_html(b)
        flowables.append(Paragraph(f"•  {safe_b}", styles["body_bullet"]))
    return flowables


def build_companion_pdf(
    ticker: str,
    content: dict,
    out_path: str,
    audience: str = "student",
) -> dict:
    """
    Builds companion PDF from pre-generated content dict.
    Returns {"error": None} or {"error": "message"}.
    """
    try:
        S = _styles(audience)
        company_name = content.get("company_name", ticker)
        pdf_content  = content.get("pdf_content", "")
        today        = date.today().strftime("%B %d, %Y")
        aud_label    = "Student Edition" if audience == "student" else "Professional Edition"

        doc = SimpleDocTemplate(
            out_path,
            pagesize=letter,
            leftMargin=0.85 * inch,
            rightMargin=0.85 * inch,
            topMargin=1.0 * inch,
            bottomMargin=0.9 * inch,
        )

        story = []

        # ── Cover page ────────────────────────────────────────────────────────
        story.append(Spacer(1, 1.0 * inch))
        story.append(Paragraph(f"{company_name} ({ticker})", S["cover_title"]))
        story.append(Paragraph("Equity Research — Companion Guide", S["cover_sub"]))
        story.append(Paragraph(aud_label, S["cover_sub"]))
        story.append(Spacer(1, 0.3 * inch))
        story.append(HRFlowable(width="100%", thickness=2, color=_NAVY))
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(f"University of Cincinnati | Lindner College of Business", S["cover_meta"]))
        story.append(Paragraph(f"Generated: {today}", S["cover_meta"]))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            "This guide explains every section of the equity research workbook in plain terms. "
            "Use it alongside the Excel report, pitch deck, and research PDF.",
            S["body"],
        ))
        story.append(PageBreak())

        # ── Parse sections up front (needed for TOC) ──────────────────────────
        sections, glossary = _parse_sections(pdf_content)

        # ── Table of contents ─────────────────────────────────────────────────
        story.append(Paragraph("Contents", S["cover_title"]))
        story.append(Spacer(1, 0.15 * inch))

        # Build TOC rows from actual section titles
        toc_data = [["Section", "Page"]]
        if sections:
            for title, _, _ in sections:
                toc_data.append([title, "…"])
        else:
            for i in range(1, 13):
                toc_data.append([f"{i}. Guide Section", "…"])
        toc_data.append(["Glossary (Financial Terms)", "…"])

        toc_table = Table(toc_data, colWidths=[5.2 * inch, 1.3 * inch])
        toc_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  _NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
            ("FONTNAME",      (0, 0), (-1, 0),  "Times-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN",         (1, 0), (1, -1),  "CENTER"),
        ]))
        story.append(toc_table)
        story.append(PageBreak())

        # ── Guide sections ────────────────────────────────────────────────────
        for title, body_text, bullets in sections:
            block = [Paragraph(title, S["section_hdr"])]
            block += _render_body_paragraphs(body_text, bullets, S)
            story.append(KeepTogether(block[:3]))   # keep header + first para together
            if len(block) > 3:
                for item in block[3:]:
                    story.append(item)
            story.append(Spacer(1, 0.08 * inch))

        # Fallback if parsing produced nothing
        if not sections and pdf_content:
            for chunk in pdf_content.split("\n\n"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if re.match(r"^\d{1,2}\.", chunk[:6]):
                    story.append(Paragraph(_clean_title(chunk[:80]), S["section_hdr"]))
                else:
                    story.append(Paragraph(_md_to_html(chunk), S["body"]))

        story.append(PageBreak())

        # ── Glossary ──────────────────────────────────────────────────────────
        story.append(Paragraph("Glossary", S["section_hdr"]))
        story.append(Spacer(1, 0.1 * inch))

        if glossary:
            for term, definition in glossary:
                clean_def = _md_to_html(definition)
                entry = [
                    Paragraph(term, S["gloss_term"]),
                    Paragraph(clean_def, S["gloss_def"]),
                ]
                story.append(KeepTogether(entry))
        else:
            # Broadened fallback: title-case terms
            for line in pdf_content.splitlines():
                m = re.match(
                    r"^\**([A-Za-z][A-Za-z0-9 /()&,.-]{1,50})\**\s*:\s*(.+)$",
                    line.strip(),
                )
                if m:
                    story.append(Paragraph(m.group(1).strip(), S["gloss_term"]))
                    story.append(Paragraph(_md_to_html(m.group(2).strip()), S["gloss_def"]))

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

        return {"error": None, "path": out_path}

    except Exception as exc:
        import traceback
        return {"error": str(exc), "traceback": traceback.format_exc()}
