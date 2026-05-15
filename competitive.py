from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor

import requests
import yfinance as yf

_MAX_PEERS = 6
_MIN_PEERS = 3
_CAP_LO    = 0.20   # min market-cap multiplier vs target
_CAP_HI    = 5.00   # max market-cap multiplier vs target

_FMP_BASE = "https://financialmodelingprep.com/stable"


# ── FMP helpers (standalone — no cross-module imports) ────────────────────────

def _fmp_get(endpoint: str, params: dict) -> list | dict | None:
    """FMP REST call with timeout=10. Returns parsed JSON or None on any error."""
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            f"{_FMP_BASE}/{endpoint}",
            params={**params, "apikey": key},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _fmp_search_peers(query: str, target: str) -> list[str]:
    """Use FMP /search-name to find ticker candidates by industry/sector name.

    Returns a list of US-listed tickers (excluding target), or [] on failure.
    Used as a fallback when yfinance Industry/Sector API returns no results.
    """
    raw = _fmp_get("search-name", {"query": query, "limit": 25})
    if not raw or not isinstance(raw, list):
        return []
    us_exchanges = {"NASDAQ", "NYSE", "AMEX", "NYSE ARCA", "NASDAQ NM"}
    tickers = [
        r["symbol"] for r in raw
        if r.get("symbol")
        and r.get("symbol") != target
        and r.get("exchangeShortName", "") in us_exchanges
    ]
    return tickers[:20]


def _fmp_peer_profile(ticker: str) -> dict:
    """Fetch peer market cap and name from FMP /profile.

    Returns a partial info dict compatible with _extract_metrics().
    Used as fallback when yfinance returns empty info for a peer.
    """
    raw = _fmp_get("profile", {"symbol": ticker})
    if not raw or not isinstance(raw, list) or not raw[0]:
        return {}
    p = raw[0]
    return {
        "shortName":  p.get("companyName") or ticker,
        "marketCap":  p.get("mktCap"),
        # Margin/ratio fields not available from /profile — will render as N/A
        "revenueGrowth":    None,
        "grossMargins":     None,
        "operatingMargins": None,
        "returnOnEquity":   None,
        "debtToEquity":     None,
        "forwardPE":        None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_pct(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f * 100, 1)
    except (TypeError, ValueError):
        return None


def _safe_f(val, d: int = 1) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
    except (TypeError, ValueError):
        return None


def _fetch_info(ticker: str) -> tuple[str, dict]:
    """Fetch peer info via yfinance; fall back to FMP /profile if yfinance returns empty."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    if not info.get("marketCap"):
        fmp_info = _fmp_peer_profile(ticker)
        if fmp_info.get("marketCap"):
            return ticker, fmp_info
    return ticker, info


def _normalize(name: str) -> str:
    """yfinance Sector/Industry APIs require lowercase names."""
    return name.lower().replace(" ", "_")


def _candidate_tickers(industry: str, sector: str, target: str) -> tuple[list[str], str]:
    """Try yfinance Industry → Sector → FMP /search-name. Return (tickers, source_label)."""
    for name, src in [(industry, "industry"), (sector, "sector")]:
        if not name:
            continue
        for variant in [_normalize(name), name.lower()]:
            try:
                obj = yf.Industry(variant) if src == "industry" else yf.Sector(variant)
                top = obj.top_companies
                if top is not None and not top.empty:
                    tickers = [t for t in top.index.tolist() if t != target]
                    if len(tickers) >= _MIN_PEERS:
                        return tickers[:20], src
            except Exception:
                continue

    # FMP /search-name fallback — fires when both yfinance APIs return empty
    for query in filter(None, [industry, sector]):
        tickers = _fmp_search_peers(query, target)
        if len(tickers) >= _MIN_PEERS:
            return tickers, "fmp"

    return [], "none"


def _extract_metrics(ticker: str, info: dict) -> dict:
    return {
        "ticker":       ticker,
        "name":         (info.get("shortName") or ticker)[:22],
        "mktcap":       info.get("marketCap"),
        "rev_growth":   _safe_pct(info.get("revenueGrowth")),
        "gross_margin": _safe_pct(info.get("grossMargins")),
        "op_margin":    _safe_pct(info.get("operatingMargins")),
        "roe":          _safe_pct(info.get("returnOnEquity")),
        "de":           _safe_f(info.get("debtToEquity")),
        "fpe":          _safe_f(info.get("forwardPE")),
    }


def _median(vals: list) -> float | None:
    valid = sorted(v for v in vals if v is not None)
    if not valid:
        return None
    m = len(valid) // 2
    return round((valid[m - 1] + valid[m]) / 2, 1) if len(valid) % 2 == 0 else valid[m]


def _tercile(target_val, peer_vals: list) -> str:
    """Rank target_val against peer distribution (peers only, not target itself)."""
    if target_val is None:
        return "mid"
    valid_peers = [v for v in peer_vals if v is not None]
    if not valid_peers:
        return "mid"
    # What fraction of peers does the target beat?
    pct = sum(1 for v in valid_peers if v < target_val) / len(valid_peers)
    if pct >= 0.67:
        return "top"
    if pct <= 0.33:
        return "bot"
    return "mid"


# ── Entry point ───────────────────────────────────────────────────────────────

def run_competitive(ticker: str, stats: dict, fin_data: dict) -> dict:
    info     = stats["info"]
    tgt_cap  = info.get("marketCap")
    industry = info.get("industry") or ""
    sector   = info.get("sector") or ""

    if not tgt_cap:
        return {"error": "No market cap data for target"}

    candidates, source = _candidate_tickers(industry, sector, ticker)
    if not candidates:
        return {"error": f"No peer data available ({industry or sector or 'unknown sector'})"}

    # Parallel info fetch for all candidates
    with ThreadPoolExecutor(max_workers=8) as ex:
        peer_infos = dict(ex.map(_fetch_info, candidates))

    # Filter by market cap range, sort by proximity to target
    lo, hi = tgt_cap * _CAP_LO, tgt_cap * _CAP_HI
    eligible = [
        (t, peer_infos[t])
        for t in candidates
        if peer_infos.get(t, {}).get("marketCap") and lo <= peer_infos[t]["marketCap"] <= hi
    ]
    eligible.sort(key=lambda x: abs(x[1]["marketCap"] - tgt_cap))
    chosen = eligible[:_MAX_PEERS]

    if not chosen:
        return {"error": f"No peers in 0.2x–5x market-cap range for {ticker} ({source})"}

    tgt_m  = _extract_metrics(ticker, info)
    peer_m = [_extract_metrics(t, i) for t, i in chosen]

    # Compute peer medians and target tercile rankings
    fields  = ["rev_growth", "gross_margin", "op_margin", "roe", "fpe"]
    medians: dict = {}
    ranks:   dict = {}
    for f in fields:
        vals       = [p[f] for p in peer_m]
        medians[f] = _median(vals)
        ranks[f]   = _tercile(tgt_m[f], vals)

    if tgt_m["fpe"] and medians["fpe"]:
        ranks["fpe_premium_pct"] = round((tgt_m["fpe"] / medians["fpe"] - 1) * 100, 1)
    else:
        ranks["fpe_premium_pct"] = None

    warning = (
        f"Only {len(chosen)} peers found — results may be less representative"
        if len(chosen) < _MIN_PEERS else None
    )

    return {
        "error":        None,
        "warning":      warning,
        "source":       source,
        "industry":     industry,
        "sector":       sector,
        "target":       tgt_m,
        "peers":        peer_m,
        "peer_medians": medians,
        "rankings":     ranks,
    }
