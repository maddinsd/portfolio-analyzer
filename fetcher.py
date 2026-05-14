from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

import yfinance as yf

INFO_FIELDS = [
    "currentPrice", "previousClose", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
    "twoHundredDayAverage", "sector", "industry", "longBusinessSummary",
    "shortName", "longName",
    "totalRevenue", "grossMargins", "operatingMargins", "profitMargins",
    "totalDebt", "freeCashflow", "dividendYield", "trailingEps", "forwardEps",
    "recommendationMean", "targetMeanPrice", "numberOfAnalystOpinions",
]


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

    sp500_history = yf.Ticker("^GSPC").history(period="6mo", interval="1d", auto_adjust=True)

    return {
        "ticker": ticker,
        "info": {field: raw_info.get(field) for field in INFO_FIELDS},
        "price_history": price_history,
        "sp500_history": sp500_history,
        "financials": t.financials,
        "quarterly_financials": t.quarterly_financials,
        "balance_sheet": t.balance_sheet,
        "quarterly_balance_sheet": t.quarterly_balance_sheet,
        "cashflow": t.cashflow,
        "quarterly_cashflow": t.quarterly_cashflow,
    }
