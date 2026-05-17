"""M&A data layer — wraps lbo_fetcher.LBOInputs and adds M&A-specific fields.

Never rewrite data fetching logic — imports from lbo.lbo_fetcher exclusively.
Additional fields fetched here: EPS, P/E, analyst target, 52-week range, net income margin.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))
from lbo.lbo_fetcher import LBOInputs, fetch_lbo_inputs

_FMP_KEY = os.environ.get("FMP_API_KEY", "")


def _fmp(path: str, params: dict | None = None) -> list | dict | None:
    if not _FMP_KEY:
        return None
    try:
        p = params or {}
        p["apikey"] = _FMP_KEY
        r = requests.get(
            f"https://financialmodelingprep.com/api/v3/{path}",
            params=p, timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@dataclass
class MACompanyData:
    """Extends LBOInputs with M&A-specific fields."""
    # Core LBO data (re-exported for convenience)
    lbo: LBOInputs = None

    # Income statement extras
    net_income:          float = 0.0   # $M LTM
    net_margin:          float = 0.0   # %
    diluted_shares:      float = 0.0   # M shares (same as lbo.shares_outstanding)
    diluted_eps:         float = 0.0   # $ per share
    pe_multiple:         float = 0.0   # price / EPS

    # Credit proxy
    net_debt_ebitda:     float = 0.0
    credit_rating_proxy: str  = "Unknown"

    # Market data extras
    week52_high:         float = 0.0
    week52_low:          float = 0.0
    analyst_target:      float = 0.0   # mean price target $

    # Book value (for goodwill calc)
    book_equity:         float = 0.0   # $M

    # Warnings passthrough
    warnings:            list  = field(default_factory=list)


def fetch_ma_data(ticker: str) -> MACompanyData:
    """Fetch full M&A data package for a company."""
    d = MACompanyData()
    d.lbo = fetch_lbo_inputs(ticker)
    d.warnings = list(d.lbo.warnings)

    # ── Shares / EPS / P/E from yfinance ───────────────────────────────────────
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info or {}

    d.diluted_shares = d.lbo.shares_outstanding  # already in M

    # Net income: yfinance first, then derive from EBITDA margin
    ni_raw = info.get("netIncomeToCommon") or info.get("netIncome") or 0
    if ni_raw:
        d.net_income = ni_raw / 1e6
    elif d.lbo.ltm_ebitda > 0:
        # Approximate: EBITDA × 55% (accounts for D&A, interest, taxes at typical leverage)
        d.net_income = d.lbo.ltm_ebitda * 0.55

    # Try trailing EPS directly from yfinance
    trailing_eps = info.get("trailingEps") or 0.0
    if trailing_eps and trailing_eps > 0 and d.diluted_shares > 0:
        d.diluted_eps = trailing_eps
        d.net_income  = trailing_eps * d.diluted_shares  # re-anchor
    elif d.diluted_shares > 0 and d.net_income > 0:
        d.diluted_eps = d.net_income / d.diluted_shares

    # P/E multiple
    pe_raw = info.get("trailingPE") or info.get("forwardPE") or 0.0
    if pe_raw and pe_raw > 0:
        d.pe_multiple = pe_raw
    elif d.diluted_eps > 0 and d.lbo.share_price > 0:
        d.pe_multiple = d.lbo.share_price / d.diluted_eps

    # Net margin
    if d.lbo.ltm_revenue > 0 and d.net_income > 0:
        d.net_margin = d.net_income / d.lbo.ltm_revenue

    # Credit proxy
    if d.lbo.ltm_ebitda > 0:
        d.net_debt_ebitda = d.lbo.net_debt / d.lbo.ltm_ebitda
    d.credit_rating_proxy = (
        "Investment Grade" if d.net_debt_ebitda < 2.5
        else "Sub-Investment Grade"
    )

    # ── 52-week high / low ─────────────────────────────────────────────────────
    d.week52_high = info.get("fiftyTwoWeekHigh") or info.get("52WeekHigh") or 0.0
    d.week52_low  = info.get("fiftyTwoWeekLow")  or info.get("52WeekLow")  or 0.0

    # ── Analyst price target (FMP first, yfinance fallback) ────────────────────
    pt_data = _fmp(f"price-target/{ticker}", {"limit": 5})
    if pt_data and isinstance(pt_data, list) and pt_data:
        targets = [row.get("priceTarget") or 0 for row in pt_data if row.get("priceTarget")]
        d.analyst_target = sum(targets) / len(targets) if targets else 0.0
    if not d.analyst_target:
        d.analyst_target = info.get("targetMeanPrice") or 0.0

    # ── Book equity ────────────────────────────────────────────────────────────
    d.book_equity = d.lbo.book_equity  # already pulled in lbo_fetcher

    return d
