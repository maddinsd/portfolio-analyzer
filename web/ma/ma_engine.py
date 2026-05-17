"""M&A engine — transaction structure, pro forma IS, EPS accretion/dilution,
synergy analysis, and sensitivity tables.

All monetary values in $M unless noted. EPS in $ per share.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ma.ma_fetcher import MACompanyData


# ── Transaction Structure ─────────────────────────────────────────────────────

def build_transaction(acq: MACompanyData, tgt: MACompanyData,
                      offer_premium_pct: float = 30.0,
                      cash_pct: float = 50.0,
                      synergies_override_m: float | None = None) -> dict:
    """
    Build Sources & Uses, consideration mix, and goodwill.
    offer_premium_pct: e.g. 30.0 for 30%
    cash_pct: 0–100, percent of equity consideration paid in cash
    """
    # ── Offer terms ────────────────────────────────────────────────────────────
    tgt_price = tgt.lbo.share_price
    offer_price = tgt_price * (1 + offer_premium_pct / 100)
    tgt_shares  = tgt.diluted_shares                          # M shares

    total_equity_value = offer_price * tgt_shares             # $M
    net_debt_assumed   = tgt.lbo.net_debt                     # $M (can be negative = net cash)
    total_ev           = total_equity_value + net_debt_assumed # $M

    implied_ev_ebitda = total_ev / tgt.lbo.ltm_ebitda if tgt.lbo.ltm_ebitda > 0 else 0
    implied_ev_rev    = total_ev / tgt.lbo.ltm_revenue if tgt.lbo.ltm_revenue > 0 else 0
    implied_pe        = offer_price / tgt.diluted_eps if tgt.diluted_eps > 0 else 0

    # ── Consideration mix ──────────────────────────────────────────────────────
    stock_pct          = 100.0 - cash_pct
    cash_consideration = total_equity_value * cash_pct / 100   # $M
    stock_consideration= total_equity_value * stock_pct / 100  # $M

    acq_price          = acq.lbo.share_price
    # New MSFT shares issued = stock_consideration / acquirer share price
    new_shares_issued  = stock_consideration / acq_price if acq_price > 0 else 0  # M shares
    exchange_ratio     = offer_price / acq_price if acq_price > 0 else 0  # acq shares per tgt share

    pro_forma_shares   = acq.diluted_shares + new_shares_issued  # M shares

    # ── Financing ─────────────────────────────────────────────────────────────
    # Use up to 75% of acquirer cash for cash consideration; rest is new debt
    acq_cash_available  = acq.lbo.cash * 0.75                   # $M
    cash_from_balance   = min(cash_consideration, acq_cash_available)
    new_debt_issued     = max(0.0, cash_consideration - cash_from_balance)

    # Foregone interest income on cash used (after-tax) at 4.5% money market rate
    foregone_interest_rate = 0.045
    tax_rate = acq.lbo.ltm_tax_rate or 0.21
    foregone_int_aftertax  = cash_from_balance * foregone_interest_rate * (1 - tax_rate)

    # New debt interest (after-tax)
    new_debt_rate = 0.065 if acq.credit_rating_proxy == "Investment Grade" else 0.085
    new_debt_int_aftertax = new_debt_issued * new_debt_rate * (1 - tax_rate)

    # ── Goodwill & PPA ────────────────────────────────────────────────────────
    # Goodwill = purchase equity value − target book equity
    # Acquired intangibles = 30% of purchase premium over book (rough PPA allocation)
    purchase_premium_over_book = max(0.0, total_equity_value - max(0.0, tgt.book_equity))
    intangibles_acquired       = purchase_premium_over_book * 0.30   # $M
    goodwill                   = purchase_premium_over_book - intangibles_acquired
    # Intangibles amortization: straight-line over 10 years, GAAP (after-tax)
    intang_amort_annual        = intangibles_acquired / 10.0           # $M pretax
    intang_amort_aftertax      = intang_amort_annual * (1 - tax_rate)  # $M after-tax

    # ── Transaction fees ─────────────────────────────────────────────────────
    transaction_fees = total_equity_value * 0.005  # 50bps banking + legal

    # ── 52-week premium ───────────────────────────────────────────────────────
    implied_premium_52wk_high = (
        (offer_price / tgt.week52_high - 1) * 100
        if tgt.week52_high > 0 else 0
    )

    return {
        # Offer
        "offer_premium_pct":         offer_premium_pct,
        "tgt_share_price":           tgt_price,
        "offer_price":               offer_price,
        "tgt_diluted_shares":        tgt_shares,
        "total_equity_value":        total_equity_value,
        "net_debt_assumed":          net_debt_assumed,
        "total_ev":                  total_ev,
        "implied_ev_ebitda":         implied_ev_ebitda,
        "implied_ev_rev":            implied_ev_rev,
        "implied_pe":                implied_pe,
        "implied_premium_52wk_high": implied_premium_52wk_high,
        # Consideration
        "cash_pct":                  cash_pct,
        "stock_pct":                 stock_pct,
        "cash_consideration":        cash_consideration,
        "stock_consideration":       stock_consideration,
        "new_shares_issued":         new_shares_issued,
        "exchange_ratio":            exchange_ratio,
        "acq_price":                 acq_price,
        "acq_standalone_shares":     acq.diluted_shares,
        "pro_forma_shares":          pro_forma_shares,
        # Financing
        "cash_from_balance":         cash_from_balance,
        "new_debt_issued":           new_debt_issued,
        "new_debt_rate":             new_debt_rate,
        "foregone_int_aftertax":     foregone_int_aftertax,
        "new_debt_int_aftertax":     new_debt_int_aftertax,
        "tax_rate":                  tax_rate,
        # PPA
        "purchase_premium_over_book": purchase_premium_over_book,
        "intangibles_acquired":       intangibles_acquired,
        "goodwill":                   goodwill,
        "intang_amort_annual":        intang_amort_annual,
        "intang_amort_aftertax":      intang_amort_aftertax,
        "transaction_fees":           transaction_fees,
    }


# ── Synergy Analysis ──────────────────────────────────────────────────────────

def build_synergies(acq: MACompanyData, tgt: MACompanyData,
                    tx: dict, synergies_override_m: float | None = None) -> dict:
    """
    Build 3-year synergy ramp: 50% / 75% / 100% of run-rate.
    If synergies_override_m provided, skip bottom-up and use that total.
    After-tax synergies are what flow into pro forma net income.
    """
    tax_rate = tx["tax_rate"]

    if synergies_override_m is not None:
        total_pretax = synergies_override_m  # user-supplied $M
        cost_syn   = total_pretax * 0.70    # 70% cost, 30% revenue (typical split)
        rev_syn_pretax = total_pretax * 0.30
        rev_syn_aftertax = rev_syn_pretax * (1 - tax_rate)
        cost_syn_aftertax = cost_syn * (1 - tax_rate)
    else:
        # Bottom-up cost synergies
        combined_sgna   = (acq.lbo.ltm_revenue * 0.15 + tgt.lbo.ltm_revenue * 0.15)  # rough SG&A
        combined_rev    = acq.lbo.ltm_revenue + tgt.lbo.ltm_revenue
        combined_cogs   = combined_rev * 0.60  # rough COGS

        headcount_syn   = combined_sgna  * 0.05   # 5% of combined SG&A
        procurement_syn = combined_cogs  * 0.02   # 2% of combined COGS
        facilities_syn  = combined_rev   * 0.01   # 1% of combined revenue
        cost_syn        = headcount_syn + procurement_syn + facilities_syn
        cost_syn_aftertax = cost_syn * (1 - tax_rate)

        # Revenue synergies (conservative: 3% of target revenue × gross margin)
        tgt_gross_margin = (
            (tgt.lbo.ltm_ebitda + tgt.lbo.ltm_capex) / tgt.lbo.ltm_revenue
            if tgt.lbo.ltm_revenue > 0 else 0.40
        )
        rev_syn_pretax   = tgt.lbo.ltm_revenue * 0.03
        rev_syn_aftertax = rev_syn_pretax * max(0.25, tgt_gross_margin) * (1 - tax_rate)

        total_pretax = cost_syn + rev_syn_pretax

    total_aftertax  = cost_syn_aftertax + rev_syn_aftertax

    # 3-year ramp: 50% / 75% / 100%
    ramp = [0.50, 0.75, 1.00]
    syn_aftertax_yr = [total_aftertax * r for r in ramp]

    # Synergy NPV: perpetuity from year 3+, discounted at 8%
    discount = 0.08
    # Years 1-3 PV
    pv_ramp = sum(syn_aftertax_yr[i] / (1 + discount) ** (i + 1) for i in range(3))
    # Terminal value at end of year 3 (perpetuity)
    tv = total_aftertax / discount / (1 + discount) ** 3
    synergy_npv = pv_ramp + tv

    return {
        "total_pretax_runrate":   total_pretax,
        "cost_syn_pretax":        cost_syn,
        "rev_syn_pretax":         rev_syn_pretax if synergies_override_m is None else total_pretax * 0.30,
        "total_aftertax_runrate": total_aftertax,
        "cost_syn_aftertax":      cost_syn_aftertax,
        "rev_syn_aftertax":       rev_syn_aftertax,
        "syn_aftertax_y1":        syn_aftertax_yr[0],
        "syn_aftertax_y2":        syn_aftertax_yr[1],
        "syn_aftertax_y3":        syn_aftertax_yr[2],
        "ramp_pcts":              ramp,
        "synergy_npv":            synergy_npv,
    }


# ── Pro Forma Income Statement ────────────────────────────────────────────────

def build_pro_forma(acq: MACompanyData, tgt: MACompanyData,
                    tx: dict, syn: dict) -> dict:
    """
    3-year pro forma net income and EPS vs. standalone.
    Year 1: 50% synergies; Year 2: 75%; Year 3: 100%.
    """
    # Standalone acquirer EPS / net income
    acq_ni    = acq.net_income       # $M
    acq_eps   = acq.diluted_eps      # $/share
    acq_shares= acq.diluted_shares   # M shares

    tgt_ni    = tgt.net_income       # $M

    # Assume modest organic growth: 7% for acquirer, 6% for target per year
    acq_growth = 0.07
    tgt_growth = 0.06

    results = []
    for yr in range(1, 4):
        # Standalone NI projections (simple linear)
        acq_ni_yr  = acq_ni  * (1 + acq_growth) ** yr
        tgt_ni_yr  = tgt_ni  * (1 + tgt_growth)  ** yr
        acq_eps_yr = acq_ni_yr / acq_shares  # standalone EPS doesn't dilute

        # Pro forma adjustments
        foregone_int    = tx["foregone_int_aftertax"]   # cash yield lost
        new_debt_int    = tx["new_debt_int_aftertax"]   # new interest burden
        intang_amort    = tx["intang_amort_aftertax"]   # GAAP non-cash amort
        syn_yr          = [syn["syn_aftertax_y1"], syn["syn_aftertax_y2"], syn["syn_aftertax_y3"]][yr - 1]
        pf_shares       = tx["pro_forma_shares"]

        # GAAP pro forma net income
        pf_ni_gaap  = acq_ni_yr + tgt_ni_yr + syn_yr - foregone_int - new_debt_int - intang_amort
        pf_eps_gaap = pf_ni_gaap / pf_shares

        # Cash EPS (add back non-cash intangibles amortization)
        pf_ni_cash  = pf_ni_gaap + tx["intang_amort_aftertax"]
        pf_eps_cash = pf_ni_cash / pf_shares

        # Standalone EPS (acquirer, no deal)
        acq_eps_sa  = acq_eps_yr  # standalone EPS with organic growth

        # Accretion / dilution
        gaap_accretion_pct = (pf_eps_gaap / acq_eps_sa - 1) * 100 if acq_eps_sa != 0 else 0
        cash_accretion_pct = (pf_eps_cash / acq_eps_sa - 1) * 100 if acq_eps_sa != 0 else 0
        gaap_accretion_dol = pf_eps_gaap - acq_eps_sa
        cash_accretion_dol = pf_eps_cash - acq_eps_sa

        results.append({
            "year":               yr,
            "acq_ni_standalone":  acq_ni_yr,
            "tgt_ni_standalone":  tgt_ni_yr,
            "syn_aftertax":       syn_yr,
            "foregone_int":       foregone_int,
            "new_debt_int":       new_debt_int,
            "intang_amort_aftertax": intang_amort,
            "pf_ni_gaap":         pf_ni_gaap,
            "pf_ni_cash":         pf_ni_cash,
            "pf_shares":          pf_shares,
            "pf_eps_gaap":        pf_eps_gaap,
            "pf_eps_cash":        pf_eps_cash,
            "acq_eps_standalone": acq_eps_sa,
            "gaap_accretion_pct": gaap_accretion_pct,
            "cash_accretion_pct": cash_accretion_pct,
            "gaap_accretion_dol": gaap_accretion_dol,
            "cash_accretion_dol": cash_accretion_dol,
        })

    return {"years": results}


# ── Break-Even Analysis ───────────────────────────────────────────────────────

def _pf_eps_at_premium(acq: MACompanyData, tgt: MACompanyData,
                       premium_pct: float, cash_pct: float,
                       syn_aftertax_y1: float) -> tuple[float, float]:
    """Return (gaap_eps_y1, standalone_eps_y1) for given premium/mix/synergies."""
    tx_s = build_transaction(acq, tgt, offer_premium_pct=premium_pct, cash_pct=cash_pct)
    acq_ni_y1  = acq.net_income * 1.07
    tgt_ni_y1  = tgt.net_income * 1.06
    pf_ni_gaap = (acq_ni_y1 + tgt_ni_y1 + syn_aftertax_y1
                  - tx_s["foregone_int_aftertax"]
                  - tx_s["new_debt_int_aftertax"]
                  - tx_s["intang_amort_aftertax"])
    pf_eps     = pf_ni_gaap / tx_s["pro_forma_shares"] if tx_s["pro_forma_shares"] > 0 else 0
    sa_eps     = acq_ni_y1 / acq.diluted_shares if acq.diluted_shares > 0 else 0
    return pf_eps, sa_eps


def compute_breakeven(acq: MACompanyData, tgt: MACompanyData,
                      cash_pct: float, syn_aftertax_y1: float) -> float:
    """
    Binary search for the offer premium (%) where GAAP pro forma EPS = standalone EPS.
    Returns the breakeven premium %. Returns NaN if never breakeven in 0-200% range.
    """
    lo, hi = 0.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        pf_eps, sa_eps = _pf_eps_at_premium(acq, tgt, mid, cash_pct, syn_aftertax_y1)
        diff = pf_eps - sa_eps
        if diff > 0:
            lo = mid  # accretive at mid — can pay more
        else:
            hi = mid  # dilutive — need lower premium
        if hi - lo < 0.01:
            break
    be = (lo + hi) / 2
    # Validate: if even at 0% premium it's dilutive, return 0
    pf0, sa0 = _pf_eps_at_premium(acq, tgt, 0.0, cash_pct, syn_aftertax_y1)
    if pf0 < sa0:
        return float("nan")  # dilutive at all premiums with these synergies
    return be


# ── Sensitivity Tables ────────────────────────────────────────────────────────

def build_sensitivity(acq: MACompanyData, tgt: MACompanyData,
                      tx: dict, syn: dict, pf: dict) -> dict:
    """
    Table 1 (5×5): Accretion/dilution % vs premium rows × synergy % of base cols
    Table 2 (5×5): Accretion/dilution % vs premium rows × cash % cols
    Table 3 (3×3): Implied multiples vs premium

    Center cell of Table 1 = base case.
    """
    base_premium = tx["offer_premium_pct"]
    base_syn     = syn["total_aftertax_runrate"]
    base_cash    = tx["cash_pct"]
    tax_rate     = tx["tax_rate"]

    premiums      = [base_premium - 20, base_premium - 10, base_premium,
                     base_premium + 10, base_premium + 20]
    premiums      = [max(5.0, p) for p in premiums]
    # Synergy axis: 0%, 50%, 100% (base), 150%, 200% — center = base case
    syn_pcts      = [0.0, 0.50, 1.00, 1.50, 2.00]
    cash_pcts     = [0.0, 25.0, 50.0, 75.0, 100.0]

    def _acq_pct(prem, syn_at, cp):
        tx_s  = build_transaction(acq, tgt, offer_premium_pct=prem, cash_pct=cp)
        syn_y1 = syn_at * 0.50
        acq_ni = acq.net_income * 1.07
        tgt_ni = tgt.net_income * 1.06
        pf_ni  = (acq_ni + tgt_ni + syn_y1
                  - tx_s["foregone_int_aftertax"]
                  - tx_s["new_debt_int_aftertax"]
                  - tx_s["intang_amort_aftertax"])
        pf_eps = pf_ni / tx_s["pro_forma_shares"] if tx_s["pro_forma_shares"] > 0 else 0
        sa_eps = acq_ni / acq.diluted_shares if acq.diluted_shares > 0 else 0
        return (pf_eps / sa_eps - 1) * 100 if sa_eps != 0 else 0

    # Table 1: premium × synergy fraction
    table1 = []
    for p in premiums:
        row = []
        for sp in syn_pcts:
            row.append(_acq_pct(p, base_syn * sp, base_cash))
        table1.append(row)

    # Table 2: premium × cash pct
    table2 = []
    for p in premiums:
        row = []
        for cp in cash_pcts:
            row.append(_acq_pct(p, base_syn, cp))
        table2.append(row)

    # Table 3: implied multiples vs premium
    mult_premiums = [base_premium - 10, base_premium, base_premium + 10]
    table3 = []
    for p in mult_premiums:
        op    = tgt.lbo.share_price * (1 + p / 100)
        ev_   = op * tgt.diluted_shares + tgt.lbo.net_debt
        table3.append({
            "premium_pct": p,
            "offer_price": op,
            "ev_ebitda":   ev_ / tgt.lbo.ltm_ebitda if tgt.lbo.ltm_ebitda > 0 else 0,
            "ev_revenue":  ev_ / tgt.lbo.ltm_revenue if tgt.lbo.ltm_revenue > 0 else 0,
            "pe":          op / tgt.diluted_eps if tgt.diluted_eps > 0 else 0,
        })

    return {
        "premiums":    premiums,
        "syn_pcts":    syn_pcts,
        "cash_pcts":   cash_pcts,
        "table1":      table1,   # [row_prem][col_syn]
        "table2":      table2,   # [row_prem][col_cash]
        "table3":      table3,   # list of dicts
    }
