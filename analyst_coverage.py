from __future__ import annotations

import math
import os
import sys

import requests

_FMP_BASE = "https://financialmodelingprep.com/stable"


def _fmp_get(endpoint: str, params: dict) -> list | dict | None:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            f"{_FMP_BASE}/{endpoint}",
            params={**params, "apikey": key},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _safe_f(val, d: int = 2) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
    except (TypeError, ValueError):
        return None


def _get_buy(rec: dict) -> int:
    return (int(rec.get("analystRatingsStrongBuy") or rec.get("analystRatingsstrongBuy") or 0)
            + int(rec.get("analystRatingsbuy") or rec.get("analystRatingsBuy") or 0))


def _get_hold(rec: dict) -> int:
    return int(rec.get("analystRatingsHold") or rec.get("analystRatingshold") or 0)


def _get_sell(rec: dict) -> int:
    return (int(rec.get("analystRatingsStrongSell") or rec.get("analystRatingsstrongSell") or 0)
            + int(rec.get("analystRatingsSell") or rec.get("analystRatingssell") or 0))


def _estimate_distribution(recommendation_mean: float | None, n_analysts: int) -> tuple[int, int, int]:
    """Derive buy/hold/sell counts from recommendationMean when FMP returns no distribution."""
    rm = recommendation_mean or 2.5
    n  = n_analysts or 0
    if rm < 1.5:
        buy_pct, hold_pct, sell_pct = 0.85, 0.15, 0.00
    elif rm < 2.0:
        buy_pct, hold_pct, sell_pct = 0.70, 0.25, 0.05
    elif rm < 2.5:
        buy_pct, hold_pct, sell_pct = 0.55, 0.35, 0.10
    else:
        buy_pct, hold_pct, sell_pct = 0.20, 0.60, 0.20
    return int(n * buy_pct), int(n * hold_pct), int(n * sell_pct)


def run_analyst_coverage(ticker: str, stats: dict, fin_data: dict) -> dict:
    """Fetch analyst coverage from FMP; fall back to yfinance on failure. Never raises."""
    raw_recs    = _fmp_get("analyst-stock-recommendations", {"symbol": ticker, "limit": 6})
    raw_targets = _fmp_get("price-target", {"symbol": ticker, "limit": 10})
    raw_est     = _fmp_get("analyst-estimates", {"symbol": ticker, "period": "quarter", "limit": 4})

    info          = stats.get("info", {})
    current_price = _safe_f(stats.get("current_price"))

    # ── Rating distribution ───────────────────────────────────────────────────
    buy_count = hold_count = sell_count = 0
    if raw_recs and isinstance(raw_recs, list):
        rec        = raw_recs[0]
        buy_count  = _get_buy(rec)
        hold_count = _get_hold(rec)
        sell_count = _get_sell(rec)
        if buy_count == 0 and hold_count == 0 and sell_count == 0:
            print(f"  [analyst_coverage] FMP rec fields all zero for {ticker}. "
                  f"Raw keys: {list(rec.keys())[:12]}", file=sys.stderr)
    elif raw_recs is None:
        print(f"  [analyst_coverage] FMP analyst-stock-recommendations returned None for {ticker}", file=sys.stderr)

    total_analysts = buy_count + hold_count + sell_count
    bull_ratio     = round(buy_count / total_analysts * 100, 1) if total_analysts > 0 else None

    # FMP distribution unavailable — derive from yfinance recommendationMean
    if total_analysts == 0:
        n_yf = info.get("numberOfAnalystOpinions") or 0
        rec_mean = info.get("recommendationMean")
        if n_yf > 0:
            buy_count, hold_count, sell_count = _estimate_distribution(rec_mean, n_yf)
            total_analysts = buy_count + hold_count + sell_count
            bull_ratio = round(buy_count / total_analysts * 100, 1) if total_analysts > 0 else None
            print(f"  [analyst_coverage] Using estimated distribution from recommendationMean={rec_mean:.2f}: "
                  f"buy={buy_count} hold={hold_count} sell={sell_count}", file=sys.stderr)

    if bull_ratio is not None:
        consensus_rating = "Buy" if bull_ratio >= 60 else ("Sell" if bull_ratio <= 30 else "Hold")
    else:
        rec_mean = info.get("recommendationMean")
        if rec_mean is not None:
            consensus_rating = "Buy" if rec_mean <= 2.0 else ("Hold" if rec_mean <= 3.0 else "Sell")
        else:
            consensus_rating = None

    # ── Price targets ─────────────────────────────────────────────────────────
    mean_target = high_target = low_target = None
    recent_targets: list[dict] = []

    if raw_targets and isinstance(raw_targets, list):
        valid = [_safe_f(t.get("priceTarget")) for t in raw_targets if t.get("priceTarget") is not None]
        if valid:
            mean_target = round(sum(valid) / len(valid), 2)
            high_target = max(valid)
            low_target  = min(valid)
        for t in raw_targets[:5]:
            pt = _safe_f(t.get("priceTarget"))
            if pt is None:
                continue
            recent_targets.append({
                "firm":         t.get("analystCompany") or "—",
                "analyst":      t.get("analystName") or "—",
                "price_target": pt,
                "date":         (t.get("publishedDate") or "")[:10],
            })

    # yfinance fallback for mean target
    if mean_target is None:
        mean_target = _safe_f(info.get("targetMeanPrice"))

    # yfinance fallback for analyst count
    if total_analysts == 0:
        total_analysts = info.get("numberOfAnalystOpinions") or 0

    upside_pct = None
    if mean_target and current_price and current_price > 0:
        upside_pct = round((mean_target - current_price) / current_price * 100, 1)

    target_spread_pct = None
    if high_target and low_target and low_target > 0:
        target_spread_pct = round((high_target - low_target) / low_target * 100, 1)

    # ── EPS / Revenue estimates ───────────────────────────────────────────────
    estimates: list[dict] = []
    if raw_est and isinstance(raw_est, list):
        for e in raw_est[:4]:
            est_date = (e.get("date") or "")[:7]
            if not est_date:
                continue
            estimates.append({
                "date":       est_date,
                "eps_est":    _safe_f(e.get("epsAvg")),
                "eps_high":   _safe_f(e.get("epsHigh")),
                "eps_low":    _safe_f(e.get("epsLow")),
                "rev_est":    _safe_f(e.get("revenueAvg"), d=0),
                "rev_high":   _safe_f(e.get("revenueHigh"), d=0),
                "rev_low":    _safe_f(e.get("revenueLow"), d=0),
                "n_analysts": e.get("numberAnalystEstimatedRevenue") or e.get("numberAnalysts"),
            })

    if not mean_target and not total_analysts:
        return {"error": f"No analyst coverage data available for {ticker}"}

    return {
        "error":             None,
        "ticker":            ticker,
        "consensus_rating":  consensus_rating,
        "buy_count":         buy_count,
        "hold_count":        hold_count,
        "sell_count":        sell_count,
        "total_analysts":    total_analysts,
        "bull_ratio":        bull_ratio,
        "mean_target":       mean_target,
        "high_target":       high_target,
        "low_target":        low_target,
        "current_price":     current_price,
        "upside_pct":        upside_pct,
        "target_spread_pct": target_spread_pct,
        "estimates":         estimates,
        "recent_targets":    recent_targets,
    }
