from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 3500
SYSTEM_PROMPT = "You are a senior equity analyst. Be direct, specific, and data-driven. No disclaimers."
ANALYSIS_STRUCTURE = (
    "## Company Snapshot\n"
    "## Price Action & Technicals\n"
    "## Fundamentals\n"
    "## Revenue & Growth Trends\n"
    "## Profitability\n"
    "## Balance Sheet Health\n"
    "## Cash Flow Quality\n"
    "## Red Flags\n"
    "## Analyst Consensus\n"
    "## Bull Case\n"
    "## Bear Case\n"
    "## Key Risks\n"
    "## Verdict (one sentence)"
)


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt(val, decimals: int = 2, pct: bool = False, mult=None) -> str:
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "N/A"
    if mult:
        val = val * mult
    return f"{val:.{decimals}f}%" if pct else f"{val:.{decimals}f}"


def _fmt_large(val) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "N/A"
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= threshold:
            return f"${v / threshold:.2f}{suffix}"
    return f"${v:.2f}"


def _fmt_m(val_m) -> str:
    """Format a value already in millions."""
    if val_m is None:
        return "N/A"
    try:
        v = float(val_m)
    except (TypeError, ValueError):
        return "N/A"
    if abs(v) >= 1000:
        return f"${v / 1000:.1f}B"
    return f"${v:.0f}M"


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.1f}%" if val != 0 else "0.0%"


def _fmt_pct_plain(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


# ── Claude payload ────────────────────────────────────────────────────────────

def _build_payload(stats: dict, fin_data: dict, news: list | None = None) -> str:
    info = stats["info"]

    payload: dict = {
        "t": stats["ticker"],
        "sec": info.get("sector"),
        "ind": info.get("industry"),
        "px": _fmt(stats["current_price"]),
        "mktCap": _fmt_large(info.get("marketCap")),
        "ret6m": _fmt(stats["stock_return_6mo"], pct=True),
        "spx6m": _fmt(stats["sp500_return_6mo"], pct=True),
        "rel": _fmt(stats["relative_return"], pct=True),
        "vol": _fmt(stats["volatility_annualized"], pct=True),
        "hi52": _fmt(stats["pct_from_52w_high"], pct=True),
        "lo52": _fmt(stats["pct_from_52w_low"], pct=True),
        "pe": _fmt(info.get("trailingPE")),
        "fpe": _fmt(info.get("forwardPE")),
        "pb": _fmt(info.get("priceToBook")),
        "eps": _fmt(info.get("trailingEps")),
        "feps": _fmt(info.get("forwardEps")),
        "rat": _fmt(info.get("recommendationMean")),
        "tgt": _fmt(info.get("targetMeanPrice")),
        "nAn": info.get("numberOfAnalystOpinions"),
        "ma50": _fmt(info.get("fiftyDayAverage")),
        "ma200": _fmt(info.get("twoHundredDayAverage")),
        "biz": (info.get("longBusinessSummary") or "")[:200],
    }

    # Compact financial summary — key ratios + trends only
    inc = fin_data.get("income_statement", {})
    cf  = fin_data.get("cash_flow", {})
    bs  = fin_data.get("balance_sheet") or {}
    a_inc = inc.get("annual") or {}
    a_cf  = cf.get("annual") or {}
    q_inc = inc.get("quarterly") or {}

    def _first(lst):
        return lst[0] if lst else None

    payload["fin"] = {
        "aRevGr":  _fmt_pct(inc.get("yoy_revenue")),
        "aNIGr":   _fmt_pct(inc.get("yoy_earnings")),
        "aFCFGr":  _fmt_pct(cf.get("yoy_fcf")),
        "gm":  [_fmt_pct_plain(v) for v in (q_inc.get("gross_margin") or [])[:4]],
        "om":  [_fmt_pct_plain(v) for v in (q_inc.get("operating_margin") or [])[:4]],
        "nm":  [_fmt_pct_plain(v) for v in (q_inc.get("net_margin") or [])[:4]],
        "qFCF": [_fmt_m(v) for v in (cf.get("quarterly", {}) or {}).get("free_cash_flow", [])[:4]],
        "cash":  _fmt_m(bs.get("cash")),
        "debt":  _fmt_m(bs.get("total_debt")),
        "netDebt": _fmt_m(bs.get("net_debt")),
        "de":    _fmt(bs.get("debt_to_equity")),
        "curr":  _fmt(bs.get("current_ratio")),
    }

    if news:
        payload["news"] = [a["headline"][:60] for a in news if a.get("headline")]

    payload_json = json.dumps(payload, separators=(",", ":"))
    return payload_json


# ── Markdown financial tables ─────────────────────────────────────────────────

def _md_table(headers: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _income_tables(inc: dict) -> str:
    sections = []
    for label, data in [("Quarterly", inc.get("quarterly")), ("Annual", inc.get("annual"))]:
        if not data:
            continue
        dates = data["dates"]
        headers = [""] + dates
        rows = [
            ("Revenue",          [_fmt_m(v) for v in data["revenue"]]),
            ("Gross Profit",     [_fmt_m(v) for v in data["gross_profit"]]),
            ("Operating Income", [_fmt_m(v) for v in data["operating_income"]]),
            ("Net Income",       [_fmt_m(v) for v in data["net_income"]]),
            ("Gross Margin",     [_fmt_pct_plain(v) for v in data["gross_margin"]]),
            ("Operating Margin", [_fmt_pct_plain(v) for v in data["operating_margin"]]),
            ("Net Margin",       [_fmt_pct_plain(v) for v in data["net_margin"]]),
        ]
        if label == "Annual":
            if data.get("yoy_revenue"):
                rows.append(("YoY Revenue Growth", [_fmt_pct(v) for v in data["yoy_revenue"]]))
            if data.get("yoy_ni"):
                rows.append(("YoY Net Income Growth", [_fmt_pct(v) for v in data["yoy_ni"]]))
        table_rows = [(r[0], *r[1]) for r in rows]
        sections.append(f"**{label}**\n\n{_md_table(headers, table_rows)}")
    return "\n\n".join(sections)


def _cashflow_tables(cf: dict, inc: dict) -> str:
    sections = []
    for label, data in [("Quarterly", cf.get("quarterly")), ("Annual", cf.get("annual"))]:
        if not data:
            continue
        dates = data["dates"]
        headers = [""] + dates
        rows = [
            ("Operating Cash Flow",  [_fmt_m(v) for v in data["operating_cash_flow"]]),
            ("Capital Expenditure",  [_fmt_m(v) for v in data["capital_expenditure"]]),
            ("Free Cash Flow",       [_fmt_m(v) for v in data["free_cash_flow"]]),
            ("FCF Margin",           [_fmt_pct_plain(v) for v in data["fcf_margin"]]),
        ]
        if label == "Annual" and data.get("yoy_fcf"):
            rows.append(("YoY FCF Growth", [_fmt_pct(v) for v in data["yoy_fcf"]]))
        table_rows = [(r[0], *r[1]) for r in rows]
        sections.append(f"**{label}**\n\n{_md_table(headers, table_rows)}")
    return "\n\n".join(sections)


def _balance_sheet_table(bs: dict) -> str:
    if not bs:
        return "*Balance sheet data unavailable.*"
    rows = [
        ("Total Assets",         _fmt_m(bs.get("total_assets"))),
        ("Total Liabilities",    _fmt_m(bs.get("total_liabilities"))),
        ("Shareholders' Equity", _fmt_m(bs.get("shareholders_equity"))),
        ("Cash & Equivalents",   _fmt_m(bs.get("cash"))),
        ("Total Debt",           _fmt_m(bs.get("total_debt"))),
        ("Net Debt",             _fmt_m(bs.get("net_debt"))),
        ("Current Ratio",        _fmt(bs.get("current_ratio"))),
        ("Debt / Equity",        _fmt(bs.get("debt_to_equity"))),
    ]
    return _md_table(["Metric", "Value"], rows)


def _financial_statements_md(fin_data: dict) -> str:
    inc = fin_data.get("income_statement", {})
    cf  = fin_data.get("cash_flow", {})
    bs  = fin_data.get("balance_sheet")
    bs_date = bs.get("date", "") if bs else ""

    parts = ["---", "", "## Financial Statements", ""]

    parts += ["### Income Statement", "", _income_tables(inc), ""]

    parts += [f"### Balance Sheet ({bs_date})" if bs_date else "### Balance Sheet",
              "", _balance_sheet_table(bs), ""]

    parts += ["### Cash Flow Statement", "", _cashflow_tables(cf, inc), ""]

    return "\n".join(parts)


# ── News & Sentiment section ──────────────────────────────────────────────────

def _news_md_section(sent_data: dict) -> str:
    overall  = sent_data.get("overall", "Neutral")
    score    = sent_data.get("score")
    momentum = sent_data.get("momentum", "Stable")
    themes   = sent_data.get("themes", [])
    catalyst = sent_data.get("catalyst", "")
    summary  = sent_data.get("summary", "")
    articles = sent_data.get("articles", [])

    score_str    = f" · Score: {score}/10" if score is not None else ""
    momentum_str = f" · Momentum: {momentum}" if momentum else ""

    lines = [
        "---", "",
        "## News & Sentiment Analysis", "",
        f"**Overall Sentiment: {overall}**{score_str}{momentum_str}",
        "",
    ]
    if summary:
        lines += [f"> {summary}", ""]
    if themes:
        lines += [f"**Key Themes:** {' · '.join(themes)}", ""]
    if catalyst:
        lines += [f"**Catalyst Watch:** {catalyst}", ""]
    lines += [
        "",
        "| Impact | Type | Sentiment | Source | Date | Headline | Investment Implication |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in articles:
        hl     = a["headline"]
        url    = a.get("url", "")
        linked = f"[{hl}]({url})" if url else hl
        note   = a.get("note", "")
        lines.append(
            f"| {a.get('impact','—')} | {a.get('type','—')} | {a.get('sentiment','—')}"
            f" | {a.get('source','')} | {a.get('date','')} | {linked} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def build_report(ticker: str, stats: dict, fin_data: dict,
                 news: list | None = None, dry_run: bool = False) -> tuple[str, dict | None]:
    payload_json = _build_payload(stats, fin_data, news)

    if dry_run:
        print("=== DRY RUN: Claude payload ===")
        print(payload_json)
        print(f"\nPayload length: {len(payload_json)} chars", file=sys.stderr)
        md = (
            f"# {ticker} Analysis — {date.today()}\n\n"
            "*Dry run — Claude call skipped.*\n\n"
            f"```json\n{payload_json}\n```\n"
        )
        return md, None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    if news:
        json_schema = (
            '{"sent":[{"i":0,"s":"Positive","imp":"Major","type":"Earnings",'
            '"note":"One sentence: specific investment implication of this headline."}],'
            '"overall":"Bullish","score":8.1,"momentum":"Improving",'
            '"themes":["Theme A","Theme B","Theme C"],'
            '"catalyst":"One sentence: key near-term catalyst to watch.",'
            '"summary":"2-3 sentence IB-grade synthesis of the news flow and its implications."}'
        )
        user_content = (
            f"First, output the news sentiment JSON block below (output it first, before anything else).\n\n"
            f"```json\n{json_schema}\n```\n\n"
            f"Then analyze this stock using exactly these section headers:\n"
            f"{ANALYSIS_STRUCTURE}\n\n"
            f"Data: {payload_json}\n\n"
            f"JSON field rules — `imp`: Major/Moderate/Minor. "
            f"`type`: Earnings/Product/Regulatory/Macro/Technical/M&A/Management/Analyst/Other. "
            f"`momentum`: Improving/Stable/Deteriorating. "
            f"Write `note` and `summary` as a senior equity analyst: specific, data-referenced, actionable."
        )
    else:
        user_content = (
            f"Analyze this stock. Use exactly these section headers:\n"
            f"{ANALYSIS_STRUCTURE}\n\n"
            f"Data: {payload_json}"
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    analysis = message.content[0].text.strip()

    # Parse sentiment JSON Claude appended, then strip it from the visible analysis
    sent_data: dict | None = None
    if news:
        articles_with_sent = [{**a, "sentiment": "Neutral", "impact": "Moderate",
                                "type": "Other", "note": ""} for a in news]
        overall, score, momentum, themes, catalyst, summary = "Neutral", None, "Stable", [], "", ""
        m = re.search(r'```json\s*(\{[^`]+\})\s*```', analysis)
        if m:
            try:
                raw     = json.loads(m.group(1))
                idx_map = {item["i"]: item for item in raw.get("sent", [])}
                articles_with_sent = [
                    {**a,
                     "sentiment": idx_map.get(i, {}).get("s", "Neutral"),
                     "impact":    idx_map.get(i, {}).get("imp", "Moderate"),
                     "type":      idx_map.get(i, {}).get("type", "Other"),
                     "note":      idx_map.get(i, {}).get("note", "")}
                    for i, a in enumerate(news)
                ]
                overall  = raw.get("overall", "Neutral")
                score    = raw.get("score")
                momentum = raw.get("momentum", "Stable")
                themes   = raw.get("themes", [])
                catalyst = raw.get("catalyst", "")
                summary  = raw.get("summary", "")
                # Strip the JSON block wherever it appears
                before = analysis[:m.start()].strip()
                after  = analysis[m.end():].strip()
                analysis = (before + "\n\n" + after).strip() if before else after
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        sent_data = {
            "articles": articles_with_sent,
            "overall": overall, "score": score, "momentum": momentum,
            "themes": themes, "catalyst": catalyst, "summary": summary,
        }

    news_section = _news_md_section(sent_data) + "\n" if sent_data else ""
    fin_tables   = _financial_statements_md(fin_data)
    markdown = (
        f"# {ticker} Stock Analysis — {date.today()}\n\n"
        f"{analysis}\n\n"
        f"{news_section}"
        f"{fin_tables}"
    )
    return markdown, sent_data
