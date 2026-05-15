from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

_BASE = Path(__file__).parent
_WATCHLIST_PATH = _BASE / "watchlist.json"
_NTFY_TOPIC = "sam-madding-finance-alerts"
_NTFY_URL = f"https://ntfy.sh/{_NTFY_TOPIC}"
_ET = ZoneInfo("America/New_York")
_FMP_KEY = os.environ.get("FMP_API_KEY", "")


def load_watchlist() -> dict:
    with open(_WATCHLIST_PATH) as f:
        return json.load(f)


def get_tickers() -> list[str]:
    return load_watchlist().get("tickers", [])


def get_alert_thresholds() -> dict:
    return load_watchlist().get("alert_thresholds", {})


# ── Notifications ─────────────────────────────────────────────────────────────

def send_phone_notification(title: str, message: str,
                            priority: str = "default") -> bool:
    """POST to ntfy.sh. priority: 'default', 'high', 'urgent'."""
    try:
        r = requests.post(
            _NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "chart_with_upwards_trend",
            },
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False


def notify(title: str, message: str, priority: str = "default") -> None:
    send_phone_notification(title, message, priority)


# ── Number formatting ─────────────────────────────────────────────────────────

def format_large_number(n: float) -> str:
    if abs(n) >= 1e12:
        return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n/1e9:.1f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.1f}M"
    return f"${n:,.0f}"


def fmt_pct(n: float) -> str:
    sign = "+" if n >= 0 else ""
    return f"{sign}{n:.1f}%"


# ── Market status ─────────────────────────────────────────────────────────────

def get_market_status() -> str:
    """Return 'pre-market' / 'open' / 'after-hours' / 'closed'."""
    now = datetime.now(_ET)
    # Weekend
    if now.weekday() >= 5:
        return "closed"
    t = now.hour * 60 + now.minute
    if t < 4 * 60:          # before 4am
        return "closed"
    if t < 9 * 60 + 30:     # 4am - 9:29am
        return "pre-market"
    if t <= 16 * 60:        # 9:30am - 4:00pm
        return "open"
    if t <= 20 * 60:        # 4pm - 8pm
        return "after-hours"
    return "closed"


def is_market_hours() -> bool:
    return get_market_status() == "open"


def is_trading_day() -> bool:
    return datetime.now(_ET).weekday() < 5


# ── Quick quote via FMP ───────────────────────────────────────────────────────

def fetch_quick_quote(ticker: str) -> dict | None:
    """Return {price, change_pct, volume, market_cap, name} or None."""
    if not _FMP_KEY:
        return None
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{ticker}"
        r = requests.get(url, params={"apikey": _FMP_KEY}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        q = data[0]
        return {
            "price":      q.get("price", 0.0),
            "change_pct": q.get("changesPercentage", 0.0),
            "volume":     q.get("volume", 0),
            "avg_volume": q.get("avgVolume", 1),
            "market_cap": q.get("marketCap", 0),
            "name":       q.get("name", ticker),
            "day_high":   q.get("dayHigh", 0.0),
            "day_low":    q.get("dayLow", 0.0),
            "year_high":  q.get("yearHigh", 0.0),
            "year_low":   q.get("yearLow", 0.0),
        }
    except Exception:
        return None


def fetch_all_quotes(tickers: list[str]) -> dict[str, dict]:
    """Batch quote fetch for multiple tickers."""
    result: dict[str, dict] = {}
    if not _FMP_KEY or not tickers:
        return result
    try:
        joined = ",".join(tickers)
        url = f"https://financialmodelingprep.com/api/v3/quote/{joined}"
        r = requests.get(url, params={"apikey": _FMP_KEY}, timeout=15)
        r.raise_for_status()
        for q in r.json():
            sym = q.get("symbol", "")
            if sym:
                result[sym] = {
                    "price":      q.get("price", 0.0),
                    "change_pct": q.get("changesPercentage", 0.0),
                    "volume":     q.get("volume", 0),
                    "avg_volume": q.get("avgVolume", 1),
                    "market_cap": q.get("marketCap", 0),
                    "name":       q.get("name", sym),
                    "day_high":   q.get("dayHigh", 0.0),
                    "day_low":    q.get("dayLow", 0.0),
                    "year_high":  q.get("yearHigh", 0.0),
                    "year_low":   q.get("yearLow", 0.0),
                }
    except Exception:
        pass
    return result


# ── News via NewsAPI ──────────────────────────────────────────────────────────

def fetch_market_headlines(n: int = 5, hours_back: int = 12) -> list[dict]:
    """Return top n financial headlines from the last `hours_back` hours."""
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        return []
    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(hours=hours_back))
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "category": "business",
                "language": "en",
                "pageSize": n,
                "from":     since_str,
                "apiKey":   api_key,
            },
            timeout=10,
        )
        r.raise_for_status()
        articles = r.json().get("articles", [])
        return [
            {
                "title":  a.get("title", ""),
                "source": a.get("source", {}).get("name", ""),
                "url":    a.get("url", ""),
                "published": a.get("publishedAt", ""),
            }
            for a in articles[:n]
        ]
    except Exception:
        return []
