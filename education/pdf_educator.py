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
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
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


def _styles(audience: str) -> dict:
    base = getSampleStyleSheet()

    def _p(name, **kw) -> ParagraphStyle:
        kw.setdefault("fontName", "Times-Roman")
        return ParagraphStyle(name, **kw)

    return {
        "cover_title": _p("cover_title", fontSize=26, leading=32,
                           textColor=_NAVY, fontName="Times-Bold", spaceAfter=6),
        "cover_sub":   _p("cover_sub",   fontSize=14, leading=18,
                           textColor=_STEEL, spaceAfter=4),
        "cover_meta":  _p("cover_meta",  fontSize=10, leading=14,
                           textColor=_GREY, spaceAfter=2),
        "section_hdr": _p("section_hdr", fontSize=14, leading=18,
                           textColor=_WHITE, fontName="Times-Bold",
                           backColor=_NAVY, leftIndent=-6, rightIndent=-6,
                           borderPadding=(4, 6, 4, 6), spaceAfter=6),
        "body":        _p("body",        fontSize=10, leading=15,
                           textColor=colors.black, spaceAfter=8),
        "gloss_term":  _p("gloss_term",  fontSize=10, leading=13,
                           textColor=_NAVY, fontName="Times-Bold", spaceAfter=2),
        "gloss_def":   _p("gloss_def",   fontSize=9,  leading=13,
                           textColor=_GREY, leftIndent=12, spaceAfter=6),
        "footer":      _p("footer",      fontSize=8,  leading=10,
                           textColor=_GREY),
        "toc_entry":   _p("toc_entry",   fontSize=10, leading=14,
                           textColor=colors.black),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    canvas.setFont("Times-Italic", 8)
    canvas.setFillColor(_GREY)
    canvas.drawString(0.75 * inch, 0.5 * inch, f"University of Cincinnati | Lindner College of Business — Education Guide")
    canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _parse_sections(pdf_content: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Parses the structured text from content_engine into:
    - sections: [(title, body), ...]
    - glossary: [(term, definition), ...]
    """
    sections: list[tuple[str, str]] = []
    glossary: list[tuple[str, str]] = []

    in_glossary = False
    current_title = ""
    current_body: list[str] = []

    for line in pdf_content.splitlines():
        stripped = line.strip()

        # Detect glossary section start
        if re.match(r"^GLOSSARY\s*$", stripped, re.IGNORECASE):
            if current_title:
                sections.append((current_title, " ".join(current_body).strip()))
            current_title = ""
            current_body = []
            in_glossary = True
            continue

        if in_glossary:
            # "TERM: definition" or "**TERM**: definition"
            m = re.match(r"^\**([A-Z][A-Z/() ]{1,40})\**:\s*(.+)$", stripped)
            if m:
                glossary.append((m.group(1).strip(), m.group(2).strip()))
            continue

        # Detect numbered section header: "1. Title" or "## 1. Title"
        m = re.match(r"^(?:#{1,3}\s*)?(\d{1,2})\.\s+(.+)$", stripped)
        if m:
            if current_title:
                sections.append((current_title, " ".join(current_body).strip()))
            current_title = f"{m.group(1)}. {m.group(2)}"
            current_body = []
            continue

        if current_title and stripped:
            current_body.append(stripped)

    if current_title:
        sections.append((current_title, " ".join(current_body).strip()))

    return sections, glossary


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
        ctx = content.get("context", "")
        pdf_content = content.get("pdf_content", "")
        today = date.today().strftime("%B %d, %Y")
        aud_label = "Student Edition" if audience == "student" else "Professional Edition"

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
        story.append(Spacer(1, 1.2 * inch))
        story.append(Paragraph(f"{company_name} ({ticker})", S["cover_title"]))
        story.append(Paragraph("Equity Research — Companion Guide", S["cover_sub"]))
        story.append(Paragraph(aud_label, S["cover_sub"]))
        story.append(Spacer(1, 0.3 * inch))
        story.append(HRFlowable(width="100%", thickness=1.5, color=_NAVY))
        story.append(Spacer(1, 0.2 * inch))
        if ctx:
            story.append(Paragraph(ctx, S["cover_meta"]))
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(f"Generated: {today}", S["cover_meta"]))
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(
            "This guide explains every section of the equity research workbook in plain terms. "
            "Use it alongside the Excel report and pitch deck.",
            S["body"],
        ))
        story.append(PageBreak())

        # ── Table of contents (simple) ────────────────────────────────────────
        story.append(Paragraph("Contents", S["cover_title"]))
        story.append(Spacer(1, 0.15 * inch))
        toc_data = [
            ["Section", "Page"],
            ["1–12. Guide Sections", "3+"],
            ["Glossary (40 Terms)", "—"],
        ]
        toc_table = Table(toc_data, colWidths=[5 * inch, 1.5 * inch])
        toc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR",  (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(toc_table)
        story.append(PageBreak())

        # ── Guide sections ────────────────────────────────────────────────────
        sections, glossary = _parse_sections(pdf_content)

        for title, body in sections:
            story.append(Paragraph(title, S["section_hdr"]))
            if body:
                story.append(Paragraph(body, S["body"]))
            story.append(Spacer(1, 0.1 * inch))

        # If parsing produced nothing, fall back to raw content blocks
        if not sections:
            for chunk in pdf_content.split("\n\n"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if re.match(r"^\d{1,2}\.", chunk[:6]):
                    story.append(Paragraph(chunk[:80], S["section_hdr"]))
                else:
                    story.append(Paragraph(chunk, S["body"]))

        story.append(PageBreak())

        # ── Glossary ──────────────────────────────────────────────────────────
        story.append(Paragraph("Glossary", S["section_hdr"]))
        story.append(Spacer(1, 0.1 * inch))

        if glossary:
            for term, definition in glossary:
                story.append(Paragraph(term, S["gloss_term"]))
                story.append(Paragraph(definition, S["gloss_def"]))
        else:
            # Fallback: look for TERM: definition patterns in raw content
            for line in pdf_content.splitlines():
                m = re.match(r"^\**([A-Z][A-Z/() ]{1,40})\**:\s*(.+)$", line.strip())
                if m:
                    story.append(Paragraph(m.group(1).strip(), S["gloss_term"]))
                    story.append(Paragraph(m.group(2).strip(), S["gloss_def"]))

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

        return {"error": None, "path": out_path}

    except Exception as exc:
        import traceback
        return {"error": str(exc), "traceback": traceback.format_exc()}
