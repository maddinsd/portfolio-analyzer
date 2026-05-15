"""
Education content engine — exactly 3 Claude Sonnet API calls.
Generates all educational content for Excel comments, PPT notes, and companion PDF.
Never uses Haiku. Never exceeds 3 API calls.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096

_EXCEL_TERMS = [
    "Revenue", "Gross Profit", "EBITDA", "EBIT", "Net Income", "EPS",
    "P/E Ratio", "EV/EBITDA", "Price/Sales", "Gross Margin", "EBITDA Margin",
    "Net Margin", "Return on Equity", "Current Ratio", "Debt/Equity",
    "Free Cash Flow", "WACC", "Terminal Growth Rate", "Intrinsic Value",
    "Margin of Safety", "Beta", "Dividend Yield", "Book Value",
    "Operating Cash Flow", "CapEx", "Enterprise Value", "Market Cap",
    "Price Target", "Upside", "Conviction Score",
]

_SLIDE_TITLES = [
    "Cover / Title",
    "Investment Summary",
    "Company Overview",
    "Industry & Market Position",
    "Financial Highlights",
    "DCF Valuation",
    "Comparable Companies Analysis",
    "Risk Factors",
    "Investment Thesis",
    "Financial Projections",
    "Appendix: DCF Assumptions",
    "Appendix: Key Metrics",
]


def _company_ctx(ticker: str, stats: dict, fin_data: dict, dcf_result: dict | None) -> str:
    name = stats.get("name") or ticker
    px = stats.get("price", 0)
    mktcap = stats.get("market_cap", 0)
    rev_list = fin_data.get("revenue") or []
    rev = rev_list[-1] if rev_list else 0
    ebitda_list = fin_data.get("ebitda") or []
    ebitda = ebitda_list[-1] if ebitda_list else 0
    dcf_iv = 0.0
    dcf_up = 0.0
    if dcf_result and not dcf_result.get("error"):
        dcf_iv = dcf_result.get("valuation", {}).get("intrinsic", 0)
        dcf_up = dcf_result.get("valuation", {}).get("upside_pct", 0)
    return (
        f"{name} ({ticker}): price=${px:.2f}, mktcap=${mktcap/1e9:.1f}B, "
        f"LTM_revenue=${rev:.0f}M, LTM_EBITDA=${ebitda:.0f}M, "
        f"DCF_intrinsic=${dcf_iv:.2f} ({dcf_up:+.1f}% upside)"
    )


def run_content_engine(
    ticker: str,
    stats: dict,
    fin_data: dict,
    dcf_result: dict | None,
    audience: str = "student",
) -> dict:
    """
    Makes exactly 3 Claude Sonnet API calls.
    Returns {"excel_comments": dict, "ppt_notes": list, "pdf_content": str, ...}
    """
    client = anthropic.Anthropic()
    ctx = _company_ctx(ticker, stats, fin_data, dcf_result)
    name = stats.get("name") or ticker
    aud_label = "college finance student" if audience == "student" else "finance professional (CFA/MBA level)"
    aud_tone  = (
        "Use plain English, relatable analogies, and avoid jargon. Define every acronym."
        if audience == "student"
        else "Use precise professional terminology. Emphasize analytical rigor, data interpretation, and institutional investor framing."
    )

    # ── API CALL 1: Excel cell comments ──────────────────────────────────────
    terms_str = ", ".join(_EXCEL_TERMS)
    r1 = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": (
                f"You are writing Excel cell comments for a {name} ({ticker}) financial analysis workbook "
                f"for a {aud_label}.\n\n"
                f"Company context: {ctx}\n\n"
                f"{aud_tone}\n\n"
                f"Write a JSON object where each key is a metric name and the value is a 2-sentence comment "
                f"specific to {ticker} — reference actual numbers from the company context where helpful.\n\n"
                f"Metrics: {terms_str}\n\n"
                f"Return ONLY valid JSON. No markdown, no explanation. Format:\n"
                f'{{"{_EXCEL_TERMS[0]}": "comment text here", ...}}'
            ),
        }],
    )
    try:
        text1 = r1.content[0].text.strip()
        # Strip markdown fences if present
        if text1.startswith("```"):
            text1 = text1.split("```")[1]
            if text1.startswith("json"):
                text1 = text1[4:]
        start = text1.find("{")
        end   = text1.rfind("}") + 1
        excel_comments = json.loads(text1[start:end]) if start >= 0 else {}
    except Exception:
        excel_comments = {}

    # ── API CALL 2: PPT slide notes ───────────────────────────────────────────
    slides_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(_SLIDE_TITLES))
    r2 = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": (
                f"You are writing speaker notes for a {name} ({ticker}) pitch deck "
                f"being presented to a {aud_label}.\n\n"
                f"Company context: {ctx}\n\n"
                f"{aud_tone}\n\n"
                f"Write speaker notes for each of these 12 slides. Notes should help the presenter "
                f"explain the slide content and handle likely audience questions.\n\n"
                f"Slides:\n{slides_str}\n\n"
                f"Return ONLY a JSON array with 12 objects. No markdown, no explanation. Format:\n"
                f'[{{"slide": 1, "title": "Cover / Title", "notes": "speaker notes here"}}, ...]'
            ),
        }],
    )
    try:
        text2 = r2.content[0].text.strip()
        if text2.startswith("```"):
            text2 = text2.split("```")[1]
            if text2.startswith("json"):
                text2 = text2[4:]
        start = text2.find("[")
        end   = text2.rfind("]") + 1
        ppt_notes = json.loads(text2[start:end]) if start >= 0 else []
    except Exception:
        ppt_notes = []

    # ── API CALL 3: Companion PDF content ─────────────────────────────────────
    r3 = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": (
                f"You are writing a companion guide for a {name} ({ticker}) equity research report "
                f"for a {aud_label}.\n\n"
                f"Company context: {ctx}\n\n"
                f"{aud_tone}\n\n"
                f"Write these 12 sections (each exactly 120-150 words), then a 40-term glossary.\n\n"
                f"SECTIONS:\n"
                f"1. How to Read This Report\n"
                f"2. {name}'s Business Model — How the Company Makes Money\n"
                f"3. Key Financial Metrics — What to Watch\n"
                f"4. DCF Valuation — How We Calculated the Price Target\n"
                f"5. Reading the Comparable Companies Table\n"
                f"6. Understanding Sensitivity Analysis\n"
                f"7. Risk Factors — What Could Go Wrong\n"
                f"8. Bull Case vs Bear Case\n"
                f"9. Insider & Institutional Signals\n"
                f"10. Earnings Beats and Misses — What the Track Record Shows\n"
                f"11. How to Track This Investment Going Forward\n"
                f"12. Data Sources and Methodology\n\n"
                f"GLOSSARY:\n"
                f"Write 40 terms in format: TERM: definition (1-2 sentences, equity research context).\n"
                f"Include: DCF, WACC, EBITDA, EPS, P/E, EV/EBITDA, Free Cash Flow, Beta, Terminal Value, "
                f"Margin of Safety, Accretion, Dilution, Synergies, LBO, Goodwill, Intangibles, "
                f"Working Capital, CapEx, D&A, EBIT, Gross Margin, Net Margin, ROE, ROA, ROIC, "
                f"Current Ratio, Debt/Equity, Interest Coverage, Enterprise Value, Market Cap, "
                f"Short Interest, Float, Insider Ownership, Institutional Ownership, "
                f"Price Target, Consensus Rating, Alpha, Beta, Sharpe Ratio, "
                f"Book Value, Tangible Book Value.\n\n"
                f"Reference {ticker}'s actual numbers where relevant. Be specific, not generic."
            ),
        }],
    )
    pdf_content = r3.content[0].text

    return {
        "ticker": ticker,
        "company_name": name,
        "audience": audience,
        "excel_comments": excel_comments,
        "ppt_notes": ppt_notes,
        "pdf_content": pdf_content,
        "context": ctx,
        "error": None,
    }
