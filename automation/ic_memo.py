"""Investment Committee memo generator.

Usage:
  python3 automation/ic_memo.py TICKER
  python3 automation/ic_memo.py TICKER --thesis "AI infrastructure supercycle"
  python3 automation/ic_memo.py TICKER --recommendation BUY --conviction HIGH
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic

from automation.common import format_large_number, fmt_pct, notify

_ET = ZoneInfo("America/New_York")
_BASE = Path(__file__).parent
_MEMO_DIR = _BASE / "ic_memos"
_MEMO_DIR.mkdir(exist_ok=True)
_REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _run_pipeline(ticker: str) -> tuple[str, str]:
    """Run main.py --full for ticker. Returns (stdout, md_path)."""
    print(f"  Running full pipeline for {ticker}...")
    result = subprocess.run(
        [sys.executable, "main.py", ticker, "--full"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pipeline failed:\n{result.stderr[:500]}")

    # Find latest markdown report
    ticker_dir = _REPORTS_DIR / ticker
    md_files = sorted(ticker_dir.glob(f"{ticker}_*.md"), reverse=True)
    # Skip the *_latest.md symlink-style file for the timestamped one
    for f in md_files:
        if "latest" not in f.name:
            return result.stdout, str(f)
    raise RuntimeError(f"No markdown report found for {ticker}")


def _extract_key_data(md_text: str, ticker: str) -> dict:
    """Extract structured data from the markdown report for Claude payload."""
    lines = md_text.splitlines()
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current and buf:
                sections[current] = "\n".join(buf[:40]).strip()
            current = line[3:].strip()
            buf = []
        elif current:
            buf.append(line)
    if current and buf:
        sections[current] = "\n".join(buf[:40]).strip()

    # Grab first 120 chars of key sections for payload
    def snip(key: str) -> str:
        for k, v in sections.items():
            if key.lower() in k.lower():
                return v[:300]
        return ""

    return {
        "valuation":    snip("valuation"),
        "dcf":          snip("dcf"),
        "risks":        snip("risk"),
        "competitive":  snip("competitive"),
        "analyst":      snip("analyst"),
        "insider":      snip("insider"),
        "financials":   snip("financial"),
        "thesis":       snip("thesis"),
        "earnings":     snip("earning"),
        "sec":          snip("sec") or snip("filings"),
    }


def _build_ic_prompt(ticker: str, company_name: str, sections: dict,
                     user_thesis: str, recommendation: str, conviction: str,
                     current_price: float) -> str:
    today = datetime.now(_ET).strftime("%B %-d, %Y")

    payload_parts = []
    for key, val in sections.items():
        if val:
            payload_parts.append(f"[{key.upper()}]\n{val}")
    payload = "\n\n".join(payload_parts[:8])  # cap payload

    return f"""You are a senior portfolio manager writing an IC memo for a long/short equity fund.
Date: {today} | Ticker: {ticker} | Company: {company_name}
Current Price: ${current_price:.2f} | Recommendation: {recommendation} | Conviction: {conviction}
{f'Analyst thesis: {user_thesis}' if user_thesis else ''}

Research data:
{payload}

Write a formal Investment Committee Memorandum. Use EXACTLY this structure and headers:

---
INVESTMENT COMMITTEE MEMORANDUM
University of Cincinnati | Lindner College of Business | {today} | CONFIDENTIAL

RECOMMENDATION: {recommendation} {ticker} — {company_name}
Target Price: $[calculate from DCF/comps] | Current Price: ${current_price:.2f} | Implied Return: [X%]
Conviction: {conviction} | Time Horizon: 12 months
Position Size: [X% of portfolio based on conviction: HIGH=4-5%, MEDIUM=2-3%, LOW=1-2%]

## EXECUTIVE SUMMARY
[150 words max. What is the market missing? Single tight thesis.]

## INVESTMENT THESIS
1. [First falsifiable thesis point — cite specific metrics]
2. [Second falsifiable thesis point — cite specific metrics]
3. [Third falsifiable thesis point — cite specific metrics]

## VALUATION
[DCF intrinsic value, comps range, football field summary. Be specific — cite multiples.]

## FINANCIAL SNAPSHOT
[Key metrics table: revenue growth, EBITDA margin, FCF, P/E, EV/EBITDA, Net debt/EBITDA]

## RISK ASSESSMENT
1. [Risk] — Probability: [Low/Med/High] | Magnitude: [X% impact]
2. [Risk] — Probability: [Low/Med/High] | Magnitude: [X% impact]
3. [Risk] — Probability: [Low/Med/High] | Magnitude: [X% impact]

## COMPETITIVE POSITION
[Moat assessment, peer ranking, key differentiators — 3-4 sentences]

## ANALYST COVERAGE
[Consensus, upside to mean target, estimate revision trend]

## INSIDER ACTIVITY
[Signal label, conviction score, key transaction in last 90 days]

## RECOMMENDATION & POSITION SIZING
[Final recommendation with rationale. Position size with specific entry strategy.]

Prepared by: Samuel Madding
---

Be specific and institutional. Cite numbers. No filler."""


def _call_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _save_memo(ticker: str, memo_text: str) -> Path:
    date_str = datetime.now(_ET).strftime("%Y%m%d")
    out_path = _MEMO_DIR / f"{ticker}_{date_str}_ic_memo.md"
    out_path.write_text(memo_text, encoding="utf-8")
    return out_path


def run(ticker: str, user_thesis: str = "", recommendation: str = "BUY",
        conviction: str = "MEDIUM") -> None:
    ticker = ticker.upper()
    print(f"[ic_memo] Generating IC memo for {ticker}...")

    # 1. Run full pipeline
    _, md_path = _run_pipeline(ticker)
    print(f"  Pipeline complete. Reading {md_path}...")

    md_text = Path(md_path).read_text(encoding="utf-8")

    # Extract company name from report header
    company_name = ticker
    for line in md_text.splitlines():
        if line.startswith("# ") and ticker in line:
            company_name = line[2:].strip()
            break

    # Extract current price from report
    current_price = 0.0
    for line in md_text.splitlines():
        if "current price" in line.lower() or ("$" in line and "price" in line.lower()):
            import re
            m = re.search(r"\$(\d+(?:\.\d+)?)", line)
            if m:
                current_price = float(m.group(1))
                break

    # 2. Extract structured data
    sections = _extract_key_data(md_text, ticker)

    # 3. Generate IC memo
    print("  Calling Claude for IC memo generation...")
    prompt = _build_ic_prompt(
        ticker, company_name, sections,
        user_thesis, recommendation, conviction, current_price
    )
    memo_text = _call_claude(prompt)

    # 4. Save
    out_path = _save_memo(ticker, memo_text)
    print(f"  Saved: {out_path}")

    # 5. Notify
    notify(
        f"IC Memo Ready — {ticker} {recommendation}",
        f"{ticker} | {conviction} conviction | {recommendation}\nMemo saved to ic_memos/",
    )

    print("\n" + "─" * 60)
    print(memo_text[:1000] + ("\n..." if len(memo_text) > 1000 else ""))
    print("─" * 60)
    print(f"\nFull memo: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="ic_memo")
    parser.add_argument("ticker", help="Stock ticker (e.g. AAPL)")
    parser.add_argument("--thesis", default="", help="Investment thesis statement")
    parser.add_argument("--recommendation", default="BUY",
                        choices=["BUY", "SELL", "HOLD"], help="Recommendation")
    parser.add_argument("--conviction", default="MEDIUM",
                        choices=["HIGH", "MEDIUM", "LOW"], help="Conviction level")
    args = parser.parse_args()
    run(args.ticker, args.thesis, args.recommendation, args.conviction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
