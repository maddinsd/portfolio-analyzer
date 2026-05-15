"""Real-time market alert monitor — runs every 15 min during market hours.

Usage: python3 automation/notification_tool.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests

from automation.common import (
    fetch_all_quotes,
    fmt_pct,
    format_large_number,
    get_alert_thresholds,
    get_tickers,
    is_market_hours,
    notify,
    send_phone_notification,
)

_ET_TZ = ZoneInfo("America/New_York")
_BASE = Path(__file__).parent
_CACHE_PATH = _BASE / ".alert_cache.json"
_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_EDGAR_HEADERS = {"User-Agent": "SamuelMadding/1.0 sdmadding@icloud.com"}
_EDGAR_DELAY = 0.15


# ── Alert cache ───────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _already_sent(cache: dict, key: str) -> bool:
    """True if this alert was sent in the last 24 hours."""
    if key not in cache:
        return False
    sent_at = cache[key]
    try:
        sent_dt = datetime.fromisoformat(sent_at)
        return (datetime.now() - sent_dt) < timedelta(hours=24)
    except Exception:
        return False


def _mark_sent(cache: dict, key: str) -> None:
    cache[key] = datetime.now().isoformat()


# ── Checkers ──────────────────────────────────────────────────────────────────

def check_price_moves(quotes: dict, thresholds: dict) -> list[dict]:
    """Return alerts for price moves exceeding threshold."""
    threshold = thresholds.get("price_move_pct", 3.0)
    alerts = []
    for sym, q in quotes.items():
        pct = q.get("change_pct", 0.0)
        if abs(pct) >= threshold:
            price     = q["price"]
            year_high = q.get("year_high", 0)
            year_low  = q.get("year_low", 0)
            near_high = year_high > 0 and price >= year_high * 0.98
            near_low  = year_low > 0  and price <= year_low  * 1.02
            context   = ""
            if near_high:
                context = " — near 52-week high"
            elif near_low:
                context = " — near 52-week low"
            direction = "+" if pct >= 0 else ""
            alerts.append({
                "key":      f"price_{sym}_{datetime.now(_ET_TZ).strftime('%Y%m%d')}",
                "title":    f"{'🟢' if pct > 0 else '🔴'} PRICE ALERT — {sym} {direction}{pct:.1f}%",
                "message":  (f"{sym} ${price:.2f} ({direction}{pct:.1f}%){context}\n"
                             f"Vol: {q.get('volume',0)/q.get('avg_volume',1):.1f}x avg"),
                "priority": "high",
            })
    return alerts


def check_analyst_changes(tickers: list[str], thresholds: dict) -> list[dict]:
    """Check FMP for recent analyst target changes."""
    if not _FMP_KEY:
        return []
    alerts = []
    today = datetime.now(_ET_TZ).strftime("%Y-%m-%d")
    min_chg = thresholds.get("analyst_target_change_pct", 10.0)

    for sym in tickers:
        try:
            r = requests.get(
                f"https://financialmodelingprep.com/api/v3/analyst-stock-recommendations/{sym}",
                params={"apikey": _FMP_KEY, "limit": 5},
                timeout=10,
            )
            r.raise_for_status()
            items = r.json()
            for item in items:
                if item.get("date", "")[:10] != today:
                    continue
                rating_prev = item.get("previousGradingBuy", "")
                rating_new  = item.get("newGradingBuy", "")
                analyst     = item.get("analystCompany", "Unknown")
                # FMP recommendations endpoint
                action = item.get("recommendationMean") or ""
                grade  = item.get("newGrade") or item.get("grade") or action
                prev_grade = item.get("previousGrade") or ""
                if grade and grade != prev_grade and prev_grade:
                    upgrade = grade.lower() in {"strong buy", "buy", "outperform", "overweight"}
                    emoji   = "⬆️" if upgrade else "⬇️"
                    alerts.append({
                        "key":      f"analyst_{sym}_{today}_{analyst}",
                        "title":    f"{emoji} RATING CHANGE — {sym}",
                        "message":  f"{sym}: {prev_grade} → {grade} ({analyst})",
                        "priority": "default",
                    })
        except Exception:
            pass
    return alerts


def check_earnings_surprises(tickers: list[str], thresholds: dict) -> list[dict]:
    """Check FMP for recent earnings surprises."""
    if not _FMP_KEY:
        return []
    alerts = []
    threshold = thresholds.get("earnings_surprise_pct", 5.0)
    today = datetime.now(_ET_TZ).strftime("%Y-%m-%d")

    for sym in tickers:
        try:
            r = requests.get(
                f"https://financialmodelingprep.com/api/v3/earnings-surprises/{sym}",
                params={"apikey": _FMP_KEY},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                continue
            latest = data[0]
            # Only alert if filed today or yesterday
            date_str = latest.get("date", "")
            if not date_str or date_str[:10] < (datetime.now(_ET_TZ) - timedelta(days=1)).strftime("%Y-%m-%d"):
                continue
            actual = latest.get("actualEarningResult", 0) or 0
            est    = latest.get("estimatedEarning", 0) or 0
            if est == 0:
                continue
            surprise_pct = ((actual - est) / abs(est)) * 100
            if abs(surprise_pct) >= threshold:
                direction  = "BEAT" if surprise_pct > 0 else "MISS"
                emoji      = "🟢" if surprise_pct > 0 else "🔴"
                alerts.append({
                    "key":      f"earnings_{sym}_{date_str}",
                    "title":    f"{emoji} EARNINGS {direction} — {sym}",
                    "message":  (f"{sym} EPS ${actual:.2f} vs ${est:.2f}E "
                                 f"({fmt_pct(surprise_pct)} surprise)"),
                    "priority": "high",
                })
        except Exception:
            pass
    return alerts


def check_insider_buys(tickers: list[str], thresholds: dict) -> list[dict]:
    """Check EDGAR for recent insider buys above threshold."""
    min_usd = thresholds.get("insider_buy_min_usd", 1_000_000)
    alerts  = []

    # Reuse CIK lookup logic (no cross-import)
    try:
        time.sleep(_EDGAR_DELAY)
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_EDGAR_HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        cik_map = {}
        for entry in r.json().values():
            t = entry.get("ticker", "").upper()
            if t in tickers:
                cik_map[t] = str(entry["cik_str"]).zfill(10)
    except Exception:
        return []

    cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    for sym, cik10 in cik_map.items():
        try:
            time.sleep(_EDGAR_DELAY)
            r2 = requests.get(
                f"https://data.sec.gov/submissions/CIK{cik10}.json",
                headers=_EDGAR_HEADERS,
                timeout=20,
            )
            r2.raise_for_status()
            subs = r2.json()
            recent = subs["filings"]["recent"]
            forms  = recent.get("form", [])
            dates  = recent.get("filingDate", [])
            accs   = recent.get("accessionNumber", [])
            cik_int = int(subs.get("cik", 0))

            for i, f in enumerate(forms):
                if f != "4" or dates[i] < cutoff:
                    if dates[i] < cutoff:
                        break
                    continue
                acc_clean = accs[i].replace("-", "")
                url = (f"https://www.sec.gov/Archives/edgar/data/"
                       f"{cik_int}/{acc_clean}/form4.xml")
                time.sleep(_EDGAR_DELAY)
                try:
                    r3 = requests.get(url, headers=_EDGAR_HEADERS, timeout=15)
                    r3.raise_for_status()
                    root = ET.fromstring(r3.text)
                except Exception:
                    continue

                is_10b5 = (root.findtext("aff10b5One") or "").lower() == "true"
                owner = root.find("reportingOwner")
                if owner is None:
                    continue
                name  = (owner.findtext("reportingOwnerId/rptOwnerName") or "Unknown").strip()
                title = (owner.findtext("reportingOwnerRelationship/officerTitle") or "Insider").strip()

                for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
                    code = (tx.findtext("transactionCoding/transactionCode") or "").upper()
                    if code != "P" or is_10b5:
                        continue
                    try:
                        shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
                        price  = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
                    except (ValueError, TypeError):
                        continue
                    value = shares * price
                    if value < min_usd:
                        continue
                    alert_key = f"insider_buy_{sym}_{name}_{dates[i]}"
                    alerts.append({
                        "key":      alert_key,
                        "title":    f"💼 INSIDER BUY — {sym}",
                        "message":  (f"{name} ({title}) purchased "
                                     f"{format_large_number(value)} of {sym} "
                                     f"@ ${price:.2f} (open market)"),
                        "priority": "high",
                    })
        except Exception:
            pass

    return alerts


def check_new_filings(tickers: list[str]) -> list[dict]:
    """Check EDGAR for new 10-K or 10-Q filings today."""
    alerts = []
    today  = datetime.now().strftime("%Y-%m-%d")

    try:
        time.sleep(_EDGAR_DELAY)
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_EDGAR_HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        cik_map = {}
        for entry in r.json().values():
            t = entry.get("ticker", "").upper()
            if t in tickers:
                cik_map[t] = str(entry["cik_str"]).zfill(10)
    except Exception:
        return []

    for sym, cik10 in cik_map.items():
        try:
            time.sleep(_EDGAR_DELAY)
            r2 = requests.get(
                f"https://data.sec.gov/submissions/CIK{cik10}.json",
                headers=_EDGAR_HEADERS,
                timeout=20,
            )
            r2.raise_for_status()
            subs   = r2.json()
            recent = subs["filings"]["recent"]
            forms  = recent.get("form", [])
            dates  = recent.get("filingDate", [])

            for i, f in enumerate(forms):
                if dates[i] < today:
                    break
                if f in {"10-K", "10-Q"}:
                    alerts.append({
                        "key":      f"filing_{sym}_{f}_{today}",
                        "title":    f"📄 NEW FILING — {sym} {f}",
                        "message":  f"{sym} filed {f} with SEC today — key sections available",
                        "priority": "default",
                    })
        except Exception:
            pass

    return alerts


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    now_et = datetime.now(_ET_TZ)
    print(f"[notification_tool] {now_et.strftime('%Y-%m-%d %H:%M ET')}")

    if not is_market_hours():
        status = "closed" if now_et.weekday() >= 5 else "outside market hours"
        print(f"  Market {status} — exiting.")
        return

    tickers    = get_tickers()
    thresholds = get_alert_thresholds()
    cache      = _load_cache()

    # Collect all potential alerts
    print("  Fetching quotes for price checks...")
    quotes = fetch_all_quotes(tickers)
    all_alerts: list[dict] = []
    all_alerts.extend(check_price_moves(quotes, thresholds))

    print("  Checking analyst changes...")
    all_alerts.extend(check_analyst_changes(tickers, thresholds))

    print("  Checking earnings surprises...")
    all_alerts.extend(check_earnings_surprises(tickers, thresholds))

    print("  Checking insider buys (EDGAR)...")
    all_alerts.extend(check_insider_buys(tickers, thresholds))

    print("  Checking new filings (EDGAR)...")
    all_alerts.extend(check_new_filings(tickers))

    # Deduplicate and send
    sent_count = 0
    for alert in all_alerts:
        key = alert["key"]
        if _already_sent(cache, key):
            print(f"  [dup] {key}")
            continue
        title    = alert["title"]
        message  = alert["message"]
        priority = alert.get("priority", "default")
        send_phone_notification(title, message, priority)
        _mark_sent(cache, key)
        print(f"  [sent] {title}")
        sent_count += 1

    _save_cache(cache)
    print(f"  Done — {sent_count} new alerts sent, {len(all_alerts) - sent_count} suppressed (dedup).")


if __name__ == "__main__":
    run()
