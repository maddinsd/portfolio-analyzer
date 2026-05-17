"""LBO model computation engine — transaction structure through sensitivity tables."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from lbo.lbo_fetcher import LBOInputs


# ── Assumptions ────────────────────────────────────────────────────────────────

@dataclass
class LBOAssumptions:
    # Entry
    entry_ev_ebitda:     float = 0.0   # set from inputs if not overridden
    transaction_fees_pct: float = 0.020
    mgmt_rollover_pct:   float = 0.10  # % of equity tranche

    # Capital structure (% of Entry EV)
    tlb_pct:             float = 0.35
    senior_notes_pct:    float = 0.20
    sub_debt_pct:        float = 0.10
    # equity_pct = 1 - debt total, implied

    # Interest rates
    tlb_rate:            float = 0.083  # will be updated from fetcher
    senior_notes_rate:   float = 0.095
    sub_debt_rate:       float = 0.120
    revolver_size:       float = 0.0   # set from EV
    revolver_commit_fee: float = 0.00375

    # TLB amortization
    tlb_amort_pct:       float = 0.010  # 1% mandatory per year

    # Operating (5 years)
    hold_years:          int   = 5
    rev_growth:          list  = field(default_factory=lambda: [0.05]*5)
    ebitda_margin_y0:    float = 0.0
    ebitda_margin_exp:   float = 0.005  # +50bps/yr
    capex_pct_rev:       float = 0.03
    nwc_pct_rev:         float = 0.05
    tax_rate:            float = 0.21
    da_pct_rev:          float = 0.03

    # Exit
    exit_year:           int   = 5
    exit_ev_ebitda:      float = 0.0   # set from entry - 0.5x
    mgmt_promote_moic:   float = 2.0
    mgmt_promote_pct:    float = 0.20

    # Net return fees
    mgmt_fee_pct:        float = 0.020  # 2% annual on committed capital
    carry_pct:           float = 0.200  # 20%


def build_assumptions(inp: LBOInputs,
                      entry_multiple: float | None = None,
                      hold_years: int = 5,
                      debt_pct: float | None = None) -> LBOAssumptions:
    a = LBOAssumptions()

    a.entry_ev_ebitda = entry_multiple if entry_multiple else round(inp.current_ev_ebitda, 1)
    if a.entry_ev_ebitda <= 0:
        a.entry_ev_ebitda = 8.0

    a.exit_ev_ebitda  = max(4.0, a.entry_ev_ebitda - 0.5)
    a.hold_years      = hold_years
    a.tlb_rate        = getattr(inp, "_tlb_rate", 0.083)

    # Override total debt % if supplied (distribute proportionally)
    if debt_pct:
        ratio = debt_pct / (a.tlb_pct + a.senior_notes_pct + a.sub_debt_pct)
        a.tlb_pct         = a.tlb_pct         * ratio
        a.senior_notes_pct= a.senior_notes_pct * ratio
        a.sub_debt_pct    = a.sub_debt_pct     * ratio

    # Operating assumptions from fetched data
    a.ebitda_margin_y0 = inp.ltm_ebitda_margin
    a.capex_pct_rev    = inp.capex_pct_rev if inp.capex_pct_rev > 0 else 0.03
    a.nwc_pct_rev      = abs(inp.nwc_pct_rev) if inp.nwc_pct_rev else 0.05
    a.tax_rate         = inp.ltm_tax_rate
    a.da_pct_rev       = inp.ltm_da / inp.ltm_revenue if inp.ltm_revenue > 0 else 0.03

    # Revenue growth: Y1-Y2 from analyst estimates, Y3-Y5 at sector median
    base_growth = max(0.01, inp.sector_rev_growth)
    a.rev_growth = [
        max(0.00, inp.rev_growth_y1),
        max(0.00, inp.rev_growth_y2),
        base_growth,
        base_growth,
        base_growth,
    ]

    # Revolver = 5% of Entry EV
    a.revolver_size = inp.ltm_ebitda * a.entry_ev_ebitda * 0.05

    return a


# ── Transaction Structure ──────────────────────────────────────────────────────

def build_transaction(inp: LBOInputs, a: LBOAssumptions) -> dict:
    ev           = inp.ltm_ebitda * a.entry_ev_ebitda
    fees         = ev * a.transaction_fees_pct
    total_uses   = ev + fees

    debt_total   = ev * (a.tlb_pct + a.senior_notes_pct + a.sub_debt_pct)
    equity_total = total_uses - debt_total

    tlb_proceeds       = ev * a.tlb_pct
    senior_proceeds    = ev * a.senior_notes_pct
    sub_proceeds       = ev * a.sub_debt_pct
    mgmt_rollover      = equity_total * a.mgmt_rollover_pct
    sponsor_equity     = equity_total - mgmt_rollover

    debt_ebitda        = debt_total / inp.ltm_ebitda if inp.ltm_ebitda > 0 else 0
    blended_rate       = (
        (tlb_proceeds * a.tlb_rate +
         senior_proceeds * a.senior_notes_rate +
         sub_proceeds * a.sub_debt_rate) / debt_total
    ) if debt_total > 0 else 0
    interest_yr1       = debt_total * blended_rate
    coverage_yr1       = inp.ltm_ebitda / interest_yr1 if interest_yr1 > 0 else 999

    flags = []
    if debt_ebitda > 7:
        flags.append(f"⚠ HIGH LEVERAGE: {debt_ebitda:.1f}x Debt/EBITDA (PE comfort zone: 4-6x)")
    if coverage_yr1 < 1.5:
        flags.append(f"⚠ THIN COVERAGE: {coverage_yr1:.2f}x interest coverage (min viable: 1.5x)")
    if coverage_yr1 < 1.0:
        flags.append(f"🚨 INTEREST COVERAGE < 1x — LBO IS NOT SERVICEABLE AT THIS VALUATION")

    return {
        "entry_ev":         ev,
        "transaction_fees": fees,
        "total_uses":       total_uses,
        "tlb":              tlb_proceeds,
        "senior_notes":     senior_proceeds,
        "sub_debt":         sub_proceeds,
        "total_debt":       debt_total,
        "mgmt_rollover":    mgmt_rollover,
        "sponsor_equity":   sponsor_equity,
        "equity_total":     equity_total,
        "debt_pct":         debt_total / ev if ev > 0 else 0,
        "equity_pct":       equity_total / total_uses if total_uses > 0 else 0,
        "debt_ebitda":      debt_ebitda,
        "blended_rate":     blended_rate,
        "interest_yr1":     interest_yr1,
        "coverage_yr1":     coverage_yr1,
        "flags":            flags,
    }


# ── Debt Schedule ──────────────────────────────────────────────────────────────

def build_debt_schedule(tx: dict, a: LBOAssumptions,
                        fcf_available: list[float] | None = None) -> dict:
    """
    Returns per-year dicts with beginning/ending balances and interest for each tranche.
    fcf_available: list of FCF available for sweep, one per hold year (can be None for first pass).
    """
    years      = a.hold_years
    tlb_orig   = tx["tlb"]
    sn_orig    = tx["senior_notes"]
    sub_orig   = tx["sub_debt"]
    fcf        = fcf_available or [0.0] * years  # no sweep on first pass

    schedule = []
    tlb_bal  = tlb_orig
    sn_bal   = sn_orig
    sub_bal  = sub_orig
    rev_commit_fee = a.revolver_size * a.revolver_commit_fee  # revolver undrawn

    for yr in range(years):
        yr_fcf = fcf[yr] if yr < len(fcf) else 0.0

        # ── TLB ──────────────────────────────────────────────────────────────
        tlb_beg    = tlb_bal
        tlb_amort  = min(tlb_orig * a.tlb_amort_pct, tlb_beg)
        # Cash sweep: excess FCF after mandatory amort, applied to TLB first
        sweep_avail = max(0.0, yr_fcf - tlb_amort)
        tlb_sweep  = min(sweep_avail, max(0.0, tlb_beg - tlb_amort))
        tlb_int    = tlb_beg * a.tlb_rate   # on beginning balance (no circularity)
        tlb_end    = max(0.0, tlb_beg - tlb_amort - tlb_sweep)

        # ── Senior Notes (bullet — no amortization until Y5 or maturity) ────
        sn_beg     = sn_bal
        sn_amort   = 0.0  # bullet
        # Sweep residual after TLB paid
        sn_sweep_avail = max(0.0, sweep_avail - tlb_sweep)
        sn_sweep   = min(sn_sweep_avail, sn_beg)
        sn_int     = sn_beg * a.senior_notes_rate
        sn_end     = max(0.0, sn_beg - sn_sweep)

        # ── Sub Debt (bullet) ─────────────────────────────────────────────────
        sub_beg    = sub_bal
        sub_amort  = 0.0
        sub_sweep  = 0.0  # sub debt only paid after senior is cleared
        sub_int    = sub_beg * a.sub_debt_rate
        sub_end    = max(0.0, sub_beg)  # PIK-like, no cash paydown

        total_int  = tlb_int + sn_int + sub_int + rev_commit_fee
        total_debt_end = tlb_end + sn_end + sub_end
        total_debt_beg = tlb_beg + sn_beg + sub_beg
        total_paydown  = (tlb_amort + tlb_sweep) + sn_sweep

        schedule.append({
            "year":            yr + 1,
            # TLB
            "tlb_beg":         tlb_beg,
            "tlb_amort":       tlb_amort,
            "tlb_sweep":       tlb_sweep,
            "tlb_int":         tlb_int,
            "tlb_end":         tlb_end,
            # Senior Notes
            "sn_beg":          sn_beg,
            "sn_amort":        sn_amort,
            "sn_sweep":        sn_sweep,
            "sn_int":          sn_int,
            "sn_end":          sn_end,
            # Sub Debt
            "sub_beg":         sub_beg,
            "sub_amort":       sub_amort,
            "sub_sweep":       sub_sweep,
            "sub_int":         sub_int,
            "sub_end":         sub_end,
            # Revolver
            "rev_commit_fee":  rev_commit_fee,
            # Totals
            "total_int":       total_int,
            "total_debt_beg":  total_debt_beg,
            "total_debt_end":  total_debt_end,
            "total_paydown":   total_paydown,
        })

        tlb_bal = tlb_end
        sn_bal  = sn_end
        sub_bal = sub_end

    return {"schedule": schedule, "orig_tlb": tlb_orig, "orig_sn": sn_orig, "orig_sub": sub_orig}


# ── Three Statement Model ─────────────────────────────────────────────────────

def build_three_statements(inp: LBOInputs, a: LBOAssumptions,
                           tx: dict, debt_sched: dict) -> dict:
    """
    Build IS, CF, BS for hold_years. Iterate twice to resolve debt sweep.
    Returns: {income_stmt, cash_flow, balance_sheet} each as list of year dicts.
    """
    sched      = debt_sched["schedule"]
    ltm_da     = inp.ltm_da

    # ── First pass: IS + CF without sweep (to get FCF available) ────────────
    is_rows = []
    cf_rows = []
    bs_rows = []

    prev_rev = inp.ltm_revenue
    prev_nwc = inp.accounts_receivable + inp.inventory - inp.accounts_payable

    # Opening balance sheet (post-close)
    cash_min      = inp.ltm_revenue * 0.01   # 1% of revenue minimum operating cash
    opening_ppe   = inp.ppe_net
    opening_cash  = max(cash_min, inp.cash)  # company retains its cash; fees funded from equity check
    opening_ar_inv = inp.accounts_receivable + inp.inventory
    opening_ap    = inp.accounts_payable
    opening_equity = tx["equity_total"]      # sponsor + mgmt rollover
    opening_debt   = tx["total_debt"]
    # Goodwill as plug: makes opening BS balance exactly
    goodwill = opening_equity + opening_debt + opening_ap - opening_cash - opening_ar_inv - opening_ppe

    prev_cash     = opening_cash
    prev_ppe      = opening_ppe
    sponsor_eq    = tx["sponsor_equity"]
    mgmt_rollover = tx["mgmt_rollover"]

    fcf_for_sweep = []

    for yr_idx, ds in enumerate(sched):
        yr = yr_idx + 1

        # Revenue
        rev = prev_rev * (1 + a.rev_growth[yr_idx])

        # EBITDA margin steps up each year
        ebitda_margin = a.ebitda_margin_y0 + a.ebitda_margin_exp * yr
        ebitda        = rev * ebitda_margin

        # D&A: proportional to PP&E, floored at historical rate
        da = max(rev * a.da_pct_rev, prev_ppe * 0.10)
        da = min(da, ebitda * 0.50)  # cap at 50% EBITDA
        capex_yr = rev * a.capex_pct_rev
        da = min(da, prev_ppe + capex_yr)  # can't depreciate more than PP&E pool

        ebit     = ebitda - da
        int_exp  = ds["total_int"]
        ebt      = ebit - int_exp
        tax      = max(0.0, ebt * a.tax_rate)
        net_inc  = ebt - tax

        # Capex & WC
        capex    = capex_yr     # already computed above
        nwc_now  = rev * a.nwc_pct_rev
        nwc_chg  = nwc_now - prev_nwc   # positive = use of cash (WC increases)

        # Cash flow
        cfo       = net_inc + da - nwc_chg
        levered_fcf = cfo - capex
        # FCF available for mandatory amort + sweep
        mand_amort  = ds["tlb_amort"]
        fcf_after_amort = levered_fcf - mand_amort
        fcf_for_sweep.append(max(0.0, fcf_after_amort))

        # PP&E roll-forward
        ppe_end = max(0.0, prev_ppe + capex - da)

        # Ending cash
        # Cash = beg cash + levered FCF - mandatory amort
        cash_end = max(cash_min, prev_cash + levered_fcf - mand_amort)

        # Debt from schedule (first pass, no sweep applied yet)
        debt_end = ds["total_debt_end"]

        # Balance sheet build
        rev_scale = rev / inp.ltm_revenue if inp.ltm_revenue > 0 else 1.0
        ap        = inp.accounts_payable * rev_scale
        ar_inv    = nwc_now + ap                      # NWC + AP = AR + Inv (gross)

        total_assets = cash_end + ar_inv + ppe_end + goodwill
        total_liab   = ap + debt_end
        # Equity roll: opening equity + net income (no dividends in LBO)
        if yr_idx == 0:
            equity_prev = opening_equity
        else:
            equity_prev = bs_rows[yr_idx - 1]["total_equity"]
        equity_end   = equity_prev + net_inc
        check        = total_assets - total_liab - equity_end

        is_rows.append({
            "year": yr, "revenue": rev, "ebitda": ebitda,
            "ebitda_margin": ebitda_margin, "da": da, "ebit": ebit,
            "interest_exp": int_exp, "ebt": ebt, "tax": tax, "net_income": net_inc,
        })
        cf_rows.append({
            "year": yr, "net_income": net_inc, "da": da, "nwc_change": nwc_chg,
            "cfo": cfo, "capex": capex, "levered_fcf": levered_fcf,
            "mand_amort": mand_amort, "fcf_after_amort": max(0, fcf_after_amort),
        })
        bs_rows.append({
            "year": yr, "cash": cash_end, "ar_inventory": ar_inv,
            "ppe_net": ppe_end, "goodwill": goodwill,
            "total_assets": total_assets, "accounts_payable": ap,
            "debt": debt_end, "total_liab": total_liab,
            "total_equity": equity_end, "bs_check": check,
        })

        prev_rev  = rev
        prev_nwc  = nwc_now
        prev_cash = cash_end
        prev_ppe  = ppe_end

    # ── Second pass: rebuild debt schedule with sweep ────────────────────────
    debt_sched2 = build_debt_schedule(tx, a, fcf_for_sweep)
    sched2      = debt_sched2["schedule"]

    # Update CF and BS with actual sweep
    prev_cash = opening_cash
    prev_ppe  = opening_ppe
    prev_nwc  = inp.accounts_receivable + inp.inventory - inp.accounts_payable

    is_rows2 = []
    cf_rows2 = []
    bs_rows2 = []
    prev_rev = inp.ltm_revenue

    for yr_idx, ds in enumerate(sched2):
        yr     = yr_idx + 1
        is_r   = is_rows[yr_idx]
        cf_r   = cf_rows[yr_idx]

        rev     = is_r["revenue"]
        nwc_now = rev * a.nwc_pct_rev
        nwc_chg = nwc_now - prev_nwc
        da      = is_r["da"]
        capex   = cf_r["capex"]
        net_inc = is_r["net_income"]

        # Recompute interest with actual sweep schedule
        int_exp   = ds["total_int"]
        ebt       = is_r["ebit"] - int_exp
        tax       = max(0.0, ebt * a.tax_rate)
        net_inc2  = ebt - tax

        cfo       = net_inc2 + da - nwc_chg
        levered_fcf = cfo - capex
        total_pay = ds["total_paydown"]
        net_cf    = levered_fcf - total_pay

        raw_cash  = prev_cash + net_cf
        # If cash would fall below minimum, draw on revolver (adds to debt, keeps BS balanced)
        revolver_draw = max(0.0, cash_min - raw_cash)
        cash_end  = max(cash_min, raw_cash)
        debt_end  = ds["total_debt_end"] + revolver_draw
        ppe_end   = max(0.0, prev_ppe + capex - da)

        rev_scale = rev / inp.ltm_revenue if inp.ltm_revenue > 0 else 1.0
        ap        = inp.accounts_payable * rev_scale
        ar_inv    = nwc_now + ap                      # NWC + AP = AR + Inv (gross)
        total_assets = cash_end + ar_inv + ppe_end + goodwill
        total_liab   = ap + debt_end

        if yr_idx == 0:
            equity_prev = opening_equity
        else:
            equity_prev = bs_rows2[yr_idx - 1]["total_equity"]
        equity_end   = equity_prev + net_inc2
        check        = total_assets - total_liab - equity_end

        is_rows2.append({
            "year": yr, "revenue": rev, "ebitda": is_r["ebitda"],
            "ebitda_margin": is_r["ebitda_margin"], "da": da, "ebit": is_r["ebit"],
            "interest_exp": int_exp, "ebt": ebt, "tax": tax, "net_income": net_inc2,
        })
        cf_rows2.append({
            "year": yr, "net_income": net_inc2, "da": da, "nwc_change": nwc_chg,
            "cfo": cfo, "capex": capex, "levered_fcf": levered_fcf,
            "total_paydown": total_pay, "net_cf": net_cf,
        })
        bs_rows2.append({
            "year": yr, "cash": cash_end, "ar_inventory": ar_inv,
            "ppe_net": ppe_end, "goodwill": goodwill,
            "total_assets": total_assets, "accounts_payable": ap,
            "debt": debt_end, "total_liab": total_liab,
            "total_equity": equity_end, "bs_check": check,
        })

        prev_rev  = rev
        prev_nwc  = nwc_now
        prev_cash = cash_end
        prev_ppe  = ppe_end

    return {
        "income_stmt":  is_rows2,
        "cash_flow":    cf_rows2,
        "balance_sheet": bs_rows2,
        "debt_sched2":  debt_sched2,
    }


# ── Returns Analysis ───────────────────────────────────────────────────────────

def _irr(cashflows: list[float]) -> float:
    """Newton-Raphson IRR. Returns NaN if no solution."""
    if not cashflows or cashflows[0] >= 0:
        return float("nan")
    # Guess 20%
    r = 0.20
    for _ in range(100):
        npv  = sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))
        dnpv = sum(-t * cf / (1 + r) ** (t + 1) for t, cf in enumerate(cashflows))
        if abs(dnpv) < 1e-12:
            break
        r_new = r - npv / dnpv
        if abs(r_new - r) < 1e-8:
            r = r_new
            break
        r = r_new
        r = max(-0.999, min(10.0, r))
    # Validate
    check = sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))
    if abs(check) > 1e4:
        return float("nan")
    return r


def build_returns(inp: LBOInputs, a: LBOAssumptions,
                  tx: dict, stmts: dict) -> dict:
    is_rows = stmts["income_stmt"]
    ds2     = stmts["debt_sched2"]["schedule"]
    bs_rows = stmts["balance_sheet"]

    # Exit at hold_years
    exit_yr    = min(a.exit_year, a.hold_years) - 1  # 0-indexed
    exit_ebitda = is_rows[exit_yr]["ebitda"]
    exit_ev     = exit_ebitda * a.exit_ev_ebitda
    exit_debt   = ds2[exit_yr]["total_debt_end"]
    exit_equity_total = max(0.0, exit_ev - exit_debt)

    # Management promote
    entry_equity = tx["equity_total"]
    exit_moic_pre_promote = exit_equity_total / entry_equity if entry_equity > 0 else 0

    promote = 0.0
    if exit_moic_pre_promote > a.mgmt_promote_moic:
        # Promote applies to upside above 2x
        upside_equity   = exit_equity_total - entry_equity * a.mgmt_promote_moic
        promote         = upside_equity * a.mgmt_promote_pct * (tx["mgmt_rollover"] / tx["equity_total"])

    sponsor_proceeds  = exit_equity_total * (tx["sponsor_equity"] / tx["equity_total"]) - promote
    mgmt_proceeds     = exit_equity_total * (tx["mgmt_rollover"] / tx["equity_total"]) + promote

    sponsor_invested  = tx["sponsor_equity"]
    gross_moic        = sponsor_proceeds / sponsor_invested if sponsor_invested > 0 else 0
    gross_irr_cfs     = [-sponsor_invested] + [0.0] * (a.hold_years - 1) + [sponsor_proceeds]
    # Insert at correct position
    gross_irr_cfs     = [-sponsor_invested] + [0.0] * (a.exit_year - 1) + [sponsor_proceeds]
    gross_irr         = _irr(gross_irr_cfs)

    # Net returns: apply 2% mgmt fee on invested capital + 20% carry
    total_fees        = sponsor_invested * a.mgmt_fee_pct * a.exit_year
    carry_base        = max(0.0, sponsor_proceeds - sponsor_invested - total_fees)
    carry             = carry_base * a.carry_pct
    net_proceeds      = sponsor_proceeds - total_fees - carry
    net_moic          = net_proceeds / sponsor_invested if sponsor_invested > 0 else 0
    net_irr_cfs       = [-sponsor_invested] + [0.0] * (a.exit_year - 1) + [net_proceeds]
    net_irr           = _irr(net_irr_cfs)

    # Cash-on-cash and payback
    coc               = gross_moic  # same as MOIC for equity
    # Payback: find first year cumulative FCF >= invested
    cumul = 0.0
    payback = None
    for i, r in enumerate(stmts["cash_flow"]):
        cumul += r["net_cf"]
        if cumul >= sponsor_invested and payback is None:
            payback = i + 1

    # Debt paydown summary
    entry_debt = tx["total_debt"]
    exit_debt_actual = ds2[exit_yr]["total_debt_end"]
    debt_paydown = entry_debt - exit_debt_actual
    deleveraging = ds2[exit_yr]["total_debt_end"] / is_rows[exit_yr]["ebitda"] if is_rows[exit_yr]["ebitda"] > 0 else 0

    return {
        "exit_ebitda":        exit_ebitda,
        "exit_ev":            exit_ev,
        "exit_ev_ebitda":     a.exit_ev_ebitda,
        "exit_debt":          exit_debt_actual,
        "exit_equity_total":  exit_equity_total,
        "sponsor_invested":   sponsor_invested,
        "sponsor_proceeds":   sponsor_proceeds,
        "mgmt_proceeds":      mgmt_proceeds,
        "promote":            promote,
        "gross_moic":         gross_moic,
        "gross_irr":          gross_irr,
        "net_moic":           net_moic,
        "net_irr":            net_irr,
        "total_mgmt_fees":    total_fees,
        "carry":              carry,
        "coc":                coc,
        "payback_years":      payback,
        "entry_debt_ebitda":  tx["debt_ebitda"],
        "exit_debt_ebitda":   deleveraging,
        "debt_paydown":       debt_paydown,
    }


# ── Sensitivity Tables ─────────────────────────────────────────────────────────

def _run_scenario(inp: LBOInputs, a: LBOAssumptions,
                  entry_mult: float, exit_mult: float,
                  rev_cagr: float | None = None,
                  ebitda_margin_exp: float | None = None) -> tuple[float, float]:
    """Run a mini-LBO and return (IRR, MOIC). Returns (nan, nan) on failure."""
    try:
        a2 = LBOAssumptions(
            entry_ev_ebitda   = entry_mult,
            exit_ev_ebitda    = exit_mult,
            transaction_fees_pct = a.transaction_fees_pct,
            mgmt_rollover_pct    = a.mgmt_rollover_pct,
            tlb_pct              = a.tlb_pct,
            senior_notes_pct     = a.senior_notes_pct,
            sub_debt_pct         = a.sub_debt_pct,
            tlb_rate             = a.tlb_rate,
            senior_notes_rate    = a.senior_notes_rate,
            sub_debt_rate        = a.sub_debt_rate,
            revolver_size        = a.revolver_size,
            revolver_commit_fee  = a.revolver_commit_fee,
            tlb_amort_pct        = a.tlb_amort_pct,
            hold_years           = a.hold_years,
            rev_growth           = [rev_cagr or g for g in a.rev_growth],
            ebitda_margin_y0     = a.ebitda_margin_y0,
            ebitda_margin_exp    = ebitda_margin_exp if ebitda_margin_exp is not None else a.ebitda_margin_exp,
            capex_pct_rev        = a.capex_pct_rev,
            nwc_pct_rev          = a.nwc_pct_rev,
            tax_rate             = a.tax_rate,
            da_pct_rev           = a.da_pct_rev,
            exit_year            = a.exit_year,
            mgmt_promote_moic    = a.mgmt_promote_moic,
            mgmt_promote_pct     = a.mgmt_promote_pct,
            mgmt_fee_pct         = a.mgmt_fee_pct,
            carry_pct            = a.carry_pct,
        )
        tx2    = build_transaction(inp, a2)
        ds2    = build_debt_schedule(tx2, a2)
        stmts2 = build_three_statements(inp, a2, tx2, ds2)
        ret2   = build_returns(inp, a2, tx2, stmts2)
        return ret2["gross_irr"], ret2["gross_moic"]
    except Exception:
        return float("nan"), float("nan")


def build_sensitivity(inp: LBOInputs, a: LBOAssumptions,
                      tx: dict, base_returns: dict) -> dict:
    entry_mult = a.entry_ev_ebitda
    exit_mult  = a.exit_ev_ebitda

    # Table 1: IRR sensitivity — entry multiple (rows) vs exit multiple (cols), 5x5
    entry_range = [entry_mult + d for d in (-2, -1, 0, 1, 2)]
    exit_range  = [exit_mult  + d for d in (-2, -1, 0, 1, 2)]
    irr_table   = []
    moic_table1 = []
    for em in entry_range:
        row_irr  = []
        row_moic = []
        for xm in exit_range:
            irr, moic = _run_scenario(inp, a, max(3.0, em), max(3.0, xm))
            row_irr.append(irr)
            row_moic.append(moic)
        irr_table.append(row_irr)
        moic_table1.append(row_moic)

    # Table 2: MOIC sensitivity — rev CAGR (rows) vs EBITDA margin expansion (cols), 5x5
    base_cagr   = sum(a.rev_growth) / len(a.rev_growth)
    cagr_range  = [base_cagr + d for d in (-0.04, -0.02, 0, 0.02, 0.04)]
    margin_exp_range = [0.000, 0.003, 0.005, 0.008, 0.010]  # 0 to +100bps/yr
    moic_table2 = []
    irr_table2  = []
    for cagr in cagr_range:
        row_moic = []
        row_irr  = []
        for mexp in margin_exp_range:
            irr, moic = _run_scenario(inp, a, entry_mult, exit_mult,
                                       rev_cagr=max(0, cagr), ebitda_margin_exp=mexp)
            row_moic.append(moic)
            row_irr.append(irr)
        moic_table2.append(row_moic)
        irr_table2.append(row_irr)

    # Table 3: Leverage sensitivity — Debt/EBITDA (rows) vs rate environment (cols), 3x3
    base_rate  = a.tlb_rate
    rate_bumps = [-0.01, 0.0, +0.01]  # -100bps, base, +100bps
    lev_levels = [4.0, 5.0, 6.0]      # D/EBITDA targets
    lev_table  = []
    for target_lev in lev_levels:
        row = []
        for bump in rate_bumps:
            # Derive new debt percentages from target leverage
            target_debt = target_lev * inp.ltm_ebitda
            target_debt_pct = target_debt / (inp.ltm_ebitda * entry_mult) if entry_mult > 0 else 0.65
            target_debt_pct = min(0.75, max(0.30, target_debt_pct))
            # Scale tranches proportionally
            base_total = a.tlb_pct + a.senior_notes_pct + a.sub_debt_pct
            scale = target_debt_pct / base_total if base_total > 0 else 1.0
            a3 = LBOAssumptions(
                entry_ev_ebitda  = entry_mult,
                exit_ev_ebitda   = exit_mult,
                transaction_fees_pct = a.transaction_fees_pct,
                mgmt_rollover_pct    = a.mgmt_rollover_pct,
                tlb_pct          = a.tlb_pct * scale,
                senior_notes_pct = a.senior_notes_pct * scale,
                sub_debt_pct     = a.sub_debt_pct * scale,
                tlb_rate         = min(0.12, a.tlb_rate + bump),
                senior_notes_rate= min(0.15, a.senior_notes_rate + bump),
                sub_debt_rate    = min(0.18, a.sub_debt_rate + bump),
                revolver_size    = a.revolver_size,
                revolver_commit_fee = a.revolver_commit_fee,
                tlb_amort_pct    = a.tlb_amort_pct,
                hold_years       = a.hold_years,
                rev_growth       = a.rev_growth,
                ebitda_margin_y0 = a.ebitda_margin_y0,
                ebitda_margin_exp= a.ebitda_margin_exp,
                capex_pct_rev    = a.capex_pct_rev,
                nwc_pct_rev      = a.nwc_pct_rev,
                tax_rate         = a.tax_rate,
                da_pct_rev       = a.da_pct_rev,
                exit_year        = a.exit_year,
                mgmt_promote_moic= a.mgmt_promote_moic,
                mgmt_promote_pct = a.mgmt_promote_pct,
                mgmt_fee_pct     = a.mgmt_fee_pct,
                carry_pct        = a.carry_pct,
            )
            try:
                tx3    = build_transaction(inp, a3)
                ds3    = build_debt_schedule(tx3, a3)
                stmts3 = build_three_statements(inp, a3, tx3, ds3)
                ret3   = build_returns(inp, a3, tx3, stmts3)
                row.append(ret3["gross_irr"])
            except Exception:
                row.append(float("nan"))
        lev_table.append(row)

    return {
        "entry_range":       entry_range,
        "exit_range":        exit_range,
        "irr_table":         irr_table,
        "moic_table1":       moic_table1,
        "cagr_range":        cagr_range,
        "margin_exp_range":  margin_exp_range,
        "moic_table2":       moic_table2,
        "irr_table2":        irr_table2,
        "lev_levels":        lev_levels,
        "rate_bumps":        rate_bumps,
        "lev_table":         lev_table,
    }
