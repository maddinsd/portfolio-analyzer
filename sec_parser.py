from __future__ import annotations

import html as html_lib
import re
import time
from datetime import date

import requests

_HEADERS = {"User-Agent": "SamuelMadding/1.0 sdmadding@icloud.com"}
_DELAY   = 0.15   # 150ms between EDGAR requests — stays well under 10 req/sec
_MAX_DL  = 1_500_000   # 1.5MB cap on primary document download

_POS_WORDS = [
    "increased", "grew", "expanded", "record", "strong", "improved",
    "exceeded", "accelerated", "momentum", "robust", "favorable",
    "outperformed", "higher", "growth", "gains", "solid", "positive",
]
_CAU_WORDS = [
    "decreased", "declined", "uncertainty", "challenging", "headwind",
    "may adversely", "could adversely", "pressure", "weakness", "lower",
    "difficult", "adverse", "volatile", "concern", "impairment",
    "restructur", "charges", "litigation",
]

_RISK_CATS = {
    "Regulatory":    {"regulat", "legislat", "tax law", "sanction", "govern", "compli", "tariff"},
    "Cybersecurity": {"cyber", "data breach", "secur", "hack", "privacy", "ransomware"},
    "Supply Chain":  {"supply chain", "manufactur", "supplier", "component", "inventory", "outsourc"},
    "Competitive":   {"compet", "market share", "rival", "competitive"},
    "Financial":     {"debt", "interest rate", "credit", "capital", "fiscal", "currency", "exchange rate"},
    "IP / Legal":    {"intellectu", "patent", "licens", "copyright", "lawsuit", "litigation"},
    "Technology":    {"technolog", "innovat", "platform", "software", "hardware", "algorithm"},
}


# ── EDGAR helpers ─────────────────────────────────────────────────────────────

def _edgar_get(url: str, timeout: int = 20) -> requests.Response | None:
    """GET with required EDGAR headers + polite delay. Returns None on any error."""
    time.sleep(_DELAY)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception:
        return None


def _get_cik(ticker: str) -> str | None:
    """Return 10-digit zero-padded CIK string for ticker, or None."""
    r = _edgar_get("https://www.sec.gov/files/company_tickers.json")
    if not r:
        return None
    try:
        data = r.json()
        ticker_up = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_up:
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        pass
    return None


def _get_submissions(cik10: str) -> dict | None:
    """Fetch EDGAR submissions JSON for the given 10-digit CIK."""
    r = _edgar_get(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not r:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _latest_filing(submissions: dict, form_type: str) -> dict | None:
    """Return metadata for the most recent filing of `form_type`."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accs    = recent.get("accessionNumber", [])
    pdocs   = recent.get("primaryDocument", [])
    periods = recent.get("reportDate", [])
    cik_int = int(submissions.get("cik", 0))

    for i, f in enumerate(forms):
        if f == form_type:
            acc_clean = accs[i].replace("-", "")
            pdoc      = pdocs[i] if i < len(pdocs) else ""
            period    = periods[i] if i < len(periods) else ""
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{cik_int}/{acc_clean}/{pdoc}")
            return {
                "form":        form_type,
                "filed":       dates[i],
                "period":      period,
                "accession":   accs[i],
                "primary_doc": pdoc,
                "url":         url,
            }
    return None


def _filing_history(submissions: dict, n: int = 5) -> list[dict]:
    """Return last `n` 10-K and last `n` 10-Q filings, sorted newest-first."""
    recent  = submissions.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accs    = recent.get("accessionNumber", [])
    pdocs   = recent.get("primaryDocument", [])
    periods = recent.get("reportDate", [])
    cik_int = int(submissions.get("cik", 0))

    history: list[dict] = []
    counts: dict[str, int] = {"10-K": 0, "10-Q": 0}

    for i, f in enumerate(forms):
        if f not in counts or counts[f] >= n:
            continue
        acc_clean = accs[i].replace("-", "")
        pdoc      = pdocs[i] if i < len(pdocs) else ""
        period    = periods[i] if i < len(periods) else ""
        url = (f"https://www.sec.gov/Archives/edgar/data/"
               f"{cik_int}/{acc_clean}/{pdoc}")
        history.append({
            "type":   f,
            "filed":  dates[i],
            "period": period,
            "url":    url,
        })
        counts[f] += 1
        if counts["10-K"] >= n and counts["10-Q"] >= n:
            break

    return sorted(history, key=lambda x: x["filed"], reverse=True)


# ── Text extraction ───────────────────────────────────────────────────────────

def _strip_html(t: str) -> str:
    # Convert block-level tags to newlines to preserve paragraph structure
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(
        r'</?(?:p|div|tr|li|h[1-6]|table|tbody|thead|tfoot|section)[^>]*>',
        '\n', t, flags=re.IGNORECASE,
    )
    t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r'<!--.*?-->', '', t, flags=re.DOTALL)
    t = re.sub(r'<[^>]+>', '', t)
    t = html_lib.unescape(t)
    t = t.replace('\xa0', ' ')
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n[ \t]+\n', '\n\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _find_section(text: str, start_pats: list[str],
                  end_pats: list[str], max_len: int = 20000) -> str:
    """Find the body section text, skipping TOC entries."""
    for pat in start_pats:
        for m in re.finditer(pat, text, re.IGNORECASE):
            # Skip TOC entries: immediately followed by page number + "Item"
            after = text[m.end():m.end() + 35].strip()
            if re.match(r'^\d+\s*(?:item|part)', after, re.IGNORECASE):
                continue
            remaining = text[m.start():]
            # Find end of section
            end_pos = max_len
            for ep in end_pats:
                em = re.search(ep, remaining[80:], re.IGNORECASE)
                if em and em.start() < end_pos:
                    end_pos = em.start()
            if end_pos > 800:   # real section has substance
                return remaining[:end_pos]
    return ""


def _fetch_and_clean(url: str) -> str:
    """Download filing, cap at _MAX_DL bytes, strip HTML → clean text."""
    r = _edgar_get(url, timeout=30)
    if not r:
        return ""
    raw = r.text[:_MAX_DL]
    return _strip_html(raw)


# ── Risk factor extraction ────────────────────────────────────────────────────

def _categorize(text: str) -> str:
    t = text[:300].lower()  # use opening of paragraph for category
    for cat, keywords in _RISK_CATS.items():
        if any(kw in t for kw in keywords):
            return cat
    return "Operational"


def _risk_title(text: str, max_chars: int = 110) -> str:
    """Extract concise risk title from paragraph opening."""
    # Find first sentence boundary: period + space + capital, within limit
    m = re.search(r'\.\s+[A-Z]', text[:max_chars + 40])
    if m and m.start() <= max_chars:
        return text[:m.start() + 1]
    # Word-boundary truncation
    fragment = text[:max_chars]
    space = fragment.rfind(' ')
    if space > 50:
        return fragment[:space] + '...'
    return fragment + '...'


def _extract_risks(section: str, n: int = 5) -> list[dict]:
    """Extract top-n risk factors sorted by paragraph length (longer = more material)."""
    lines = [l.strip() for l in section.split('\n') if l.strip()]
    risks: list[dict] = []

    for line in lines:
        # Skip page headers and very short / very long header lines
        if re.match(r'.{1,60}\|\s*\d{4}\s*Form\s*10', line):
            continue
        if len(line) < 150:
            continue
        risks.append({
            "title":    _risk_title(line),
            "category": _categorize(line),
            "summary":  (line[:220] + '...') if len(line) > 220 else line,
            "_len":     len(line),
        })

    risks.sort(key=lambda r: r["_len"], reverse=True)
    for r in risks:
        del r["_len"]
    return risks[:n]


# ── MD&A tone scoring ─────────────────────────────────────────────────────────

def _mda_tone(mda_text: str) -> dict:
    t = mda_text.lower()
    pos_found = [w for w in _POS_WORDS if w in t]
    cau_found = [w for w in _CAU_WORDS if w in t]
    pc, cc = len(pos_found), len(cau_found)
    if pc >= cc * 1.5:
        label = "Positive"
    elif cc >= pc * 1.5:
        label = "Cautious"
    else:
        label = "Neutral"
    return {
        "tone_label":     label,
        "positive_count": pc,
        "cautious_count": cc,
        "positive_words": pos_found[:6],
        "cautious_words": cau_found[:6],
    }


# ── Main entry ────────────────────────────────────────────────────────────────

def run_sec_parser(ticker: str, stats: dict, fin_data: dict) -> dict:
    """Fetch and parse most recent 10-K and 10-Q from SEC EDGAR.

    No Claude API calls — all extraction is algorithmic.
    Returns {"error": "reason"} on failure, never raises.
    """
    try:
        return _run(ticker, stats, fin_data)
    except Exception as exc:
        return {"error": str(exc)}


def _run(ticker: str, stats: dict, fin_data: dict) -> dict:
    # ── 1. CIK lookup ─────────────────────────────────────────────────────────
    cik10 = _get_cik(ticker)
    if not cik10:
        return {"error": f"CIK not found for {ticker}"}

    # ── 2. Submissions metadata ────────────────────────────────────────────────
    submissions = _get_submissions(cik10)
    if not submissions:
        return {"error": "EDGAR submissions API unavailable"}

    info_10k = _latest_filing(submissions, "10-K")
    info_10q = _latest_filing(submissions, "10-Q")

    if not info_10k:
        return {"error": "No 10-K filing found in EDGAR"}

    history = _filing_history(submissions, n=4)

    result: dict = {
        "error":          None,
        "cik":            cik10,
        "ticker":         ticker.upper(),
        "latest_10k_date": info_10k["filed"] if info_10k else None,
        "latest_10q_date": info_10q["filed"] if info_10q else None,
        "filing_url_10k":  info_10k["url"]   if info_10k else None,
        "filing_url_10q":  info_10q["url"]   if info_10q else None,
        "filing_history":  history,
        # Filled below:
        "top_risks":      [],
        "mda_summary":    "",
        "business_summary": "",
        "tone_signals":   {},
    }

    # ── 3. Fetch and parse 10-K body ──────────────────────────────────────────
    if info_10k and info_10k.get("url"):
        clean = _fetch_and_clean(info_10k["url"])
        if clean:
            # Item 1: Business
            sec_biz = _find_section(
                clean,
                [r'item\s*1\b(?!\s*[aAbBcC])\.?\s*(?:business|general)', r'\bitem\s*1[\.\s]\s*business'],
                [r'\nitem\s*1a[\.\s]', r'\nitem\s*2[\.\s]'],
                max_len=3000,
            )
            if sec_biz:
                lines_biz = [l.strip() for l in sec_biz.split('\n') if len(l.strip()) > 60]
                # Skip the header line itself, take first substantive paragraph
                for l in lines_biz[1:]:
                    result["business_summary"] = l[:400]
                    break

            # Item 1A: Risk Factors
            sec_1a = _find_section(
                clean,
                [r'item\s*1a\.?\s*risk\s+factors', r'item\s*1a[\.\s]'],
                [r'\nitem\s*1b[\.\s]', r'\nitem\s*1c[\.\s]', r'\nitem\s*2[\.\s]'],
                max_len=30000,
            )
            if sec_1a:
                result["top_risks"] = _extract_risks(sec_1a)

            # Item 7: MD&A
            sec_7 = _find_section(
                clean,
                [r'item\s*7\.?\s*management.?s?\s+discussion', r'item\s*7[\.\s]'],
                [r'\nitem\s*7a[\.\s]', r'\nitem\s*8[\.\s]'],
                max_len=5000,
            )
            if sec_7:
                lines_7 = [l.strip() for l in sec_7.split('\n') if len(l.strip()) > 80]
                # Skip boilerplate "read in conjunction" / product announcement headers
                _skip = re.compile(
                    r'(?i)read in conjunction|product.*service.*software|^first quarter|'
                    r'^second quarter|^third quarter|^fourth quarter|fiscal year \d{4}:|'
                    r"^the company.{0,30}fiscal year is|^an additional week"
                )
                for l in lines_7[1:]:
                    if not _skip.search(l[:120]):
                        result["mda_summary"] = l[:600]
                        break
                result["tone_signals"] = _mda_tone(sec_7)

    return result
