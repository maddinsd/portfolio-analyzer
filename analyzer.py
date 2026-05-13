from __future__ import annotations

import math
import pandas as pd

from fetcher import TickerData


def _round(value, digits: int = 4):
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _daily_returns(history: pd.DataFrame) -> pd.Series:
    return history["Close"].pct_change().dropna()


def analyze(data: list[TickerData]) -> dict:
    n = len(data)
    weight = 1.0 / n

    returns_frame = pd.DataFrame(
        {d.ticker: _daily_returns(d.history) for d in data}
    ).dropna(how="any")

    holdings = []
    for d in data:
        closes = d.history["Close"]
        six_mo_return = (closes.iloc[-1] / closes.iloc[0]) - 1.0
        daily_vol = _daily_returns(d.history).std()
        info = d.info
        holdings.append(
            {
                "ticker": d.ticker,
                "weight": _round(weight, 4),
                "sector": info.get("sector"),
                "current_price": _round(info.get("currentPrice"), 2),
                "market_cap": info.get("marketCap"),
                "trailing_pe": _round(info.get("trailingPE"), 2),
                "fifty_two_week_high": _round(info.get("fiftyTwoWeekHigh"), 2),
                "fifty_two_week_low": _round(info.get("fiftyTwoWeekLow"), 2),
                "six_mo_return_pct": _round(six_mo_return * 100, 2),
                "daily_volatility_pct": _round(daily_vol * 100, 3),
            }
        )

    correlation = returns_frame.corr(method="pearson")
    corr_dict = {
        row: {col: _round(correlation.loc[row, col], 3) for col in correlation.columns}
        for row in correlation.index
    }

    portfolio_return = sum(h["six_mo_return_pct"] for h in holdings) / n
    avg_daily_vol = sum(h["daily_volatility_pct"] for h in holdings) / n

    sector_weights: dict[str, float] = {}
    for h in holdings:
        sector = h["sector"] or "Unknown"
        sector_weights[sector] = sector_weights.get(sector, 0.0) + h["weight"]
    sector_weights = {k: _round(v, 4) for k, v in sector_weights.items()}

    return {
        "holdings": holdings,
        "correlation": corr_dict,
        "portfolio": {
            "tickers": [d.ticker for d in data],
            "equal_weight": _round(weight, 4),
            "avg_six_mo_return_pct": _round(portfolio_return, 2),
            "avg_daily_volatility_pct": _round(avg_daily_vol, 3),
            "sector_weights": sector_weights,
        },
    }
