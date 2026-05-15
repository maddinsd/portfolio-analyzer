from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests
import yfinance as yf

INFO_FIELDS = [
    "currentPrice", "previousClose", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
    "twoHundredDayAverage", "sector", "industry", "longBusinessSummary",
    "shortName", "longName",
    "beta", "sharesOutstanding", "impliedSharesOutstanding",
    "totalRevenue", "grossMargins", "operatingMargins", "profitMargins",
    "totalDebt", "freeCashflow", "dividendYield", "trailingEps", "forwardEps",
    "recommendationMean", "targetMeanPrice", "numberOfAnalystOpinions",
]

_FMP_BASE = "https://financialmodelingprep.com/stable"


# ── FMP helpers ───────────────────────────────────────────────────────────────

def _fmp_get(endpoint: str, params: dict) -> list | dict | None:
    """Single FMP request. Returns parsed JSON or None on any error. Never raises."""
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


def _fmp_to_income_df(records: list | None):
    """Convert FMP /income-statement records to a yfinance-style financials DataFrame.

    Returns a DataFrame with rows = income line items, columns = pd.Timestamps
    (descending, most-recent first), or None if records are empty/invalid.
    """
    try:
        import pandas as pd
        if not records or not isinstance(records, list):
            return None
        rows: dict[str, list] = {
            "Total Revenue":    [],
            "Gross Profit":     [],
            "Operating Income": [],
            "Net Income":       [],
        }
        dates: list = []
        for rec in records[:4]:
            date_str = rec.get("date") or rec.get("fillingDate") or ""
            if not date_str:
                continue
            ts = pd.Timestamp(date_str)
            dates.append(ts)
            rows["Total Revenue"].append(rec.get("revenue"))
            rows["Gross Profit"].append(rec.get("grossProfit"))
            rows["Operating Income"].append(rec.get("operatingIncome"))
            rows["Net Income"].append(rec.get("netIncome"))
        if not dates:
            return None
        # Build DataFrame: rows=dates, cols=metrics → then transpose
        df = pd.DataFrame(rows, index=dates).T
        # Columns already in descending order (FMP default)
        return df
    except Exception:
        return None


# ── News ──────────────────────────────────────────────────────────────────────

def fetch_news(ticker: str, company_name: str) -> list[dict]:
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        print("Error: NEWS_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    query = f"{ticker} {company_name}"
    from_date = (date.today() - timedelta(days=7)).isoformat()
    params = urllib.parse.urlencode({
        "q": query,
        "from": from_date,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": 5,
        "apiKey": api_key,
    })
    url = f"https://newsapi.org/v2/everything?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "portfolio-analyzer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Warning: NewsAPI request failed: {e}", file=sys.stderr)
        return []

    if data.get("status") != "ok":
        print(f"Warning: NewsAPI error: {data.get('message', 'unknown')}", file=sys.stderr)
        return []

    articles = []
    for a in data.get("articles", [])[:5]:
        headline = (a.get("title") or "").strip()
        if not headline or headline == "[Removed]":
            continue
        articles.append({
            "headline": headline[:120],
            "source":   a.get("source", {}).get("name", ""),
            "date":     (a.get("publishedAt") or "")[:10],
            "url":      a.get("url", ""),
        })
    return articles


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_stock_data(ticker: str) -> dict:
    t = yf.Ticker(ticker)

    price_history = t.history(period="6mo", interval="1d", auto_adjust=True)
    if price_history.empty:
        print(f"Error: '{ticker}' is not a valid ticker or has no data.", file=sys.stderr)
        sys.exit(1)

    raw_info = t.info or {}
    if not raw_info.get("currentPrice") and not raw_info.get("regularMarketPrice"):
        print(f"Error: No market data found for '{ticker}'.", file=sys.stderr)
        sys.exit(1)

    # ── Parallel: S&P 500 + four FMP calls ───────────────────────────────────
    # FMP calls fire concurrently while yfinance DataFrames are fetched below.
    # Each FMP call is capped at 10s; failures return None silently.
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_sp500     = ex.submit(
            lambda: yf.Ticker("^GSPC").history(period="6mo", interval="1d", auto_adjust=True)
        )
        f_income_a  = ex.submit(_fmp_get, "income-statement", {"symbol": ticker})
        f_income_q  = ex.submit(_fmp_get, "income-statement",
                                {"symbol": ticker, "period": "quarter"})
        f_profile   = ex.submit(_fmp_get, "profile", {"symbol": ticker})
        f_quote     = ex.submit(_fmp_get, "quote",   {"symbol": ticker})

        # yfinance DataFrames (sequential on the same Ticker object)
        financials_yf           = t.financials
        quarterly_financials_yf = t.quarterly_financials
        balance_sheet           = t.balance_sheet
        quarterly_balance_sheet = t.quarterly_balance_sheet
        cashflow                = t.cashflow
        quarterly_cashflow      = t.quarterly_cashflow

        sp500_history = f_sp500.result()
        fmp_income_a  = f_income_a.result()
        fmp_income_q  = f_income_q.result()
        fmp_profile   = f_profile.result()
        fmp_quote     = f_quote.result()

    # ── Build info dict (yfinance base + FMP additive fields) ─────────────────
    info = {field: raw_info.get(field) for field in INFO_FIELDS}

    # FMP profile: additive — CEO, employees, city, state, exchange, IPO date
    fmp_p = (fmp_profile or [{}])[0] if isinstance(fmp_profile, list) else {}
    if fmp_p:
        info["fmp_ceo"]       = fmp_p.get("ceo")
        info["fmp_employees"] = fmp_p.get("fullTimeEmployees")
        info["fmp_city"]      = fmp_p.get("city")
        info["fmp_state"]     = fmp_p.get("state")
        info["fmp_exchange"]  = fmp_p.get("exchange")
        info["fmp_ipo_date"]  = fmp_p.get("ipoDate")

    # FMP quote: additive — daily change %
    fmp_q = (fmp_quote or [{}])[0] if isinstance(fmp_quote, list) else {}
    if fmp_q:
        info["fmp_change_pct"] = fmp_q.get("changesPercentage")

    # ── Financial statements: FMP primary, yfinance fallback ──────────────────
    df_income_a = _fmp_to_income_df(fmp_income_a)
    df_income_q = _fmp_to_income_df(fmp_income_q)

    fmp_hits = []
    if df_income_a is not None: fmp_hits.append(f"income({len(fmp_income_a)}y)")
    if df_income_q is not None: fmp_hits.append(f"income({len(fmp_income_q)}q)")
    if fmp_p:                   fmp_hits.append("profile")
    if fmp_q:                   fmp_hits.append("quote")
    print(f"  FMP: {', '.join(fmp_hits) if fmp_hits else 'all fallback to yfinance'}")

    return {
        "ticker":                   ticker,
        "info":                     info,
        "price_history":            price_history,
        "sp500_history":            sp500_history,
        # Income statement: FMP primary, yfinance fallback
        "financials":               df_income_a if df_income_a is not None else financials_yf,
        "quarterly_financials":     df_income_q if df_income_q is not None else quarterly_financials_yf,
        # Cashflow + balance sheet: yfinance (no FMP endpoint specified)
        "balance_sheet":            balance_sheet,
        "quarterly_balance_sheet":  quarterly_balance_sheet,
        "cashflow":                 cashflow,
        "quarterly_cashflow":       quarterly_cashflow,
        # Raw FMP responses stored for Phase 4 (pitch deck, PDF)
        "fmp_income_annual":        fmp_income_a,
        "fmp_profile":              fmp_profile,
    }
