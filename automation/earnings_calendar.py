"""Earnings calendar monitor — runs Mon 6:30am (weekly) + daily 7:30am.

Usage: python3 automation/earnings_calendar.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests
import yfinance as yf

from automation.common import (
    fmt_pct,
    get_tickers,
    notify,
    send_mac_notification,
)

_ET = ZoneInfo("America/New_York")
_BASE = Path(__file__).parent
_CAL_DIR = _BASE / "calendars"
_CAL_DIR.mkdir(exist_ok=True)
_FMP_KEY = os.environ.get("FMP_API_KEY", "")

_WEEKDAY = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


def _fmp_get(path: str, params: dict | None = None) -> list | dict | None:
    if not _FMP_KEY:
        return None
    try:
        p = params or {}
        p["apikey"] = _FMP_KEY
        r = requests.get(
            f"https://financialmodelingprep.com/api/v3/{path}",
            params=p,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_earnings_calendar(tickers: list[str], days_ahead: int = 28) -> dict[str, dict]:
    """Return {ticker: {date, eps_est, rev_est, time}} for upcoming earnings."""
    result: dict[str, dict] = {}
    today      = datetime.now(_ET).date()
    end_date   = today + timedelta(days=days_ahead)
    today_str  = today.strftime("%Y-%m-%d")
    end_str    = end_date.strftime("%Y-%m-%d")

    # FMP batch earnings calendar
    data = _fmp_get("earning_calendar", {"from": today_str, "to": end_str})
    if data:
        for item in data:
            sym = item.get("symbol", "").upper()
            if sym not in tickers:
                continue
            result[sym] = {
                "date":     item.get("date", ""),
                "eps_est":  item.get("epsEstimated"),
                "rev_est":  item.get("revenueEstimated"),
                "time":     item.get("time", ""),  # "bmo" / "amc" / ""
                "eps_act":  item.get("eps"),
                "rev_act":  item.get("revenue"),
            }

    # Fallback: yfinance for any tickers still missing
    for sym in tickers:
        if sym in result:
            continue
        try:
            t = yf.Ticker(sym)
            info = t.info
            next_date = info.get("earningsDate") or info.get("earningsTimestamp")
            if next_date:
                if isinstance(next_date, (int, float)):
                    next_date = datetime.fromtimestamp(next_date).strftime("%Y-%m-%d")
                result[sym] = {
                    "date":    str(next_date)[:10],
                    "eps_est": info.get("forwardEps"),
                    "rev_est": None,
                    "time":    "",
                    "eps_act": None,
                    "rev_act": None,
                }
        except Exception:
            pass

    return result


def fetch_last_earnings(ticker: str) -> dict:
    """Return last quarter's actual vs estimate."""
    data = _fmp_get(f"earnings-surprises/{ticker}")
    if data and isinstance(data, list) and data:
        last = data[0]
        eps_act = last.get("actualEarningResult", 0) or 0
        eps_est = last.get("estimatedEarning", 0) or 0
        surprise = ((eps_act - eps_est) / abs(eps_est) * 100) if eps_est != 0 else 0
        return {
            "date":     last.get("date", "")[:10],
            "eps_act":  eps_act,
            "eps_est":  eps_est,
            "surprise": surprise,
        }
    return {}


def fetch_implied_move(ticker: str) -> float | None:
    """Estimate implied move from nearest ATM straddle (yfinance options)."""
    try:
        t   = yf.Ticker(ticker)
        exp = t.options
        if not exp:
            return None
        nearest = exp[0]
        chain = t.option_chain(nearest)
        price = t.info.get("regularMarketPrice") or t.history(period="1d")["Close"].iloc[-1]
        # Find ATM call + put
        calls = chain.calls
        puts  = chain.puts
        # Nearest strike to current price
        atm_strike = min(calls["strike"].tolist(), key=lambda x: abs(x - price))
        call_row   = calls[calls["strike"] == atm_strike]
        put_row    = puts[puts["strike"] == atm_strike]
        if call_row.empty or put_row.empty:
            return None
        call_mid = (call_row["bid"].values[0] + call_row["ask"].values[0]) / 2
        put_mid  = (put_row["bid"].values[0]  + put_row["ask"].values[0])  / 2
        straddle = call_mid + put_mid
        return (straddle / price) * 100
    except Exception:
        return None


def _days_until(date_str: str) -> int:
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (d - datetime.now(_ET).date()).days
    except Exception:
        return 999


def _time_label(time_code: str) -> str:
    if time_code == "bmo":
        return "BMO"   # before market open
    if time_code == "amc":
        return "AMC"   # after market close
    return "TBD"


def run_preview(ticker: str) -> None:
    """Run main.py --dry-run and generate pre-earnings note."""
    print(f"    Running pre-earnings preview for {ticker}...")
    result = subprocess.run(
        [sys.executable, "main.py", ticker, "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    if result.returncode == 0:
        print(f"    Preview data fetched for {ticker}.")
    else:
        print(f"    Warning: dry-run for {ticker} had errors: {result.stderr[:200]}")


def build_calendar_report(
    upcoming: dict[str, dict],
    last_earnings: dict[str, dict],
) -> str:
    today = datetime.now(_ET)
    week_str = today.strftime("%Y-W%V")

    lines = [
        f"# Earnings Calendar — Week of {today.strftime('%B %-d, %Y')}",
        f"*Generated {today.strftime('%H:%M ET')}*\n",
        "## Upcoming Earnings (Next 28 Days)\n",
        "| Ticker | Date | Day | Time | Days | EPS Est | Rev Est | Impl Move | Last Surp |",
        "|--------|------|-----|------|------|---------|---------|-----------|-----------|",
    ]

    sorted_upcoming = sorted(
        upcoming.items(),
        key=lambda x: x[1].get("date", "9999"),
    )

    for sym, info in sorted_upcoming:
        date_str = info.get("date", "—")
        days     = _days_until(date_str)
        try:
            day_name = _WEEKDAY.get(datetime.strptime(date_str[:10], "%Y-%m-%d").weekday(), "—")
        except Exception:
            day_name = "—"
        time_lbl = _time_label(info.get("time", ""))
        eps_est  = info.get("eps_est")
        rev_est  = info.get("rev_est")
        eps_str  = f"${eps_est:.2f}" if eps_est is not None else "—"
        rev_str  = f"${rev_est/1e9:.1f}B" if rev_est and rev_est > 1e8 else ("—" if not rev_est else f"${rev_est:.0f}")

        # Implied move
        impl = last_earnings.get(sym, {}).get("_implied")
        impl_str = f"±{impl:.1f}%" if impl else "—"

        # Last earnings surprise
        last = last_earnings.get(sym, {})
        surp = last.get("surprise")
        surp_str = fmt_pct(surp) if surp is not None else "—"

        lines.append(
            f"| **{sym}** | {date_str[:10]} | {day_name} | {time_lbl} | "
            f"{days}d | {eps_str} | {rev_str} | {impl_str} | {surp_str} |"
        )

    return "\n".join(lines)


def run() -> None:
    today = datetime.now(_ET)
    print(f"[earnings_calendar] {today.strftime('%Y-%m-%d %H:%M ET')}")

    tickers = get_tickers()

    print("  Fetching earnings calendar (FMP + yfinance)...")
    upcoming = fetch_earnings_calendar(tickers, days_ahead=28)
    print(f"  Found {len(upcoming)} upcoming earnings dates.")

    # Fetch last earnings surprise for all, plus implied move for near-term
    last_earnings: dict[str, dict] = {}
    for sym in tickers:
        last = fetch_last_earnings(sym)
        last_earnings[sym] = last

    # Identify stocks reporting soon
    reporting_1_2d  = [(sym, info) for sym, info in upcoming.items() if 0 <= _days_until(info["date"]) <= 2]
    reporting_3_7d  = [(sym, info) for sym, info in upcoming.items() if 3 <= _days_until(info["date"]) <= 7]

    # Run pre-earnings preview for T-1 and T-2 stocks
    if reporting_1_2d:
        print(f"\n  [{len(reporting_1_2d)} stocks report in 1-2 days — generating previews]")
        for sym, info in reporting_1_2d:
            # Fetch implied move
            impl = fetch_implied_move(sym)
            if impl:
                last_earnings.setdefault(sym, {})["_implied"] = impl
            run_preview(sym)
            notify(
                f"Earnings T-{_days_until(info['date'])} — {sym}",
                f"{sym} reports {info['date'][:10]} {_time_label(info.get('time',''))} | "
                f"Pre-earnings preview generated",
                priority="high",
            )

    # Send reminder notifications for T-3 to T-7
    if reporting_3_7d:
        print(f"\n  [{len(reporting_3_7d)} stocks report in 3-7 days — sending reminders]")
        for sym, info in reporting_3_7d:
            days = _days_until(info["date"])
            eps_est = info.get("eps_est")
            eps_str = f"EPS est ${eps_est:.2f}" if eps_est else ""
            send_mac_notification(
                f"Earnings in {days} days — {sym}",
                f"{sym} reports {info['date'][:10]} {_time_label(info.get('time',''))} | {eps_str}",
            )

    # Build and save calendar report
    report = build_calendar_report(upcoming, last_earnings)
    week_str = today.strftime("%YW%V")
    out_path = _CAL_DIR / f"{week_str}_earnings_calendar.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n  Calendar saved: {out_path}")

    # Summary notification
    week_schedule = ", ".join(
        f"{sym} ({info['date'][5:10]})"
        for sym, info in sorted(upcoming.items(), key=lambda x: x[1]["date"])
        if _days_until(info["date"]) <= 7
    ) or "None this week"

    notify(
        "Earnings Calendar Updated",
        f"This week: {week_schedule}",
    )

    print("\n" + "─" * 60)
    print(report[:800])
    if len(report) > 800:
        print("...")
    print("─" * 60)


if __name__ == "__main__":
    run()
