from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
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
    "## DCF Valuation\n"
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

def _build_payload(stats: dict, fin_data: dict, news: list | None = None,
                   dcf_result: dict | None = None,
                   competitive: dict | None = None,
                   analyst_coverage: dict | None = None,
                   transcript_result: dict | None = None,
                   sec_result: dict | None = None) -> str:
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

    if dcf_result and not dcf_result.get("error"):
        v   = dcf_result["valuation"]
        inp = dcf_result["inputs"]
        payload["dcf"] = {
            "iv":   _fmt(v["intrinsic"]),
            "px":   _fmt(v["current_price"]) if v["current_price"] else "N/A",
            "up":   _fmt_pct(v["upside_pct"]) if v["upside_pct"] is not None else "N/A",
            "wacc": f"{inp['wacc']}%",
            "tv":   f"{v['tv_pct']}%",
            "ev":   _fmt_large(v["ev_m"] * 1e6) if v["ev_m"] else "N/A",
        }
        if dcf_result.get("warnings"):
            payload["dcf"]["warn"] = dcf_result["warnings"][0]

    if competitive and not competitive.get("error"):
        tgt   = competitive["target"]
        peers = competitive["peers"]
        med   = competitive["peer_medians"]
        ranks = competitive["rankings"]
        payload["comp"] = {
            "tgt": {
                "gm":  tgt.get("gross_margin"),
                "om":  tgt.get("op_margin"),
                "roe": tgt.get("roe"),
                "gr":  tgt.get("rev_growth"),
                "fpe": tgt.get("fpe"),
            },
            "peers": [
                {"t": p["ticker"], "gm": p.get("gross_margin"), "om": p.get("op_margin"),
                 "roe": p.get("roe"), "gr": p.get("rev_growth"), "fpe": p.get("fpe")}
                for p in peers
            ],
            "med": {
                "gm":  med.get("gross_margin"),
                "om":  med.get("op_margin"),
                "roe": med.get("roe"),
                "gr":  med.get("rev_growth"),
                "fpe": med.get("fpe"),
            },
            "ranks": {k: ranks[k] for k in ("rev_growth", "gross_margin", "op_margin", "roe", "fpe")
                      if k in ranks},
            "src": competitive.get("source"),
        }

    if analyst_coverage and not analyst_coverage.get("error"):
        cov = analyst_coverage
        payload["cov"] = {
            "rating": cov.get("consensus_rating"),
            "bull":   cov.get("bull_ratio"),
            "n":      cov.get("total_analysts"),
            "tgt": {
                "mean": _fmt(cov.get("mean_target")),
                "hi":   _fmt(cov.get("high_target")),
                "lo":   _fmt(cov.get("low_target")),
            },
            "up":     _fmt_pct(cov.get("upside_pct")),
            "spread": _fmt_pct(cov.get("target_spread_pct")),
        }

    if transcript_result and not transcript_result.get("error"):
        tr = transcript_result
        payload["transcript"] = {
            "streak": tr.get("beat_streak", 0),
            "beats":  tr.get("beat_count", 0),
            "of":     tr.get("total_quarters", 0),
            "tone":   tr.get("tone_label"),
            "score":  tr.get("tone_score"),
            "surp":   tr.get("last_eps_surprise"),
            "next":   tr.get("next_earnings_date"),
        }

    if sec_result and not sec_result.get("error"):
        sr = sec_result
        risks_compact = [
            f"{r['category']}: {r['title'][:70]}"
            for r in (sr.get("top_risks") or [])[:3]
        ]
        payload["edgar"] = {
            "10k":   sr.get("latest_10k_date"),
            "10q":   sr.get("latest_10q_date"),
            "tone":  sr.get("tone_signals", {}).get("tone_label"),
            "risks": risks_compact,
            "mda":   (sr.get("mda_summary") or "")[:200],
        }

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


# ── Research pipeline markdown ────────────────────────────────────────────────

def _research_md_sections(research: dict) -> str:
    parts = []

    # Investment Thesis
    th = research.get("thesis", {})
    if not th.get("_placeholder"):
        lines = ["---", "", "## Investment Thesis", "",
                 f"**Rating:** {th.get('rating','N/A')}   ·   **Target:** {th.get('target','N/A')}",
                 ""]
        if th.get("bull"):
            lines += ["**Bull Case**"] + [f"{i+1}. {p}" for i, p in enumerate(th["bull"])] + [""]
        if th.get("bear"):
            lines += ["**Bear Case**"] + [f"{i+1}. {p}" for i, p in enumerate(th["bear"])] + [""]
        if th.get("catalysts"):
            lines += ["**Key Catalysts**"] + [f"- {c}" for c in th["catalysts"]] + [""]
        if th.get("verdict"):
            lines += [f"**Verdict:** {th['verdict']}", ""]
        parts.append("\n".join(lines))
    else:
        parts.append("---\n\n## Investment Thesis\n\n*Analysis unavailable.*\n")

    # Comps Analysis
    co = research.get("comps", {})
    if not co.get("_placeholder"):
        lines = ["---", "", "## Comparable Companies Analysis", ""]
        if co.get("summary"):
            lines += [co["summary"], ""]
        if co.get("premium"):
            lines += [f"**vs. Peer Median:** {co['premium']}", ""]
        if co.get("comps"):
            lines += ["| Company | Ticker | EV/EBITDA | P/E (Fwd) | EV/Revenue | Note |",
                      "|---|---|---|---|---|---|"]
            for c in co["comps"]:
                def _mx(v):
                    try: return f"{float(v):.1f}x"
                    except Exception: return str(v) if v is not None else "N/A"
                lines.append(
                    f"| {c.get('company','')} | {c.get('ticker','')} | "
                    f"{_mx(c.get('ev_ebitda'))} | {_mx(c.get('pe_fwd'))} | "
                    f"{_mx(c.get('ev_rev'))} | {c.get('note','')} |"
                )
            lines.append("")
        parts.append("\n".join(lines))
    else:
        parts.append("---\n\n## Comparable Companies Analysis\n\n*Analysis unavailable.*\n")

    # Earnings Preview
    ep = research.get("earnings", {})
    if not ep.get("_placeholder"):
        lines = ["---", "", "## Earnings Preview", ""]
        meta = "   ·   ".join(x for x in [
            f"**Next Earnings:** {ep['next_earnings']}" if ep.get("next_earnings") else None,
            f"**Consensus Revenue:** {ep['consensus_rev']}" if ep.get("consensus_rev") else None,
            f"**EPS:** {ep['consensus_eps']}" if ep.get("consensus_eps") else None,
            f"**Options Implied Move:** {ep['implied_move']}" if ep.get("implied_move") else None,
        ] if x)
        if meta:
            lines += [meta, ""]
        if ep.get("watch"):
            lines += [f"**Key Metrics to Watch:** {' · '.join(ep['watch'])}", ""]
        if ep.get("scenarios"):
            lines += ["| Scenario | Revenue | EPS | Implied Move | Probability | Trigger |",
                      "|---|---|---|---|---|---|"]
            for s in ep["scenarios"]:
                lines.append(
                    f"| {s.get('name','')} | {s.get('rev','')} | {s.get('eps','')} | "
                    f"{s.get('move','')} | {s.get('prob','')} | {s.get('trigger','')} |"
                )
            lines.append("")
        parts.append("\n".join(lines))
    else:
        parts.append("---\n\n## Earnings Preview\n\n*Analysis unavailable.*\n")

    return "\n".join(parts)


# ── Competitive analysis markdown ─────────────────────────────────────────────

def _competitive_md_section(comp_result: dict, comp_assessment: dict | None) -> str:
    if comp_result.get("error"):
        return "---\n\n## Competitive Analysis\n\n*Competitive data unavailable.*\n"

    target  = comp_result.get("target", {})
    peers   = comp_result.get("peers", [])
    medians = comp_result.get("peer_medians", {})
    ca      = comp_assessment or {}

    moat_type = ca.get("moat_type", "N/A")
    moat_str  = ca.get("moat_strength", "N/A")
    position  = ca.get("position", "N/A")
    key_risk  = ca.get("key_risk", "N/A")
    assessment = ca.get("assessment", "")

    def _fp(v):
        return "N/A" if v is None else f"{v:.1f}%"

    def _fpe(v):
        return "N/A" if v is None else f"{v:.1f}x"

    lines = [
        "---", "",
        "## Competitive Analysis", "",
        f"**Competitive Position:** {position}  |  **Moat:** {moat_type} ({moat_str})",
        f"**Key Competitive Risk:** {key_risk}",
        "",
        "### Peer Comparison",
        "",
        "| Company | Ticker | Rev Growth | Gross Margin | Op Margin | ROE | D/E | Fwd P/E |",
        "|---|---|---|---|---|---|---|---|",
        # Target row (bold)
        f"| **{target.get('name','')}** | **{target.get('ticker','')}** "
        f"| **{_fp(target.get('rev_growth'))}** | **{_fp(target.get('gross_margin'))}** "
        f"| **{_fp(target.get('op_margin'))}** | **{_fp(target.get('roe'))}** "
        f"| **{_fp(target.get('de'))}** | **{_fpe(target.get('fpe'))}** |",
    ]

    for p in sorted(peers, key=lambda x: x.get("mktcap") or 0, reverse=True):
        lines.append(
            f"| {p.get('name','')} | {p.get('ticker','')} "
            f"| {_fp(p.get('rev_growth'))} | {_fp(p.get('gross_margin'))} "
            f"| {_fp(p.get('op_margin'))} | {_fp(p.get('roe'))} "
            f"| {_fp(p.get('de'))} | {_fpe(p.get('fpe'))} |"
        )

    lines.append(
        f"| *Peer Median* | — "
        f"| *{_fp(medians.get('rev_growth'))}* | *{_fp(medians.get('gross_margin'))}* "
        f"| *{_fp(medians.get('op_margin'))}* | *{_fp(medians.get('roe'))}* "
        f"| — | *{_fpe(medians.get('fpe'))}* |"
    )
    lines.append("")

    if assessment:
        lines += ["### Competitive Assessment", "", assessment, ""]

    return "\n".join(lines)


# ── SEC filing markdown ───────────────────────────────────────────────────────

def _sec_md_section(result: dict | None) -> str:
    if not result or result.get("error"):
        return "---\n\n## SEC Filings\n\n*SEC filing data unavailable.*\n"

    ticker   = result.get("ticker", "")
    k_date   = result.get("latest_10k_date") or "—"
    q_date   = result.get("latest_10q_date") or "—"
    k_url    = result.get("filing_url_10k")
    q_url    = result.get("filing_url_10q")
    tone     = result.get("tone_signals", {}).get("tone_label", "—")
    pos_n    = result.get("tone_signals", {}).get("positive_count", 0)
    cau_n    = result.get("tone_signals", {}).get("cautious_count", 0)
    risks    = result.get("top_risks", [])
    mda      = result.get("mda_summary", "")
    history  = result.get("filing_history", [])

    k_link = f"[View 10-K]({k_url})" if k_url else k_date
    q_link = f"[View 10-Q]({q_url})" if q_url else q_date

    lines = [
        "---", "",
        "## SEC Filings", "",
        f"**Latest 10-K:** {k_date} {k_link}  |  **Latest 10-Q:** {q_date} {q_link}",
        f"**MD&A Tone: {tone}** (positive signals: {pos_n}, cautious: {cau_n})",
        "",
    ]

    if mda:
        lines += [f"> {mda[:400]}", ""]

    if risks:
        lines += [
            "### Top Risk Factors (10-K)", "",
            "| # | Category | Risk Summary |",
            "|---|---|---|",
        ]
        for i, r in enumerate(risks, 1):
            summary = r.get("summary", "")[:180]
            lines.append(f"| {i} | {r.get('category','—')} | {summary} |")
        lines.append("")

    if history:
        lines += [
            "### Filing History", "",
            "| Type | Filed | Period | Link |",
            "|---|---|---|---|",
        ]
        for h in history[:6]:
            url   = h.get("url", "")
            label = f"[SEC EDGAR]({url})" if url else "—"
            lines.append(
                f"| {h.get('type','—')} | {h.get('filed','—')} "
                f"| {h.get('period','—')} | {label} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Transcript / earnings beat-miss markdown ─────────────────────────────────

def _transcript_md_section(result: dict | None) -> str:
    if not result or result.get("error"):
        return "---\n\n## Earnings Beat/Miss History\n\n*Earnings history unavailable.*\n"

    streak   = result.get("beat_streak", 0)
    misses   = result.get("miss_streak", 0)
    beats    = result.get("beat_count", 0)
    total    = result.get("total_quarters", 0)
    tone     = result.get("tone_label", "N/A")
    score    = result.get("tone_score")
    guidance = result.get("guidance_signals", [])
    nxt      = result.get("next_earnings_date")
    history  = result.get("beat_miss_history", [])

    def _ps(v):
        return "N/A" if v is None else f"{v:+.1f}%"

    def _pm(v):
        return "N/A" if v is None else f"${v:.0f}M"

    lines = [
        "---", "",
        "## Earnings Beat/Miss History", "",
        (f"**Tone: {tone}** (score: {score:+.2f})  |  "
         f"**Beat Streak: {streak}**  |  **{beats}/{total} beats**"
         if score is not None else
         f"**Tone: {tone}**  |  **Beat Streak: {streak}**  |  **{beats}/{total} beats**"),
        "",
    ]

    if nxt:
        lines += [f"**Next Earnings Date:** {nxt}", ""]

    if guidance:
        lines += ["**Key Signals:**"]
        for sig in guidance:
            lines.append(f"- {sig}")
        lines.append("")

    if history:
        lines += [
            "### Quarterly EPS Beat/Miss",
            "",
            "| Date | EPS Est | Reported EPS | Surprise % | Beat/Miss | Revenue | Rev Growth |",
            "|---|---|---|---|---|---|---|",
        ]
        for q in history:
            beat_str = "Beat" if q.get("beat") is True else ("Miss" if q.get("beat") is False else "—")
            lines.append(
                f"| {q.get('date','—')} "
                f"| ${q.get('eps_est') or 'N/A'} "
                f"| ${q.get('eps_actual') or 'N/A'} "
                f"| {_ps(q.get('eps_surprise'))} "
                f"| {beat_str} "
                f"| {_pm(q.get('rev_actual'))} "
                f"| {_ps(q.get('rev_growth'))} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Analyst coverage markdown ─────────────────────────────────────────────────

def _analyst_coverage_md_section(cov_result: dict, cov_assessment: dict | None) -> str:
    if cov_result.get("error"):
        return "---\n\n## Analyst Coverage\n\n*Analyst coverage data unavailable.*\n"

    ca            = cov_assessment or {}
    signal        = ca.get("signal", "—")
    summary_text  = ca.get("summary", "")
    rev_bias      = ca.get("revision_bias", "—")

    rating   = cov_result.get("consensus_rating") or "N/A"
    bull     = cov_result.get("bull_ratio")
    buy      = cov_result.get("buy_count", 0)
    hold     = cov_result.get("hold_count", 0)
    sell     = cov_result.get("sell_count", 0)
    total    = cov_result.get("total_analysts", 0)
    mean_tgt = cov_result.get("mean_target")
    high_tgt = cov_result.get("high_target")
    low_tgt  = cov_result.get("low_target")
    current  = cov_result.get("current_price")
    upside   = cov_result.get("upside_pct")
    spread   = cov_result.get("target_spread_pct")

    def _p(v):
        return "N/A" if v is None else f"{v:.2f}"

    def _pct(v, sign=False):
        if v is None:
            return "N/A"
        return f"{v:+.1f}%" if sign else f"{v:.1f}%"

    lines = [
        "---", "",
        "## Analyst Coverage", "",
        (f"**Consensus: {rating}**  |  **Signal: {signal}**  "
         f"|  **Estimate Revision Bias: {rev_bias}**"),
        "",
    ]
    if summary_text:
        lines += [f"> {summary_text}", ""]

    lines += [
        "### Rating Distribution", "",
        "| Buy | Hold | Sell | Total | Bull Ratio |",
        "|---|---|---|---|---|",
        f"| {buy} | {hold} | {sell} | {total} | {_pct(bull)} |",
        "",
        "### Price Target Summary", "",
        "| | Mean | High | Low | Current | Upside | Spread |",
        "|---|---|---|---|---|---|---|",
        (f"| Price | ${_p(mean_tgt)} | ${_p(high_tgt)} | ${_p(low_tgt)}"
         f" | ${_p(current)} | {_pct(upside, sign=True)} | {_pct(spread)} |"),
        "",
    ]

    estimates = cov_result.get("estimates", [])
    if estimates:
        lines += [
            "### Consensus Estimates", "",
            "| Period | EPS Est | EPS High | EPS Low | Rev Estimate | # Analysts |",
            "|---|---|---|---|---|---|",
        ]
        for e in estimates[:4]:
            def _r(v):
                if v is None: return "N/A"
                if abs(v) >= 1e9: return f"${v/1e9:.1f}B"
                if abs(v) >= 1e6: return f"${v/1e6:.0f}M"
                return f"${v:.0f}"
            lines.append(
                f"| {e.get('date','—')} | ${_p(e.get('eps_est'))}"
                f" | ${_p(e.get('eps_high'))} | ${_p(e.get('eps_low'))}"
                f" | {_r(e.get('rev_est'))} | {e.get('n_analysts') or '—'} |"
            )
        lines.append("")

    recent = cov_result.get("recent_targets", [])
    if recent:
        lines += [
            "### Recent Analyst Targets", "",
            "| Firm | Analyst | Price Target | Date |",
            "|---|---|---|---|",
        ]
        for t in recent:
            lines.append(
                f"| {t.get('firm','—')} | {t.get('analyst','—')}"
                f" | ${_p(t.get('price_target'))} | {t.get('date','—')} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def build_report(ticker: str, stats: dict, fin_data: dict,
                 news: list | None = None, dcf_result: dict | None = None,
                 research: dict | None = None, competitive: dict | None = None,
                 analyst_coverage: dict | None = None,
                 transcript_result: dict | None = None,
                 sec_result: dict | None = None,
                 dry_run: bool = False) -> tuple[str, dict | None, dict | None, dict | None]:
    payload_json = _build_payload(stats, fin_data, news, dcf_result, competitive,
                                  analyst_coverage, transcript_result, sec_result)

    if dry_run:
        print("=== DRY RUN: Claude payload ===")
        print(payload_json)
        print(f"\nPayload length: {len(payload_json)} chars", file=sys.stderr)
        md = (
            f"# {ticker} Analysis — {date.today()}\n\n"
            "*Dry run — Claude call skipped.*\n\n"
            f"```json\n{payload_json}\n```\n"
        )
        return md, None, None, None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    # DCF instruction
    if dcf_result and not dcf_result.get("error"):
        dcf_inst = (
            "\n\n## DCF Valuation: use the dcf key. Quote intrinsic value, WACC, "
            "implied upside/downside %, terminal value % of EV. Compare to analyst "
            "consensus target. State over/undervalued. Flag any warnings. 3-4 sentences."
        )
    else:
        dcf_inst = "\n\n## DCF Valuation: Model unavailable — note in one sentence."

    # Competitive instruction (appended to both prompt branches when comp data available)
    has_comp = competitive and not competitive.get("error")
    comp_inst = (
        "\n\nFor the comp JSON field: moat_type (Cost Advantage/Switching Costs/Network Effects/"
        "Intangible Assets/Efficient Scale/None), moat_strength (Wide/Narrow/None — one sentence "
        "justification citing specific margin or growth differential vs peers), "
        "position (Leader/Challenger/Follower/Niche), "
        "key_risk (name a specific competitor + threat in next 24 months), "
        "assessment (3-4 sentence institutional paragraph on competitive dynamics and "
        "what the peer comparison implies for the investment case)."
    ) if has_comp else ""

    has_cov  = analyst_coverage and not analyst_coverage.get("error")
    cov_inst = (
        "\n\nFor the cov JSON field: signal (Bullish/Neutral/Bearish based on bull ratio and "
        "mean-target upside), summary (2-3 sentence institutional assessment of analyst conviction "
        "quality, what target spread implies about certainty, and how consensus compares to DCF or "
        "current price), revision_bias (Positive/Flat/Negative based on EPS estimate trend)."
    ) if has_cov else ""

    if news:
        comp_json_field = (
            ',"comp":{"moat_type":"Switching Costs","moat_strength":"Wide — one sentence.",'
            '"position":"Leader","key_risk":"Specific named threat in 24 months.",'
            '"assessment":"3-4 sentence paragraph."}'
        ) if has_comp else ""
        cov_json_field = (
            ',"cov":{"signal":"Bullish","summary":"2-3 sentence coverage quality assessment.",'
            '"revision_bias":"Positive"}'
        ) if has_cov else ""

        json_schema = (
            '{"sent":[{"i":0,"s":"Positive","imp":"Major","type":"Earnings",'
            '"note":"One sentence: specific investment implication of this headline."}],'
            '"overall":"Bullish","score":8.1,"momentum":"Improving",'
            '"themes":["Theme A","Theme B","Theme C"],'
            '"catalyst":"One sentence: key near-term catalyst to watch.",'
            f'"summary":"2-3 sentence IB-grade synthesis of the news flow and its implications."'
            f'{comp_json_field}{cov_json_field}}}'
        )
        user_content = (
            f"First, output the JSON block below (before anything else).\n\n"
            f"```json\n{json_schema}\n```\n\n"
            f"Then analyze this stock using exactly these section headers:\n"
            f"{ANALYSIS_STRUCTURE}\n\n"
            f"Data: {payload_json}\n\n"
            f"JSON field rules — `imp`: Major/Moderate/Minor. "
            f"`type`: Earnings/Product/Regulatory/Macro/Technical/M&A/Management/Analyst/Other. "
            f"`momentum`: Improving/Stable/Deteriorating. "
            f"Write `note` and `summary` as a senior equity analyst: specific, data-referenced, actionable."
            f"{dcf_inst}{comp_inst}{cov_inst}"
        )
    else:
        json_parts = {}
        if has_comp:
            json_parts["comp"] = (
                '{"moat_type":"Switching Costs","moat_strength":"Wide — one sentence.",'
                '"position":"Leader","key_risk":"Specific named threat in 24 months.",'
                '"assessment":"3-4 sentence paragraph."}'
            )
        if has_cov:
            json_parts["cov"] = (
                '{"signal":"Bullish","summary":"2-3 sentence coverage quality assessment.",'
                '"revision_bias":"Positive"}'
            )

        schema_prefix = ""
        if json_parts:
            schema_body = "{" + ",".join(f'"{k}":{v}' for k, v in json_parts.items()) + "}"
            schema_prefix = (
                "First, output this JSON block before all analysis sections:\n\n"
                f"```json\n{schema_body}\n```\n\n"
            )
        user_content = (
            f"{schema_prefix}"
            f"Analyze this stock. Use exactly these section headers:\n"
            f"{ANALYSIS_STRUCTURE}\n\n"
            f"Data: {payload_json}"
            f"{dcf_inst}{comp_inst}{cov_inst}"
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    analysis = message.content[0].text.strip()

    # Parse JSON block from Claude's response (contains sentiment and/or comp/cov assessments)
    sent_data:       dict | None = None
    comp_assessment: dict | None = None
    cov_assessment:  dict | None = None

    m = re.search(r'```json\s*(\{[\s\S]+?\})\s*```', analysis)
    if m:
        try:
            raw = json.loads(m.group(1))
            comp_assessment = raw.get("comp") or None
            cov_assessment  = raw.get("cov")  or None

            if news and "sent" in raw:
                idx_map = {item["i"]: item for item in raw.get("sent", [])}
                articles_with_sent = [
                    {**a,
                     "sentiment": idx_map.get(i, {}).get("s", "Neutral"),
                     "impact":    idx_map.get(i, {}).get("imp", "Moderate"),
                     "type":      idx_map.get(i, {}).get("type", "Other"),
                     "note":      idx_map.get(i, {}).get("note", "")}
                    for i, a in enumerate(news)
                ]
                sent_data = {
                    "articles": articles_with_sent,
                    "overall":  raw.get("overall", "Neutral"),
                    "score":    raw.get("score"),
                    "momentum": raw.get("momentum", "Stable"),
                    "themes":   raw.get("themes", []),
                    "catalyst": raw.get("catalyst", ""),
                    "summary":  raw.get("summary", ""),
                }
            elif news:
                sent_data = {
                    "articles": [{**a, "sentiment": "Neutral", "impact": "Moderate",
                                  "type": "Other", "note": ""} for a in news],
                    "overall": "Neutral", "score": None, "momentum": "Stable",
                    "themes": [], "catalyst": "", "summary": "",
                }

            # Strip the JSON block from the visible analysis text
            before = analysis[:m.start()].strip()
            after  = analysis[m.end():].strip()
            analysis = (before + "\n\n" + after).strip() if before else after
        except (json.JSONDecodeError, KeyError, TypeError):
            if news:
                sent_data = {
                    "articles": [{**a, "sentiment": "Neutral", "impact": "Moderate",
                                  "type": "Other", "note": ""} for a in news],
                    "overall": "Neutral", "score": None, "momentum": "Stable",
                    "themes": [], "catalyst": "", "summary": "",
                }
    elif news:
        sent_data = {
            "articles": [{**a, "sentiment": "Neutral", "impact": "Moderate",
                          "type": "Other", "note": ""} for a in news],
            "overall": "Neutral", "score": None, "momentum": "Stable",
            "themes": [], "catalyst": "", "summary": "",
        }

    news_section  = _news_md_section(sent_data) + "\n" if sent_data else ""
    fin_tables    = _financial_statements_md(fin_data)
    research_md   = "\n" + _research_md_sections(research) if research else ""
    comp_md       = "\n" + _competitive_md_section(competitive, comp_assessment) if competitive else ""
    cov_md        = "\n" + _analyst_coverage_md_section(analyst_coverage, cov_assessment) if analyst_coverage else ""
    transcript_md = "\n" + _transcript_md_section(transcript_result) if transcript_result else ""
    sec_md        = "\n" + _sec_md_section(sec_result)              if sec_result        else ""
    markdown = (
        f"# {ticker} Stock Analysis — {date.today()}\n\n"
        f"{analysis}\n\n"
        f"{news_section}"
        f"{fin_tables}"
        f"{research_md}"
        f"{comp_md}"
        f"{cov_md}"
        f"{transcript_md}"
        f"{sec_md}"
    )
    return markdown, sent_data, comp_assessment, cov_assessment
