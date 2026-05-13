from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 600
SYSTEM_PROMPT = (
    "You are a financial analyst. Given this portfolio data, write a concise analysis "
    "covering: (1) overall risk profile, (2) sector concentration, (3) top 2 concerns, "
    "(4) one suggested improvement. Be direct. No disclaimers."
)


def build_payload(stats: dict) -> str:
    return json.dumps(stats, separators=(",", ":"))


def call_claude(payload: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": payload}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= threshold:
            return f"${v / threshold:.2f}{suffix}"
    return f"${v:,.0f}"


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value}{suffix}"


def _holdings_table(holdings: list[dict]) -> str:
    header = (
        "| Ticker | Weight | Sector | Price | Market Cap | P/E | 52W Low | 52W High | 6mo Return | Daily Vol |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for h in holdings:
        rows.append(
            "| {ticker} | {weight:.1%} | {sector} | {price} | {mcap} | {pe} | {low} | {high} | {ret} | {vol} |".format(
                ticker=h["ticker"],
                weight=h["weight"],
                sector=h["sector"] or "—",
                price=_fmt(h["current_price"]),
                mcap=_fmt_money(h["market_cap"]),
                pe=_fmt(h["trailing_pe"]),
                low=_fmt(h["fifty_two_week_low"]),
                high=_fmt(h["fifty_two_week_high"]),
                ret=_fmt(h["six_mo_return_pct"], "%"),
                vol=_fmt(h["daily_volatility_pct"], "%"),
            )
        )
    return header + "\n".join(rows)


def _correlation_table(corr: dict) -> str:
    tickers = list(corr.keys())
    header = "| | " + " | ".join(tickers) + " |\n"
    sep = "|" + "---|" * (len(tickers) + 1) + "\n"
    rows = []
    for row in tickers:
        cells = [f"{corr[row][col]:.3f}" if corr[row][col] is not None else "—" for col in tickers]
        rows.append(f"| **{row}** | " + " | ".join(cells) + " |")
    return header + sep + "\n".join(rows)


def _sector_table(sector_weights: dict) -> str:
    header = "| Sector | Weight |\n|---|---|\n"
    rows = [f"| {sector} | {weight:.1%} |" for sector, weight in sector_weights.items()]
    return header + "\n".join(rows)


def assemble_report(stats: dict, analysis: str) -> str:
    portfolio = stats["portfolio"]
    date_str = datetime.now().strftime("%Y-%m-%d")
    parts = [
        f"# Portfolio Report — {date_str}",
        "",
        "## Holdings",
        f"**Tickers:** {', '.join(portfolio['tickers'])}  ",
        f"**Equal weight per holding:** {portfolio['equal_weight']:.1%}  ",
        f"**Avg 6mo return:** {portfolio['avg_six_mo_return_pct']}%  ",
        f"**Avg daily volatility:** {portfolio['avg_daily_volatility_pct']}%",
        "",
        _holdings_table(stats["holdings"]),
        "",
        "## Sector Concentration",
        "",
        _sector_table(portfolio["sector_weights"]),
        "",
        "## Correlation Matrix (daily returns, 6mo)",
        "",
        _correlation_table(stats["correlation"]),
        "",
        "## Analyst Commentary",
        "",
        analysis,
        "",
    ]
    return "\n".join(parts)


def write_report(content: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"portfolio_{datetime.now().strftime('%Y%m%d')}.md"
    path = reports_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
