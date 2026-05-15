"""Morning market briefing — runs at 7am Mon-Fri via scheduled routine.

Usage: python3 automation/morning_briefing.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow imports from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic
import yfinance as yf

from automation.common import (
    fetch_all_quotes,
    fetch_market_headlines,
    fmt_pct,
    format_large_number,
    get_tickers,
    notify,
)

_ET = ZoneInfo("America/New_York")
_BASE = Path(__file__).parent
_OUT_DIR = _BASE / "briefings"
_OUT_DIR.mkdir(exist_ok=True)

_MACRO_SYMBOLS = {
    "10yr_yield": "^TNX",
    "vix":        "^VIX",
    "sp500":      "^GSPC",
    "nasdaq":     "^IXIC",
}


def _fetch_macro() -> dict:
    """Fetch macro indicators via yfinance."""
    result: dict = {}
    for label, sym in _MACRO_SYMBOLS.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="2d", interval="1d")
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                chg = ((last_close - prev_close) / prev_close) * 100
                result[label] = {"value": last_close, "change_pct": chg}
            elif len(hist) == 1:
                result[label] = {"value": float(hist["Close"].iloc[-1]), "change_pct": 0.0}
        except Exception:
            pass
    return result


def _build_payload(quotes: dict, macro: dict, headlines: list[dict]) -> str:
    """Assemble compact payload string for Claude."""
    lines: list[str] = []

    # Macro
    if macro:
        macro_parts = []
        for label, d in macro.items():
            v, chg = d.get("value", 0), d.get("change_pct", 0)
            if label == "10yr_yield":
                macro_parts.append(f"10yr={v:.2f}% ({fmt_pct(chg)})")
            elif label == "vix":
                macro_parts.append(f"VIX={v:.1f} ({fmt_pct(chg)})")
            elif label == "sp500":
                macro_parts.append(f"SPX={v:,.0f} ({fmt_pct(chg)})")
            elif label == "nasdaq":
                macro_parts.append(f"NDX={v:,.0f} ({fmt_pct(chg)})")
        lines.append("MACRO: " + " | ".join(macro_parts))

    # Watchlist movers
    if quotes:
        movers = sorted(
            [(sym, d) for sym, d in quotes.items()],
            key=lambda x: abs(x[1].get("change_pct", 0)),
            reverse=True,
        )
        mover_parts = []
        for sym, d in movers[:8]:
            pct = d.get("change_pct", 0.0)
            price = d.get("price", 0.0)
            mover_parts.append(f"{sym} ${price:.2f} ({fmt_pct(pct)})")
        lines.append("WATCHLIST: " + " | ".join(mover_parts))

    # Headlines
    if headlines:
        lines.append("HEADLINES:")
        for i, h in enumerate(headlines[:5], 1):
            lines.append(f"  {i}. [{h['source']}] {h['title']}")

    return "\n".join(lines)


def _generate_briefing(payload: str) -> str:
    """Call Claude sonnet to generate morning briefing narrative."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    prompt = f"""You are an institutional equity strategist writing the morning briefing for a hedge fund PM.
Be specific, data-grounded, and actionable. Use the morning-note framework.

Market data:
{payload}

Generate a morning briefing with exactly these sections:
MARKET TONE: [Risk-on / Risk-off / Neutral] | [one-sentence rationale citing specific data]
TOP MOVER: [ticker] [change%] — [one specific reason and key level to watch]
WATCH TODAY: (1) [specific event/level] (2) [specific event/level] (3) [specific event/level]
WATCHLIST MOVERS: [any stock ±2%+ with brief comment; skip if none]
KEY CATALYST: [single highest-conviction catalyst for today with specific trigger and magnitude]

Be concise. No filler. Cite numbers."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _find_top_mover(quotes: dict) -> tuple[str, float]:
    """Return (ticker, change_pct) for the biggest absolute mover."""
    if not quotes:
        return ("—", 0.0)
    top = max(quotes.items(), key=lambda x: abs(x[1].get("change_pct", 0)))
    return top[0], top[1].get("change_pct", 0.0)


def run() -> None:
    date_str = datetime.now(_ET).strftime("%Y%m%d")
    today_label = datetime.now(_ET).strftime("%A, %B %-d, %Y")
    print(f"[morning_briefing] Running for {today_label}...")

    tickers = get_tickers()

    # Parallel-ish: fetch all at once
    print("  Fetching watchlist quotes...")
    quotes = fetch_all_quotes(tickers)

    print("  Fetching macro indicators...")
    macro = _fetch_macro()

    print("  Fetching headlines...")
    headlines = fetch_market_headlines(n=5, hours_back=12)

    payload = _build_payload(quotes, macro, headlines)
    print(f"  Payload built ({len(payload)} chars). Calling Claude...")

    briefing_text = _generate_briefing(payload)

    # Compose full report
    report = f"""# Morning Market Briefing — {today_label}
*Generated {datetime.now(_ET).strftime('%H:%M ET')}*

---

{briefing_text}

---

## Watchlist Snapshot

| Ticker | Price | Change | Volume vs Avg |
|--------|-------|--------|---------------|
"""
    for sym in tickers:
        q = quotes.get(sym)
        if q:
            price = q["price"]
            pct   = q["change_pct"]
            vol   = q["volume"]
            avgvol= q["avg_volume"] or 1
            vol_ratio = vol / avgvol
            pct_str = fmt_pct(pct)
            report += f"| {sym} | ${price:.2f} | {pct_str} | {vol_ratio:.1f}x |\n"

    if macro:
        report += "\n## Macro\n\n"
        for label, d in macro.items():
            v   = d.get("value", 0)
            chg = d.get("change_pct", 0)
            if label == "10yr_yield":
                report += f"- **10yr Treasury**: {v:.3f}% ({fmt_pct(chg)})\n"
            elif label == "vix":
                report += f"- **VIX**: {v:.2f} ({fmt_pct(chg)})\n"
            elif label == "sp500":
                report += f"- **S&P 500**: {v:,.2f} ({fmt_pct(chg)})\n"
            elif label == "nasdaq":
                report += f"- **Nasdaq**: {v:,.2f} ({fmt_pct(chg)})\n"

    if headlines:
        report += "\n## Headlines\n\n"
        for h in headlines:
            report += f"- [{h['source']}] {h['title']}\n"

    # Save
    out_path = _OUT_DIR / f"{date_str}_morning_briefing.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"  Saved: {out_path}")

    # Notify
    top_sym, top_pct = _find_top_mover(quotes)
    # Extract tone label from briefing (first word after "MARKET TONE: ")
    tone = "—"
    for line in briefing_text.splitlines():
        if line.startswith("MARKET TONE:"):
            tone = line.split(":")[1].strip().split("|")[0].strip()
            break

    notif_title   = f"Morning Brief — {tone}"
    notif_message = f"{today_label}\n{fmt_pct(top_pct)} {top_sym} leads movers | {len(tickers)} watchlist stocks | briefing saved"

    notify(notif_title, notif_message)
    print(f"  Notifications sent: {notif_title}")
    print("\n" + "─" * 60)
    print(briefing_text)
    print("─" * 60)


if __name__ == "__main__":
    run()
