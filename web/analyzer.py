from __future__ import annotations

import math

import pandas as pd


def _safe(val, digits: int = 2):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, digits)
    except (TypeError, ValueError):
        return None


def compute_stats(data: dict) -> dict:
    info = data["info"]
    prices = data["price_history"]["Close"]
    sp500 = data["sp500_history"]["Close"]

    stock_return = _safe((prices.iloc[-1] / prices.iloc[0] - 1) * 100)
    sp500_return = _safe((sp500.iloc[-1] / sp500.iloc[0] - 1) * 100)

    daily_returns = prices.pct_change().dropna()
    volatility = _safe(daily_returns.std() * (252 ** 0.5) * 100)

    current_price = _safe(info.get("currentPrice") or prices.iloc[-1])
    high_52w = _safe(info.get("fiftyTwoWeekHigh"))
    low_52w = _safe(info.get("fiftyTwoWeekLow"))

    fcf_raw   = info.get("freeCashflow")
    mktcap    = info.get("marketCap")
    fcf_yield = _safe(fcf_raw / mktcap * 100) if fcf_raw and mktcap and mktcap > 0 else None

    pct_from_high = _safe((current_price / high_52w - 1) * 100) if current_price and high_52w else None
    pct_from_low = _safe((current_price / low_52w - 1) * 100) if current_price and low_52w else None

    revenue_growth = None
    fin = data.get("financials")
    if fin is not None and not fin.empty:
        try:
            rev = fin.loc["Total Revenue"].sort_index(ascending=False)
            if len(rev) >= 2 and rev.iloc[1] and rev.iloc[1] != 0:
                revenue_growth = _safe((rev.iloc[0] / rev.iloc[1] - 1) * 100)
        except (KeyError, IndexError):
            pass

    return {
        "ticker": data["ticker"],
        "info": info,
        "current_price": current_price,
        "stock_return_6mo": stock_return,
        "sp500_return_6mo": sp500_return,
        "relative_return": _safe((stock_return or 0) - (sp500_return or 0)),
        "volatility_annualized": volatility,
        "pct_from_52w_high": pct_from_high,
        "pct_from_52w_low": pct_from_low,
        "revenue_growth_yoy": revenue_growth,
        "fcf_yield": fcf_yield,
    }


# ── Financial statements ──────────────────────────────────────────────────────

def _to_m(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f / 1e6, 1)
    except (TypeError, ValueError):
        return None


def _pct_of(num, denom, digits: int = 1) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    try:
        return round(num / denom * 100, digits)
    except (TypeError, ZeroDivisionError):
        return None


def _yoy_growth(a, b, digits: int = 1) -> float | None:
    if a is None or b is None or b == 0:
        return None
    try:
        return round((a / b - 1) * 100, digits)
    except (TypeError, ZeroDivisionError):
        return None


def _period_label(col) -> str:
    try:
        ts = pd.Timestamp(col)
        return ts.strftime("%b '%y")
    except Exception:
        return str(col)[:7]


def _row(df, *keys):
    if df is None or df.empty:
        return None
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _extract(series, n: int) -> list:
    if series is None:
        return [None] * n
    return [_to_m(series.iloc[i]) if i < len(series) else None for i in range(n)]


def _process_income(df, n: int = 4) -> dict | None:
    if df is None or df.empty:
        return None
    n = min(n, len(df.columns))
    dates = [_period_label(c) for c in df.columns[:n]]

    rev = _extract(_row(df, "Total Revenue"), n)
    gp  = _extract(_row(df, "Gross Profit"), n)
    oi  = _extract(_row(df, "Operating Income", "EBIT", "Total Operating Income As Reported"), n)
    ni  = _extract(_row(df, "Net Income", "Net Income Common Stockholders"), n)

    return {
        "dates": dates,
        "revenue": rev,
        "gross_profit": gp,
        "operating_income": oi,
        "net_income": ni,
        "gross_margin":     [_pct_of(gp[i], rev[i]) for i in range(n)],
        "operating_margin": [_pct_of(oi[i], rev[i]) for i in range(n)],
        "net_margin":       [_pct_of(ni[i], rev[i]) for i in range(n)],
    }


def _process_cashflow(df, inc: dict | None, n: int = 4) -> dict | None:
    if df is None or df.empty:
        return None
    n = min(n, len(df.columns))
    dates = [_period_label(c) for c in df.columns[:n]]

    ocf   = _extract(_row(df, "Operating Cash Flow", "Cash Flow From Operations"), n)
    capex = _extract(_row(df, "Capital Expenditure", "Capital Expenditures"), n)
    fcf_r = _extract(_row(df, "Free Cash Flow"), n)

    fcf = []
    for j in range(n):
        if fcf_r[j] is not None:
            fcf.append(fcf_r[j])
        elif ocf[j] is not None and capex[j] is not None:
            fcf.append(round(ocf[j] + capex[j], 1))   # capex is negative in yfinance
        else:
            fcf.append(None)

    rev = (inc["revenue"] if inc else []) + [None] * n
    fcf_margin = [_pct_of(fcf[j], rev[j]) for j in range(n)]

    return {
        "dates": dates,
        "operating_cash_flow": ocf,
        "capital_expenditure": capex,
        "free_cash_flow": fcf,
        "fcf_margin": fcf_margin,
    }


def compute_financials(data: dict) -> dict:
    q_inc = _process_income(data.get("quarterly_financials"), 4)
    a_inc = _process_income(data.get("financials"), 4)

    # Annual YoY growth rates (most recent vs prior year)
    yoy_rev = _yoy_growth(
        a_inc["revenue"][0] if a_inc else None,
        a_inc["revenue"][1] if a_inc and len(a_inc["revenue"]) > 1 else None,
    )
    yoy_ni = _yoy_growth(
        a_inc["net_income"][0] if a_inc else None,
        a_inc["net_income"][1] if a_inc and len(a_inc["net_income"]) > 1 else None,
    )

    # Add YoY rows to annual income (current vs prior — shift by 1)
    if a_inc and len(a_inc["dates"]) >= 2:
        n = len(a_inc["dates"])
        a_inc["yoy_revenue"] = [
            _yoy_growth(a_inc["revenue"][i], a_inc["revenue"][i + 1])
            if i + 1 < n else None
            for i in range(n)
        ]
        a_inc["yoy_ni"] = [
            _yoy_growth(a_inc["net_income"][i], a_inc["net_income"][i + 1])
            if i + 1 < n else None
            for i in range(n)
        ]

    q_cf = _process_cashflow(data.get("quarterly_cashflow"), q_inc)
    a_cf = _process_cashflow(data.get("cashflow"), a_inc)

    # Annual FCF YoY
    yoy_fcf = _yoy_growth(
        a_cf["free_cash_flow"][0] if a_cf else None,
        a_cf["free_cash_flow"][1] if a_cf and len(a_cf["free_cash_flow"]) > 1 else None,
    )
    if a_cf and len(a_cf["dates"]) >= 2:
        n = len(a_cf["dates"])
        a_cf["yoy_fcf"] = [
            _yoy_growth(a_cf["free_cash_flow"][i], a_cf["free_cash_flow"][i + 1])
            if i + 1 < n else None
            for i in range(n)
        ]

    # Balance sheet — use most recent quarterly, fallback to annual
    bs_df = data.get("quarterly_balance_sheet")
    if bs_df is None or bs_df.empty:
        bs_df = data.get("balance_sheet")

    bs: dict | None = None
    if bs_df is not None and not bs_df.empty:
        col = bs_df.columns[0]

        def _get(*keys):
            for k in keys:
                if k in bs_df.index:
                    v = bs_df.loc[k, col]
                    return _to_m(v)
            return None

        total_assets = _get("Total Assets")
        total_liab   = _get("Total Liabilities Net Minority Interest", "Total Liabilities")
        equity       = _get("Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity")
        cash         = _get("Cash And Cash Equivalents",
                            "Cash Cash Equivalents And Short Term Investments",
                            "Cash And Short Term Investments")
        total_debt   = _get("Total Debt", "Long Term Debt")
        curr_assets  = _get("Current Assets")
        curr_liab    = _get("Current Liabilities")

        bs = {
            "date": _period_label(col),
            "total_assets": total_assets,
            "total_liabilities": total_liab,
            "shareholders_equity": equity,
            "cash": cash,
            "total_debt": total_debt,
            "net_debt": round(total_debt - cash, 1) if total_debt and cash else None,
            "current_ratio": round(curr_assets / curr_liab, 2) if curr_assets and curr_liab else None,
            "debt_to_equity": round(total_debt / equity, 2) if total_debt and equity and equity != 0 else None,
        }

    if q_inc is None and a_inc is None:
        import sys
        print(f"Warning: No financial statement data available for this ticker.", file=sys.stderr)

    return {
        "income_statement": {"quarterly": q_inc, "annual": a_inc,
                             "yoy_revenue": yoy_rev, "yoy_earnings": yoy_ni},
        "balance_sheet": bs,
        "cash_flow": {"quarterly": q_cf, "annual": a_cf, "yoy_fcf": yoy_fcf},
    }
