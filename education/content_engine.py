"""
Education content engine — 5 Claude Sonnet API calls.
Call 1: Excel cell comments
Call 2: PPT speaker notes
Call 3: PDF sections 1-6
Call 4: PDF sections 7-12
Call 5: Glossary (40 terms)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))

_MODEL      = "claude-sonnet-4-6"
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
    "Valuation Range",
    "Competitive Position",
    "Analyst Coverage",
    "Key Risks",
    "Investment Verdict",
]

_GLOSSARY_TERMS = (
    "DCF, WACC, EBITDA, EPS, P/E, EV/EBITDA, FCF, Beta, Terminal Value, Margin of Safety, "
    "Accretion, Dilution, Synergies, LBO, Goodwill, Intangibles, Working Capital, CapEx, "
    "Revenue, Gross Margin, Operating Margin, Net Margin, ROE, Debt/Equity, Net Debt, "
    "Current Ratio, Bear Case, Bull Case, Base Case, Comps, Moat, Switching Costs, ASIC, "
    "Hyperscaler, Beat/Miss, Consensus Estimate, Price Target, Initiating Coverage, "
    "Conviction, Sensitivity Analysis"
)

_FORBIDDEN = (
    "it is worth noting, importantly, it is clear that, in conclusion, it goes without saying, "
    "needless to say, at the end of the day, think of it like, imagine you are"
)


def _build_full_payload(ticker: str, stats: dict, fin_data: dict,
                         dcf_result: dict | None,
                         comp_result: dict | None = None,
                         cov_result: dict | None = None,
                         transcript_result: dict | None = None,
                         sec_result: dict | None = None) -> str:
    """Build a compact but complete data snapshot for education API calls."""
    info = stats.get("info", {})
    px   = stats.get("current_price")
    mktcap = info.get("marketCap")

    a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
    a_cf  = (fin_data.get("cash_flow") or {}).get("annual") or {}
    bs    = fin_data.get("balance_sheet") or {}

    rev_list  = a_inc.get("revenue", [])
    fcf_list  = a_cf.get("free_cash_flow", [])
    fcfm_list = a_cf.get("fcf_margin", [])
    gm_list   = a_inc.get("gross_margin", [])
    om_list   = a_inc.get("operating_margin", [])
    yoy_rev   = a_inc.get("yoy_revenue", [])

    payload = {
        "ticker":    ticker,
        "company":   info.get("shortName") or info.get("longName") or ticker,
        "sector":    info.get("sector", ""),
        "industry":  info.get("industry", ""),
        "price":     f"${px:,.2f}" if px else "N/A",
        "mktcap":    f"${mktcap/1e9:.1f}B" if mktcap else "N/A",
        "fpe":       f"{info.get('forwardPE'):.1f}x" if info.get("forwardPE") else "N/A",
        "pe_ttm":    f"{info.get('trailingPE'):.1f}x" if info.get("trailingPE") else "N/A",
        "revenue":   f"${rev_list[0]/1000:.1f}B" if rev_list and rev_list[0] else "N/A",
        "rev_growth":f"{yoy_rev[0]:+.1f}%" if yoy_rev and yoy_rev[0] else "N/A",
        "fcf":       f"${fcf_list[0]/1000:.1f}B" if fcf_list and fcf_list[0] else "N/A",
        "fcf_margin":f"{fcfm_list[0]:.1f}%" if fcfm_list and fcfm_list[0] else "N/A",
        "gross_margin": f"{gm_list[0]:.1f}%" if gm_list and gm_list[0] else "N/A",
        "op_margin":    f"{om_list[0]:.1f}%" if om_list and om_list[0] else "N/A",
        "net_debt":  f"${bs.get('net_debt', 0)/1000:.1f}B" if bs.get("net_debt") else "N/A",
        "cash":      f"${bs.get('cash', 0)/1000:.1f}B" if bs.get("cash") else "N/A",
    }

    if dcf_result and not dcf_result.get("error"):
        v = dcf_result.get("valuation", {})
        i = dcf_result.get("inputs", {})
        payload["dcf"] = {
            "intrinsic": f"${v.get('intrinsic'):.2f}" if v.get("intrinsic") else "N/A",
            "upside":    f"{v.get('upside_pct'):+.1f}%" if v.get("upside_pct") is not None else "N/A",
            "wacc":      f"{i.get('wacc'):.2f}%" if i.get("wacc") else "N/A",
            "tv_pct":    f"{v.get('tv_pct'):.1f}%" if v.get("tv_pct") else "N/A",
            "rev_cagr":  f"{i.get('rev_cagr'):.1f}%" if i.get("rev_cagr") else "N/A",
        }

    if comp_result and not comp_result.get("error"):
        med = comp_result.get("peer_medians", {})
        rks = comp_result.get("rankings", {})
        cd  = comp_result.get("claude") or {}
        payload["comp"] = {
            "peer_median_fpe": f"{med.get('fpe'):.1f}x" if med.get("fpe") else "N/A",
            "peer_median_gm":  f"{med.get('gross_margin'):.1f}%" if med.get("gross_margin") else "N/A",
            "moat_type":     cd.get("moat_type", "N/A") if isinstance(cd, dict) else "N/A",
            "moat_strength": cd.get("moat_strength", "N/A") if isinstance(cd, dict) else "N/A",
            "rev_growth_rank": rks.get("rev_growth", "N/A"),
            "gm_rank":         rks.get("gross_margin", "N/A"),
        }

    if cov_result and not cov_result.get("error"):
        payload["coverage"] = {
            "consensus":    cov_result.get("consensus_rating", "N/A"),
            "n_analysts":   cov_result.get("total_analysts", 0),
            "mean_target":  f"${cov_result.get('mean_target'):.2f}" if cov_result.get("mean_target") else "N/A",
            "upside":       f"{cov_result.get('upside_pct'):+.1f}%" if cov_result.get("upside_pct") is not None else "N/A",
            "bull_ratio":   f"{cov_result.get('bull_ratio'):.1f}%" if cov_result.get("bull_ratio") is not None else "N/A",
        }

    if transcript_result and not transcript_result.get("error"):
        payload["earnings"] = {
            "beat_streak":  transcript_result.get("beat_streak", 0),
            "beat_count":   transcript_result.get("beat_count", 0),
            "total_qtrs":   transcript_result.get("total_quarters", 0),
            "tone":         transcript_result.get("tone_label", "N/A"),
            "last_surprise":f"{transcript_result.get('last_eps_surprise'):+.2f}%" if transcript_result.get("last_eps_surprise") else "N/A",
            "next_date":    transcript_result.get("next_earnings_date", "N/A"),
        }

    if sec_result and not sec_result.get("error"):
        payload["sec"] = {
            "10k_date": sec_result.get("latest_10k_date", "N/A"),
            "mda_tone": sec_result.get("tone_signals", {}).get("tone_label", "N/A"),
            "top_risks": [r.get("title", "")[:70] for r in (sec_result.get("top_risks") or [])[:3]],
        }

    return json.dumps(payload, indent=2)


def _validate_sections(sections: dict) -> bool:
    """Raise ValueError if any section is too short or has an empty label."""
    for name, content in sections.items():
        if len(content.strip()) < 150:
            raise ValueError(f"Section '{name}' too short: {len(content.strip())} chars")
        if re.search(r'\b\w+:\s*$', content, re.MULTILINE):
            raise ValueError(f"Section '{name}' has empty label at end of line")
    return True


def _education_system_prompt(company_name: str, ticker: str, aud_label: str, aud_tone: str) -> str:
    return (
        f"You are a finance professor at a top business school who also worked 10 years at a "
        f"sell-side research desk. You are writing a companion guide to an equity research report "
        f"on {company_name} ({ticker}) for a {aud_label}.\n\n"
        f"{aud_tone}\n\n"
        f"Rules:\n"
        f"- Write directly using the actual numbers provided in the data\n"
        f"- Every section must contain at least one specific number from the data\n"
        f"- Never use a section label followed by empty content. If you cannot fill a section, "
        f"skip the label entirely\n"
        f"- Never leave a colon with nothing after it\n"
        f"- Write in plain English that a sharp undergraduate can follow\n"
        f"- Forbidden phrases: {_FORBIDDEN}\n"
        f"- No em-dashes as sentence connectors. Use periods.\n"
        f"- Minimum 200 words per section\n"
        f"- If data is unavailable for a specific point, say so directly rather than writing generically\n"
        f"- Never reference a different company. Only discuss {company_name} ({ticker})\n"
        f"- Use specific numbers from the data payload in every section"
    )


def run_content_engine(
    ticker: str,
    stats: dict,
    fin_data: dict,
    dcf_result: dict | None,
    audience: str = "student",
    comp_result: dict | None = None,
    cov_result: dict | None = None,
    transcript_result: dict | None = None,
    sec_result: dict | None = None,
) -> dict:
    """
    Makes 5 Claude Sonnet API calls:
    1. Excel cell comments
    2. PPT speaker notes
    3. PDF sections 1-6
    4. PDF sections 7-12
    5. Glossary (40 terms)
    Returns {"excel_comments": dict, "ppt_notes": list, "pdf_content": str, ...}
    """
    client = anthropic.Anthropic()
    info       = stats.get("info", {})
    name       = info.get("shortName") or info.get("longName") or ticker
    aud_label  = "college finance student" if audience == "student" else "finance professional (CFA/MBA level)"
    aud_tone   = (
        "Use plain English. Avoid jargon. Define every acronym on first use. "
        "Explain concepts by connecting them to real-world outcomes."
        if audience == "student"
        else "Use precise professional terminology. Emphasize analytical rigor and institutional investor framing."
    )

    full_payload = _build_full_payload(
        ticker, stats, fin_data, dcf_result,
        comp_result, cov_result, transcript_result, sec_result,
    )
    edu_system = _education_system_prompt(name, ticker, aud_label, aud_tone)

    # ── CALL 1: Excel cell comments ───────────────────────────────────────────
    terms_str = ", ".join(_EXCEL_TERMS)
    r1 = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=edu_system,
        messages=[{"role": "user", "content": (
            f"Write Excel cell comments for a {name} ({ticker}) financial analysis workbook.\n\n"
            f"Full data:\n{full_payload}\n\n"
            f"Write a JSON object where each key is a metric name and the value is a 2-sentence "
            f"comment using {ticker}'s actual numbers from the data above.\n\n"
            f"Metrics: {terms_str}\n\n"
            f"Return ONLY valid JSON. No markdown, no explanation.\n"
            f'Format: {{"{_EXCEL_TERMS[0]}": "comment using real numbers", ...}}'
        )}],
    )
    try:
        text1 = r1.content[0].text.strip()
        if text1.startswith("```"):
            text1 = text1.split("```")[1]
            if text1.startswith("json"):
                text1 = text1[4:]
        start = text1.find("{")
        end   = text1.rfind("}") + 1
        excel_comments = json.loads(text1[start:end]) if start >= 0 else {}
    except Exception as exc:
        print(f"  [education] Excel comments parse error: {exc}", file=sys.stderr)
        excel_comments = {}

    # ── CALL 2: PPT speaker notes ─────────────────────────────────────────────
    slides_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(_SLIDE_TITLES))
    r2 = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=edu_system,
        messages=[{"role": "user", "content": (
            f"Write speaker notes for a {name} ({ticker}) pitch deck.\n\n"
            f"Full data:\n{full_payload}\n\n"
            f"Write speaker notes for each of these 12 slides. Each note must reference "
            f"specific numbers from the data above. Minimum 100 words per slide.\n\n"
            f"Slides:\n{slides_str}\n\n"
            f"Return ONLY a JSON array with 12 objects. No markdown, no explanation.\n"
            f'Format: [{{"slide": 1, "title": "Cover / Title", "notes": "speaker notes here"}}, ...]'
        )}],
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
    except Exception as exc:
        print(f"  [education] PPT notes parse error: {exc}", file=sys.stderr)
        ppt_notes = []

    # ── CALL 3: PDF sections 1-6 ──────────────────────────────────────────────
    sections_1_6_prompt = (
        f"Write sections 1 through 6 of a companion guide for the {name} ({ticker}) "
        f"equity research report.\n\n"
        f"Full data:\n{full_payload}\n\n"
        f"Write exactly these 6 sections. Each section must be at least 200 words. "
        f"Every section must contain specific numbers from the data. "
        f"Use the numbered format: '1. Section Title' on its own line, then the content.\n\n"
        f"1. How to Read This Report\n"
        f"Explain the structure of the research report and what each section tells the reader. "
        f"Reference the actual rating and price target from the data.\n\n"
        f"2. {name}'s Business Model\n"
        f"Explain specifically how {name} makes money. Use revenue, margins, and segment data from above.\n\n"
        f"3. Key Financial Metrics\n"
        f"Explain what the most important metrics are for this specific company and why. "
        f"Reference the actual FCF margin, gross margin, and revenue growth from the data.\n\n"
        f"4. DCF Valuation\n"
        f"Explain step by step how the DCF was calculated for {name}. "
        f"Use the actual WACC, terminal growth, and intrinsic value from the data.\n\n"
        f"5. Reading the Comparable Companies Table\n"
        f"Explain what the comps table shows. Reference the actual peer median P/E and "
        f"{ticker}'s forward P/E from the data.\n\n"
        f"6. Understanding Sensitivity Analysis\n"
        f"Explain what the sensitivity table shows and why WACC and terminal growth rate matter. "
        f"Use specific numbers from the DCF data."
    )

    for attempt in range(2):
        r3 = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=edu_system,
            messages=[{"role": "user", "content": sections_1_6_prompt}],
        )
        sections_1_6_text = r3.content[0].text.strip()
        try:
            _validate_sections({"sections_1_6": sections_1_6_text})
            break
        except ValueError as exc:
            if attempt == 0:
                print(f"  [education] Sections 1-6 validation failed (retrying): {exc}", file=sys.stderr)
            else:
                print(f"  [education] Sections 1-6 validation failed after retry: {exc}", file=sys.stderr)

    # ── CALL 4: PDF sections 7-12 ─────────────────────────────────────────────
    sections_7_12_prompt = (
        f"Write sections 7 through 12 of a companion guide for the {name} ({ticker}) "
        f"equity research report.\n\n"
        f"Full data:\n{full_payload}\n\n"
        f"Write exactly these 6 sections. Each section must be at least 200 words. "
        f"Every section must contain specific numbers from the data. "
        f"Use the numbered format: '7. Section Title' on its own line, then the content.\n\n"
        f"7. Risk Factors\n"
        f"Explain the specific risks to this investment. Reference actual risk factors from the SEC "
        f"filing data and the bear case. Do not write generic risk language.\n\n"
        f"8. Investment Scenarios\n"
        f"Write the bull case, base case, and bear case price targets with their specific assumptions. "
        f"The base case target is the analyst consensus target from the coverage data. "
        f"Bull case = 15% above base. Bear case = 25% below current price. "
        f"State specific revenue growth and margin assumptions for each scenario.\n\n"
        f"9. Insider and Institutional Signals\n"
        f"Explain what insider buying and selling patterns signal for this stock. "
        f"Use the insider data from the payload. If no recent insider transactions, say so directly.\n\n"
        f"10. Earnings Beats and Misses\n"
        f"Explain the earnings beat/miss history. Reference the actual beat streak and beat count "
        f"from the earnings data. Explain what consistent beats mean for the stock price.\n\n"
        f"11. How to Track This Investment\n"
        f"List the specific metrics and dates to monitor for {name}. Include the next earnings date "
        f"from the data and specific things to watch for.\n\n"
        f"12. Data Sources and Methodology\n"
        f"Explain where the data in this report came from and how the analysis was built. "
        f"Reference yfinance, FMP, and SEC EDGAR as sources."
    )

    for attempt in range(2):
        r4 = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=edu_system,
            messages=[{"role": "user", "content": sections_7_12_prompt}],
        )
        sections_7_12_text = r4.content[0].text.strip()
        try:
            _validate_sections({"sections_7_12": sections_7_12_text})
            break
        except ValueError as exc:
            if attempt == 0:
                print(f"  [education] Sections 7-12 validation failed (retrying): {exc}", file=sys.stderr)
            else:
                print(f"  [education] Sections 7-12 validation failed after retry: {exc}", file=sys.stderr)

    # ── CALL 5: Glossary ──────────────────────────────────────────────────────
    r5 = client.messages.create(
        model=_MODEL,
        max_tokens=2000,
        system=f"Define each term in 1-2 sentences. Use concrete examples from {ticker} data where available. Never truncate. Complete all 40 terms. No filler. No hedging.",
        messages=[{"role": "user", "content": (
            f"Full {ticker} data:\n{full_payload}\n\n"
            f"Define all 40 of these finance terms. For each one, provide a 1-2 sentence definition "
            f"and, where the {ticker} data provides a concrete example, use it.\n\n"
            f"Terms: {_GLOSSARY_TERMS}\n\n"
            f"Format each entry as: TERM: definition.\n"
            f"Start with 'GLOSSARY' on its own line, then list all 40 terms."
        )}],
    )
    glossary_text = r5.content[0].text.strip()

    pdf_content = sections_1_6_text + "\n\n" + sections_7_12_text + "\n\n" + glossary_text

    return {
        "ticker":        ticker,
        "company_name":  name,
        "audience":      audience,
        "excel_comments": excel_comments,
        "ppt_notes":     ppt_notes,
        "pdf_content":   pdf_content,
        "error":         None,
    }
