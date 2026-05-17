"""LBO Model CLI — orchestrates fetcher → engine → excel.

Usage:
    python3 lbo/lbo_model.py TICKER [options]

Options:
    --entry-multiple FLOAT   Entry EV/EBITDA (default: current market + 10% premium)
    --hold-years INT         Hold period in years (default: 5)
    --debt-pct FLOAT         Total debt % of TEV (default: 0.60)
    --output PATH            Output file path (default: lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

# Allow imports from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from lbo.lbo_fetcher import fetch_lbo_inputs
from lbo.lbo_engine import (
    build_assumptions,
    build_transaction,
    build_debt_schedule,
    build_three_statements,
    build_returns,
    build_sensitivity,
)
from lbo.lbo_excel import build_lbo_excel


def _fmt_pct(v: float) -> str:
    return f"{v*100:.1f}%"


def _fmt_x(v: float) -> str:
    return f"{v:.2f}x"


def _fmt_m(v: float) -> str:
    return f"${v:,.1f}M"


def run(ticker: str, entry_multiple: float | None, hold_years: int, debt_pct: float,
        output_path: str | None) -> str:
    print(f"\n{'='*60}")
    print(f"  LBO MODEL — {ticker.upper()}")
    print(f"{'='*60}")

    # ── Stage 1: Fetch inputs ─────────────────────────────────────────────────
    print("\n[1/6] Fetching market data...")
    inp = fetch_lbo_inputs(ticker)

    print(f"  Company:      {inp.company_name}")
    print(f"  LTM Revenue:  {_fmt_m(inp.ltm_revenue)}")
    print(f"  LTM EBITDA:   {_fmt_m(inp.ltm_ebitda)} ({_fmt_pct(inp.ltm_ebitda_margin)} margin)")
    print(f"  Current EV:   {_fmt_m(inp.current_ev)} ({_fmt_x(inp.current_ev_ebitda)} EV/EBITDA)")
    print(f"  Net Debt:     {_fmt_m(inp.net_debt)}")

    for w in inp.warnings:
        print(f"\n  ⚠️  {w}")

    # ── Stage 2: Build assumptions ────────────────────────────────────────────
    print("\n[2/6] Building assumptions...")
    a = build_assumptions(inp, entry_multiple=entry_multiple,
                          hold_years=hold_years, debt_pct=debt_pct)

    debt_pct_total = a.tlb_pct + a.senior_notes_pct + a.sub_debt_pct
    print(f"  Entry Multiple: {_fmt_x(a.entry_ev_ebitda)}")
    print(f"  Hold Period:    {a.hold_years} years")
    print(f"  Debt / TEV:     {_fmt_pct(debt_pct_total)}")
    print(f"  TLB Rate:       {_fmt_pct(a.tlb_rate)}")
    print(f"  Exit Multiple:  {_fmt_x(a.exit_ev_ebitda)} (base)")

    # ── Stage 3: Transaction structure ───────────────────────────────────────
    print("\n[3/6] Building transaction structure...")
    tx = build_transaction(inp, a)

    print(f"  Purchase Price: {_fmt_m(tx['entry_ev'])} ({_fmt_x(a.entry_ev_ebitda)} EV/EBITDA)")
    print(f"  Equity Check:   {_fmt_m(tx['sponsor_equity'])} ({_fmt_pct(tx['equity_pct'])} of TEV)")
    print(f"  Total Debt:     {_fmt_m(tx['total_debt'])} ({tx['debt_ebitda']:.1f}x EBITDA)")
    print(f"  Blended Rate:   {_fmt_pct(tx['blended_rate'])}")
    print(f"  Coverage:       {_fmt_x(tx['coverage_yr1'])} EBITDA/interest")

    for f in tx.get("flags", []):
        print(f"  ⚠️  {f}")

    # ── Stage 4: Three statements + debt schedule ─────────────────────────────
    print("\n[4/6] Building 3-statement model and debt schedule...")
    ds_pass1 = build_debt_schedule(tx, a)
    stmts = build_three_statements(inp, a, tx, ds_pass1)

    # Check balance sheet (bs_rows is a list of dicts, each has "bs_check")
    bs_ok = True
    for row in stmts["balance_sheet"]:
        yr = row["year"]
        chk = row.get("bs_check", 0)
        if abs(chk) > 0.1:
            print(f"  ⚠️  Balance sheet out of balance Year {yr}: {chk:.2f}")
            bs_ok = False
    if bs_ok:
        print(f"  ✓ Balance sheet balances all {a.hold_years} years")

    # ── Stage 5: Returns ──────────────────────────────────────────────────────
    print("\n[5/6] Computing returns...")
    ret = build_returns(inp, a, tx, stmts)

    print(f"  Exit EV:        {_fmt_m(ret['exit_ev'])} ({_fmt_x(a.exit_ev_ebitda)} EV/EBITDA)")
    print(f"  Exit Equity:    {_fmt_m(ret['exit_equity_total'])}")
    print(f"  Gross IRR:      {_fmt_pct(ret['gross_irr'])}")
    print(f"  Gross MOIC:     {_fmt_x(ret['gross_moic'])}")
    print(f"  Net IRR:        {_fmt_pct(ret['net_irr'])}")
    print(f"  Net MOIC:       {_fmt_x(ret['net_moic'])}")

    # ── Stage 6: Sensitivity ──────────────────────────────────────────────────
    print("\n[6/6] Building sensitivity tables...")
    sens = build_sensitivity(inp, a, tx, ret)
    print(f"  ✓ IRR sensitivity (5×5 entry×exit)")
    print(f"  ✓ MOIC sensitivity (5×5 rev CAGR×margin)")
    print(f"  ✓ Leverage sensitivity (3×3 debt%×rate)")

    # ── Assemble data package ─────────────────────────────────────────────────
    data = {
        "inputs": inp,
        "assumptions": a,
        "transaction": tx,
        "statements": stmts,
        "returns": ret,
        "sensitivity": sens,
    }

    # ── Output path ───────────────────────────────────────────────────────────
    if output_path is None:
        out_dir = Path(__file__).parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        date_str = date.today().strftime("%Y%m%d")
        output_path = str(out_dir / f"{ticker.upper()}_{date_str}_lbo.xlsx")

    # ── Build Excel ───────────────────────────────────────────────────────────
    print(f"\nBuilding Excel workbook...")
    build_lbo_excel(data, output_path)
    print(f"  ✓ Saved: {output_path}")

    print(f"\n{'='*60}")
    print(f"  SUMMARY — {inp.company_name} LBO")
    print(f"{'='*60}")
    print(f"  Entry:       {_fmt_x(a.entry_ev_ebitda)} EV/EBITDA | {_fmt_m(tx['entry_ev'])}")
    print(f"  Capital:     {_fmt_pct(tx['equity_pct'])} equity / {_fmt_pct(1-tx['equity_pct'])} debt")
    print(f"  Exit:        {_fmt_x(a.exit_ev_ebitda)} EV/EBITDA (Y{a.hold_years})")
    print(f"  Gross IRR:   {_fmt_pct(ret['gross_irr'])} | MOIC: {_fmt_x(ret['gross_moic'])}")
    print(f"  Net IRR:     {_fmt_pct(ret['net_irr'])} | MOIC: {_fmt_x(ret['net_moic'])}")
    print(f"  Output:      {output_path}")
    print()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LBO model for any public company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--entry-multiple", type=float, default=None,
                        help="Entry EV/EBITDA multiple (default: market + 10%% premium)")
    parser.add_argument("--hold-years", type=int, default=5,
                        help="Hold period in years (default: 5)")
    parser.add_argument("--debt-pct", type=float, default=0.60,
                        help="Total debt as %% of TEV (default: 0.60)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path")

    args = parser.parse_args()

    try:
        run(
            ticker=args.ticker,
            entry_multiple=args.entry_multiple,
            hold_years=args.hold_years,
            debt_pct=args.debt_pct,
            output_path=args.output,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
