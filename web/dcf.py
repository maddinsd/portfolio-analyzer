from __future__ import annotations

import math

RF     = 4.5    # risk-free rate (%)
ERP    = 5.5    # equity risk premium (%)
TG     = 2.5    # terminal growth rate (%)
N      = 5      # forecast years
DECAY  = 0.15   # annual growth decay toward TG


def _row(df, *keys):
    if df is None or df.empty:
        return None
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _sf(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _avg(lst):
    clean = [x for x in lst if x is not None]
    return sum(clean) / len(clean) if clean else None


def _extract_drivers(data: dict):
    fin  = data.get("financials")
    cf   = data.get("cashflow")
    info = data.get("info", {})

    if fin is None or fin.empty or cf is None or cf.empty:
        return None, "No financial data available"

    fin = fin.sort_index(axis=1, ascending=False)
    cf  = cf.sort_index(axis=1, ascending=False)

    n = min(len(fin.columns), len(cf.columns), 4)
    if n < 2:
        return None, "Need ≥2 years of history"

    rev_row    = _row(fin, "Total Revenue")
    ebit_row   = _row(fin, "EBIT", "Operating Income")
    tax_row    = _row(fin, "Tax Provision")
    pretax_row = _row(fin, "Pretax Income")
    da_row     = _row(cf,  "Depreciation And Amortization")
    capex_row  = _row(cf,  "Capital Expenditure")
    nwc_row    = _row(cf,  "Change In Working Capital")
    int_row    = _row(fin, "Interest Expense")

    if rev_row is None:
        return None, "No revenue row in financials"
    if ebit_row is None:
        return None, "No EBIT row in financials"

    # Revenue series (raw dollars, most-recent first)
    revenues = [_sf(rev_row.iloc[i]) for i in range(min(4, len(rev_row)))]
    revenues = [r for r in revenues if r and r > 0]
    if len(revenues) < 2:
        return None, "Insufficient revenue history"

    if len(revenues) >= 4:
        rev_cagr = (revenues[0] / revenues[3]) ** (1 / 3) - 1
    else:
        rev_cagr = (revenues[0] / revenues[-1]) ** (1 / (len(revenues) - 1)) - 1
    rev_cagr = max(-0.10, min(0.40, rev_cagr))

    # Tax rate (average of available years, clamped to 5-50%)
    tax_rates = []
    for i in range(n):
        tp = _sf(tax_row.iloc[i]    if tax_row    is not None and i < len(tax_row)    else None)
        pt = _sf(pretax_row.iloc[i] if pretax_row is not None and i < len(pretax_row) else None)
        if tp is not None and pt is not None and pt > 0:
            t = abs(tp / pt)
            if 0.05 <= t <= 0.50:
                tax_rates.append(t)
    tax_rate = _avg(tax_rates) or 0.21

    # EBIT margin
    ebit_margins = []
    for i in range(n):
        e = _sf(ebit_row.iloc[i] if i < len(ebit_row) else None)
        r = revenues[i] if i < len(revenues) else None
        if e is not None and r:
            ebit_margins.append(e / r)
    ebit_margin = max(0.01, min(0.60, _avg(ebit_margins) or 0.25))

    # D&A % revenue
    da_pcts = []
    for i in range(n):
        d = _sf(da_row.iloc[i] if da_row is not None and i < len(da_row) else None)
        r = revenues[i] if i < len(revenues) else None
        if d is not None and r:
            da_pcts.append(abs(d) / r)
    da_pct = max(0.0, _avg(da_pcts) or 0.02)

    # CapEx % revenue
    capex_pcts = []
    for i in range(n):
        c = _sf(capex_row.iloc[i] if capex_row is not None and i < len(capex_row) else None)
        r = revenues[i] if i < len(revenues) else None
        if c is not None and r:
            capex_pcts.append(abs(c) / r)
    capex_pct = max(0.0, _avg(capex_pcts) or 0.03)

    # ΔWC % revenue — positive = cash inflow (WC decreased)
    nwc_pcts = []
    for i in range(n):
        w = _sf(nwc_row.iloc[i] if nwc_row is not None and i < len(nwc_row) else None)
        r = revenues[i] if i < len(revenues) else None
        if w is not None and r:
            nwc_pcts.append(w / r)
    nwc_pct = _avg(nwc_pcts) or 0.0

    # Pre-tax cost of debt = |Interest Expense| / Total Debt
    total_debt = _sf(info.get("totalDebt"))
    kd_pretax = 0.04
    if int_row is not None and total_debt and total_debt > 0:
        ie = _sf(int_row.iloc[0] if len(int_row) > 0 else None)
        if ie is not None:
            kd_pretax = max(0.01, min(0.20, abs(ie) / total_debt))

    return {
        "base_rev":    revenues[0],
        "rev_cagr":    rev_cagr,
        "ebit_margin": ebit_margin,
        "da_pct":      da_pct,
        "capex_pct":   capex_pct,
        "nwc_pct":     nwc_pct,
        "tax_rate":    tax_rate,
        "kd_pretax":   kd_pretax,
    }, None


def _compute_wacc(data: dict, drivers: dict):
    info = data.get("info", {})
    beta = max(0.1, min(3.0, _sf(info.get("beta")) or 1.0))
    ke   = (RF + beta * ERP) / 100

    kd_pretax   = drivers["kd_pretax"]
    tax         = drivers["tax_rate"]
    kd_aftertax = kd_pretax * (1 - tax)

    mktcap  = _sf(info.get("marketCap")) or 0
    debt    = _sf(info.get("totalDebt"))  or 0
    total_v = mktcap + debt
    if total_v <= 0:
        return None, "Cannot compute weights: zero market cap + debt"

    we   = mktcap / total_v
    wd   = debt   / total_v
    wacc = ke * we + kd_aftertax * wd

    if wacc > 0.20:
        return None, f"WACC {wacc*100:.1f}% exceeds 20% ceiling — halted"

    return {
        "beta": beta, "ke": ke,
        "kd_pretax": kd_pretax, "kd_aftertax": kd_aftertax,
        "tax_rate": tax, "we": we, "wd": wd, "wacc": wacc,
    }, None


def _build_forecast(drivers: dict, wacc_data: dict):
    cagr  = drivers["rev_cagr"]
    tg    = TG / 100
    base  = drivers["base_rev"]
    em    = drivers["ebit_margin"]
    da_p  = drivers["da_pct"]
    cx_p  = drivers["capex_pct"]
    nwc_p = drivers["nwc_pct"]
    tax   = wacc_data["tax_rate"]

    # Growth decays toward terminal: g_i = tg + (cagr - tg) * (1-DECAY)^i
    growth = [max(tg, tg + (cagr - tg) * (1 - DECAY) ** i) for i in range(N)]

    revenues, ebits, nopats, das, capexes, dnwcs, fcffs = [], [], [], [], [], [], []
    prev = base
    for g in growth:
        rev   = prev * (1 + g)
        ebit  = rev * em
        nopat = ebit * (1 - tax)
        da    = rev * da_p
        cx    = rev * cx_p
        dnwc  = rev * nwc_p   # positive = cash inflow
        fcff  = nopat + da - cx + dnwc
        revenues.append(rev); ebits.append(ebit); nopats.append(nopat)
        das.append(da); capexes.append(cx); dnwcs.append(dnwc); fcffs.append(fcff)
        prev = rev

    # Flag 3+ consecutive negative FCFF
    warnings = []
    streak = max_streak = 0
    for f in fcffs:
        streak = streak + 1 if f < 0 else 0
        max_streak = max(max_streak, streak)
    if max_streak >= 3:
        warnings.append(f"⚠ {max_streak} consecutive negative FCFF years — review assumptions")

    return {
        "growth": growth,
        "revenue": revenues, "ebit": ebits, "nopat": nopats,
        "da": das, "capex": capexes, "dnwc": dnwcs, "fcff": fcffs,
    }, warnings


def _valuation(forecast: dict, wacc_data: dict, fin_data: dict, data: dict):
    wacc = wacc_data["wacc"]
    tg   = TG / 100
    if tg >= wacc:
        return None, f"Terminal growth ({TG}%) ≥ WACC ({wacc*100:.1f}%) — Gordon Growth invalid"

    fcffs   = forecast["fcff"]
    pv_fcff = sum(f / (1 + wacc) ** (i + 1) for i, f in enumerate(fcffs))
    tv_fcff = fcffs[-1] * (1 + tg)
    tv      = tv_fcff / (wacc - tg)
    pv_tv   = tv / (1 + wacc) ** N
    ev      = pv_fcff + pv_tv

    if ev < 0:
        return None, f"Negative enterprise value ({ev/1e9:.1f}B) — halted"

    # Net debt from fin_data (values in millions)
    bs        = fin_data.get("balance_sheet") or {}
    net_debt  = ((bs.get("total_debt") or 0) - (bs.get("cash") or 0)) * 1e6

    eq_val = ev - net_debt

    info   = data.get("info", {})
    shares = (_sf(info.get("sharesOutstanding")) or
              _sf(info.get("impliedSharesOutstanding")))
    if not shares or shares <= 0:
        return None, "No shares outstanding data"

    iv     = eq_val / shares
    px     = _sf(info.get("currentPrice"))
    upside = ((iv / px) - 1) * 100 if px else None

    M = 1e6
    return {
        "pv_fcff_m":    round(pv_fcff / M, 1),
        "tv_m":         round(tv      / M, 1),
        "pv_tv_m":      round(pv_tv   / M, 1),
        "ev_m":         round(ev      / M, 1),
        "net_debt_m":   round(net_debt / M, 1),
        "eq_val_m":     round(eq_val  / M, 1),
        "shares_m":     round(shares  / M, 2),
        "intrinsic":    round(iv, 2),
        "current_price": px,
        "upside_pct":   round(upside, 1) if upside is not None else None,
        "tv_pct":       round(pv_tv / ev * 100, 1),
    }, None


def _sensitivity(forecast: dict, wacc_data: dict, fin_data: dict, data: dict):
    base_w = wacc_data["wacc"]
    wacc_range = [base_w + d for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    tg_range   = [0.015, 0.020, 0.025, 0.030, 0.035]

    bs       = fin_data.get("balance_sheet") or {}
    net_debt = ((bs.get("total_debt") or 0) - (bs.get("cash") or 0)) * 1e6
    info     = data.get("info", {})
    shares   = (_sf(info.get("sharesOutstanding")) or
                _sf(info.get("impliedSharesOutstanding")) or 1)
    fcffs    = forecast["fcff"]

    table = []
    for w in wacc_range:
        row_vals = []
        for tg in tg_range:
            if tg >= w or w <= 0:
                row_vals.append(None)
                continue
            pv    = sum(f / (1 + w) ** (i + 1) for i, f in enumerate(fcffs))
            tv    = fcffs[-1] * (1 + tg) / (w - tg)
            ev    = pv + tv / (1 + w) ** N
            iv    = (ev - net_debt) / shares
            row_vals.append(round(iv, 2) if iv > 0 else None)
        table.append(row_vals)

    return {
        "wacc_range": [round(w * 100, 2) for w in wacc_range],
        "tg_range":   [round(t * 100,  1) for t in tg_range],
        "table": table,
    }


def run_dcf(data: dict, fin_data: dict) -> dict:
    drivers, err = _extract_drivers(data)
    if err:
        return {"error": err}

    wacc_data, err = _compute_wacc(data, drivers)
    if err:
        return {"error": err}

    forecast, warnings = _build_forecast(drivers, wacc_data)

    val, err = _valuation(forecast, wacc_data, fin_data, data)
    if err:
        return {"error": err}

    sens = _sensitivity(forecast, wacc_data, fin_data, data)

    M = 1e6
    return {
        "error": None,
        "warnings": warnings,
        "inputs": {
            "rf":           RF,
            "erp":          ERP,
            "beta":         round(wacc_data["beta"], 3),
            "ke":           round(wacc_data["ke"]          * 100, 2),
            "kd_pretax":    round(wacc_data["kd_pretax"]   * 100, 2),
            "kd_aftertax":  round(wacc_data["kd_aftertax"] * 100, 2),
            "tax_rate":     round(wacc_data["tax_rate"]    * 100, 2),
            "we":           round(wacc_data["we"]          * 100, 1),
            "wd":           round(wacc_data["wd"]          * 100, 1),
            "wacc":         round(wacc_data["wacc"]        * 100, 2),
            "tg":           TG,
            "rev_cagr":     round(drivers["rev_cagr"]      * 100, 2),
            "ebit_margin":  round(drivers["ebit_margin"]   * 100, 2),
            "da_pct":       round(drivers["da_pct"]        * 100, 2),
            "capex_pct":    round(drivers["capex_pct"]     * 100, 2),
            "nwc_pct":      round(drivers["nwc_pct"]       * 100, 2),
        },
        "forecast": {
            "years":      list(range(1, N + 1)),
            "growth_pct": [round(g * 100, 2) for g in forecast["growth"]],
            "revenue_m":  [round(v / M, 1) for v in forecast["revenue"]],
            "ebit_m":     [round(v / M, 1) for v in forecast["ebit"]],
            "nopat_m":    [round(v / M, 1) for v in forecast["nopat"]],
            "da_m":       [round(v / M, 1) for v in forecast["da"]],
            "capex_m":    [round(v / M, 1) for v in forecast["capex"]],
            "dnwc_m":     [round(v / M, 1) for v in forecast["dnwc"]],
            "fcff_m":     [round(v / M, 1) for v in forecast["fcff"]],
        },
        "valuation": val,
        "sensitivity": sens,
    }
