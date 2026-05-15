"""Fetch all inputs needed for the LBO model from FMP + yfinance."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests
import yfinance as yf

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_SOFR = 0.053  # approximate SOFR as of 2026


@dataclass
class LBOInputs:
    ticker:              str     = ""
    company_name:        str     = ""
    # Income statement
    ltm_revenue:         float   = 0.0   # $M
    ltm_ebitda:          float   = 0.0   # $M
    ltm_ebit:            float   = 0.0   # $M
    ltm_da:              float   = 0.0   # $M
    ltm_capex:           float   = 0.0   # $M
    ltm_interest_exp:    float   = 0.0   # $M
    ltm_tax_rate:        float   = 0.21
    # Balance sheet
    total_debt:          float   = 0.0   # $M
    cash:                float   = 0.0   # $M
    net_debt:            float   = 0.0   # $M
    book_equity:         float   = 0.0   # $M
    total_assets:        float   = 0.0   # $M
    accounts_receivable: float   = 0.0   # $M
    inventory:           float   = 0.0   # $M
    accounts_payable:    float   = 0.0   # $M
    ppe_net:             float   = 0.0   # $M
    # Cash flow
    ltm_nwc_change:      float   = 0.0   # $M (positive = use of cash)
    ltm_fcf:             float   = 0.0   # $M
    fcf_conversion:      float   = 0.0   # FCF / EBITDA
    capex_pct_rev:       float   = 0.0
    nwc_pct_rev:         float   = 0.0
    # Market data
    share_price:         float   = 0.0
    shares_outstanding:  float   = 0.0   # M shares
    market_cap:          float   = 0.0   # $M
    current_ev:          float   = 0.0   # $M
    current_ev_ebitda:   float   = 0.0
    ev_ebitda_1yr_low:   float   = 0.0
    ev_ebitda_1yr_high:  float   = 0.0
    beta:                float   = 1.0
    # Growth estimates
    rev_growth_y1:       float   = 0.05
    rev_growth_y2:       float   = 0.05
    sector_rev_growth:   float   = 0.04
    ltm_ebitda_margin:   float   = 0.0
    # Flags
    warnings:            list    = field(default_factory=list)


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


def fetch_lbo_inputs(ticker: str) -> LBOInputs:
    inp = LBOInputs(ticker=ticker.upper())

    # ── yfinance core data ─────────────────────────────────────────────────────
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info or {}

    inp.company_name        = info.get("shortName") or info.get("longName") or ticker
    inp.share_price         = info.get("regularMarketPrice") or info.get("currentPrice") or 0.0
    inp.shares_outstanding  = (info.get("sharesOutstanding") or 0) / 1e6  # → M shares
    inp.market_cap          = (info.get("marketCap") or 0) / 1e6          # → $M
    inp.beta                = info.get("beta") or 1.0
    inp.total_debt          = (info.get("totalDebt") or 0) / 1e6
    inp.cash                = (info.get("totalCash") or 0) / 1e6
    inp.net_debt            = inp.total_debt - inp.cash
    inp.book_equity         = (info.get("bookValue") or 0) * inp.shares_outstanding

    # ── Income statement from FMP (with yfinance fallback) ────────────────────
    is_data = _fmp(f"income-statement/{ticker}", {"limit": 4, "period": "annual"})
    if is_data and isinstance(is_data, list) and is_data:
        ltm = is_data[0]
        inp.ltm_revenue      = (ltm.get("revenue") or 0) / 1e6
        inp.ltm_ebit         = (ltm.get("operatingIncome") or 0) / 1e6
        inp.ltm_da           = (ltm.get("depreciationAndAmortization") or 0) / 1e6
        inp.ltm_ebitda       = inp.ltm_ebit + inp.ltm_da
        inp.ltm_interest_exp = abs((ltm.get("interestExpense") or 0)) / 1e6
        # Tax rate from last 2 years average
        tax_rates = []
        for row in is_data[:2]:
            ebt = row.get("incomeBeforeTax", 0) or 0
            tax = row.get("incomeTaxExpense", 0) or 0
            if ebt > 0 and tax > 0:
                tax_rates.append(tax / ebt)
        inp.ltm_tax_rate = sum(tax_rates) / len(tax_rates) if tax_rates else 0.21
    else:
        # yfinance fallback — info dict has totalRevenue and ebitda
        inp.ltm_revenue = (info.get("totalRevenue") or 0) / 1e6
        inp.ltm_ebitda  = (info.get("ebitda") or 0) / 1e6
        # Derive EBIT from operating margin if available
        op_margin = info.get("operatingMargins") or 0
        if op_margin and inp.ltm_revenue > 0:
            inp.ltm_ebit = inp.ltm_revenue * op_margin
            inp.ltm_da   = max(0, inp.ltm_ebitda - inp.ltm_ebit)
        elif inp.ltm_ebitda > 0:
            inp.ltm_da   = inp.ltm_ebitda * 0.03  # sector default 3% of revenue
            inp.ltm_ebit = inp.ltm_ebitda - inp.ltm_da
        # capex from yfinance cashflow if available
        try:
            cf_stmt = yf_ticker.cashflow
            if cf_stmt is not None and not cf_stmt.empty:
                capex_row = cf_stmt.loc[cf_stmt.index.str.contains("Capital Expenditure", case=False), :]
                if not capex_row.empty:
                    capex_val = abs(float(capex_row.iloc[0, 0])) / 1e6
                    if capex_val > 0:
                        inp.ltm_capex = capex_val
        except Exception:
            pass

    # ── Balance sheet from FMP ─────────────────────────────────────────────────
    bs_data = _fmp(f"balance-sheet-statement/{ticker}", {"limit": 2, "period": "annual"})
    if bs_data and isinstance(bs_data, list) and bs_data:
        bs = bs_data[0]
        inp.total_assets        = (bs.get("totalAssets") or 0) / 1e6
        inp.accounts_receivable = (bs.get("netReceivables") or 0) / 1e6
        inp.inventory           = (bs.get("inventory") or 0) / 1e6
        inp.accounts_payable    = (bs.get("accountPayables") or 0) / 1e6
        inp.ppe_net             = (bs.get("propertyPlantEquipmentNet") or 0) / 1e6
        if not inp.book_equity:
            inp.book_equity     = (bs.get("totalStockholdersEquity") or 0) / 1e6
        # Recalculate debt/cash from BS if more accurate
        bs_debt = (bs.get("totalDebt") or 0) / 1e6
        bs_cash = (bs.get("cashAndCashEquivalents") or 0) / 1e6
        if bs_debt > 0:
            inp.total_debt = bs_debt
        if bs_cash > 0:
            inp.cash = bs_cash
        inp.net_debt = inp.total_debt - inp.cash

    # ── Cash flow from FMP ─────────────────────────────────────────────────────
    cf_data = _fmp(f"cash-flow-statement/{ticker}", {"limit": 3, "period": "annual"})
    if cf_data and isinstance(cf_data, list) and cf_data:
        cf = cf_data[0]
        inp.ltm_capex     = abs((cf.get("capitalExpenditure") or 0)) / 1e6
        inp.ltm_nwc_change = (cf.get("changeInWorkingCapital") or 0) / 1e6 * -1  # flip sign
        # Use 3yr avg capex/rev for stability
        cap_pcts = []
        for row in cf_data:
            cap = abs(row.get("capitalExpenditure") or 0) / 1e6
            # Need revenue for the same year — approximate from IS
            if is_data and len(is_data) >= len(cf_data):
                rev = (is_data[cf_data.index(row)].get("revenue") or 1) / 1e6
            else:
                rev = inp.ltm_revenue or 1
            if rev > 0:
                cap_pcts.append(cap / rev)
        inp.capex_pct_rev = sum(cap_pcts) / len(cap_pcts) if cap_pcts else 0.03
        inp.ltm_fcf       = inp.ltm_ebitda - inp.ltm_capex - inp.ltm_nwc_change
        inp.fcf_conversion = inp.ltm_fcf / inp.ltm_ebitda if inp.ltm_ebitda > 0 else 0.6

    # ── Working capital % revenue ──────────────────────────────────────────────
    if inp.ltm_revenue > 0:
        nwc = inp.accounts_receivable + inp.inventory - inp.accounts_payable
        inp.nwc_pct_rev = nwc / inp.ltm_revenue

    # ── EV / EBITDA from FMP enterprise values ─────────────────────────────────
    ev_data = _fmp(f"enterprise-values/{ticker}", {"limit": 8, "period": "annual"})
    if ev_data and isinstance(ev_data, list) and ev_data:
        latest = ev_data[0]
        inp.current_ev = (latest.get("enterpriseValue") or 0) / 1e6
        if inp.ltm_ebitda > 0:
            inp.current_ev_ebitda = inp.current_ev / inp.ltm_ebitda
        multiples = []
        for row in ev_data[:4]:
            ev_val = (row.get("enterpriseValue") or 0) / 1e6
            ebitda_val = inp.ltm_ebitda  # use current as approx
            if ev_val > 0 and ebitda_val > 0:
                multiples.append(ev_val / ebitda_val)
        if multiples:
            inp.ev_ebitda_1yr_low  = min(multiples)
            inp.ev_ebitda_1yr_high = max(multiples)
    else:
        # Fallback: derive EV from market cap + net debt
        inp.current_ev = inp.market_cap + inp.net_debt
        if inp.ltm_ebitda > 0:
            inp.current_ev_ebitda = inp.current_ev / inp.ltm_ebitda

    # ── Revenue growth from analyst estimates (FMP) ───────────────────────────
    est_data = _fmp(f"analyst-estimates/{ticker}", {"limit": 4, "period": "annual"})
    if est_data and isinstance(est_data, list) and len(est_data) >= 2:
        rev_est = [
            (e.get("estimatedRevenueAvg") or 0) / 1e6
            for e in est_data[:2]
            if e.get("estimatedRevenueAvg")
        ]
        if len(rev_est) >= 2 and inp.ltm_revenue > 0:
            inp.rev_growth_y1 = (rev_est[0] / inp.ltm_revenue) - 1
            inp.rev_growth_y2 = (rev_est[1] / rev_est[0]) - 1 if rev_est[0] > 0 else 0.05
        elif len(rev_est) == 1 and inp.ltm_revenue > 0:
            inp.rev_growth_y1 = (rev_est[0] / inp.ltm_revenue) - 1
    # Clamp growth rates to reasonable range
    inp.rev_growth_y1 = max(-0.10, min(0.30, inp.rev_growth_y1))
    inp.rev_growth_y2 = max(-0.10, min(0.25, inp.rev_growth_y2))

    # ── Derived metrics ────────────────────────────────────────────────────────
    if inp.ltm_revenue > 0:
        inp.ltm_ebitda_margin = inp.ltm_ebitda / inp.ltm_revenue

    # ── Warnings ──────────────────────────────────────────────────────────────
    if inp.current_ev_ebitda > 15:
        inp.warnings.append(
            f"EXPENSIVE: {ticker} trades at {inp.current_ev_ebitda:.1f}x EV/EBITDA — "
            f"LBO debt serviceability threshold is typically 6-8x EBITDA. "
            f"Expect sub-15% IRR or negative returns at current valuation."
        )
    if inp.current_ev_ebitda > 20:
        inp.warnings.append(
            f"LBO NOT VIABLE: At {inp.current_ev_ebitda:.1f}x, annual interest burden "
            f"likely exceeds EBITDA. Entry multiple must be <10x for debt serviceability."
        )
    if inp.ltm_ebitda <= 0:
        inp.warnings.append(f"NEGATIVE EBITDA: LBO requires positive EBITDA. Model will use sector defaults.")
        inp.ltm_ebitda = inp.ltm_revenue * 0.15

    # TLB rate: SOFR + 300bps, capped at 8.5%
    inp._tlb_rate = min(0.085, _SOFR + 0.030)

    return inp
