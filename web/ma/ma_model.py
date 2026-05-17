"""M&A Merger Consequences Analyzer — CLI entry point.

Usage:
    python3 ma/ma_model.py ACQUIRER TARGET [options]

Options:
    --premium PCT       Offer premium % over target price (default: 30)
    --cash-pct PCT      Cash % of total equity consideration (default: 50)
    --synergies M       Override run-rate synergies in $M (default: bottom-up estimate)
    --output PATH       Output file path (default: ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx)

Example:
    python3 ma/ma_model.py MSFT AAPL --premium 30 --cash-pct 50 --synergies 5000
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ma.ma_fetcher import fetch_ma_data
from ma.ma_engine import (
    build_transaction,
    build_synergies,
    build_pro_forma,
    build_sensitivity,
    compute_breakeven,
)
from ma.ma_excel import build_ma_excel


def _pct(v: float) -> str:
    if math.isnan(v):
        return "N/A (dilutive at all premiums)"
    return f"{v:+.1f}%"


def _fmt_m(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:,.2f}T"
    if abs(v) >= 1_000:
        return f"${v/1_000:,.1f}B"
    return f"${v:,.0f}M"


def run(acquirer: str, target: str, premium_pct: float, cash_pct: float,
        synergies_m: float | None, output_path: str | None) -> str:
    print(f"\n{'='*65}")
    print(f"  M&A MERGER CONSEQUENCES — {acquirer.upper()} / {target.upper()}")
    print(f"{'='*65}")

    # ── 1. Fetch data ──────────────────────────────────────────────────────────
    print(f"\n[1/6] Fetching acquirer data ({acquirer.upper()})...")
    acq = fetch_ma_data(acquirer)
    print(f"  {acq.lbo.company_name}: ${acq.lbo.share_price:.2f} | EPS ${acq.diluted_eps:.2f} | P/E {acq.pe_multiple:.1f}x")
    print(f"  Net Income: {_fmt_m(acq.net_income)} | Shares: {acq.diluted_shares:,.0f}M | {acq.credit_rating_proxy}")

    print(f"\n[2/6] Fetching target data ({target.upper()})...")
    tgt = fetch_ma_data(target)
    print(f"  {tgt.lbo.company_name}: ${tgt.lbo.share_price:.2f} | EPS ${tgt.diluted_eps:.2f} | P/E {tgt.pe_multiple:.1f}x")
    print(f"  EV/EBITDA: {tgt.lbo.current_ev_ebitda:.1f}x | 52wk: ${tgt.week52_low:.0f}–${tgt.week52_high:.0f}")

    # ── 2. Transaction structure ───────────────────────────────────────────────
    print(f"\n[3/6] Building transaction structure...")
    tx = build_transaction(acq, tgt, offer_premium_pct=premium_pct,
                           cash_pct=cash_pct,
                           synergies_override_m=synergies_m)

    print(f"  Offer: ${tx['offer_price']:.2f}/share ({premium_pct:.0f}% premium)")
    print(f"  Equity Value: {_fmt_m(tx['total_equity_value'])} | Total EV: {_fmt_m(tx['total_ev'])}")
    print(f"  Implied EV/EBITDA: {tx['implied_ev_ebitda']:.1f}x | Implied P/E: {tx['implied_pe']:.1f}x")
    print(f"  Mix: {cash_pct:.0f}% cash / {tx['stock_pct']:.0f}% stock")
    print(f"  New shares: {tx['new_shares_issued']:,.1f}M | Exchange ratio: {tx['exchange_ratio']:.4f}x")
    print(f"  New debt: {_fmt_m(tx['new_debt_issued'])} @ {tx['new_debt_rate']*100:.1f}%")
    print(f"  Goodwill: {_fmt_m(tx['goodwill'])} | Intangibles: {_fmt_m(tx['intangibles_acquired'])}")

    for flag in acq.warnings + tgt.warnings:
        print(f"  ⚠️  {flag}")

    # ── 3. Synergies ───────────────────────────────────────────────────────────
    print(f"\n[4/6] Building synergy model...")
    syn = build_synergies(acq, tgt, tx, synergies_override_m=synergies_m)
    print(f"  Run-rate synergies: {_fmt_m(syn['total_pretax_runrate'])} pretax / {_fmt_m(syn['total_aftertax_runrate'])} after-tax")
    print(f"  Ramp: Y1={_fmt_m(syn['syn_aftertax_y1'])} | Y2={_fmt_m(syn['syn_aftertax_y2'])} | Y3={_fmt_m(syn['syn_aftertax_y3'])}")
    print(f"  Synergy NPV: {_fmt_m(syn['synergy_npv'])}")

    # ── 4. Pro forma EPS ──────────────────────────────────────────────────────
    print(f"\n[5/6] Computing EPS accretion/dilution...")
    pf = build_pro_forma(acq, tgt, tx, syn)

    print(f"\n  {'':38} {'Year 1':>10} {'Year 2':>10} {'Year 3':>10}")
    print(f"  {'─'*68}")
    rows_display = [
        ("Acquirer Standalone EPS",        "acq_eps_standalone", False),
        ("Pro Forma GAAP EPS",             "pf_eps_gaap",        False),
        ("GAAP Accretion / (Dilution) %",  "gaap_accretion_pct", True),
        ("Pro Forma Cash EPS",             "pf_eps_cash",        False),
        ("Cash Accretion / (Dilution) %",  "cash_accretion_pct", True),
    ]
    for lbl, key, is_pct in rows_display:
        vals = [yr[key] for yr in pf["years"]]
        if is_pct:
            val_strs = [f"{v:+.1f}%" for v in vals]
        else:
            val_strs = [f"${v:.2f}" for v in vals]
        print(f"  {lbl:38} {val_strs[0]:>10} {val_strs[1]:>10} {val_strs[2]:>10}")

    # ── 5. Break-even analysis ────────────────────────────────────────────────
    be_gaap = compute_breakeven(acq, tgt, cash_pct, syn["syn_aftertax_y1"])
    be_cash = compute_breakeven(acq, tgt, cash_pct,
                                syn["syn_aftertax_y1"] + tx["intang_amort_aftertax"])
    print(f"\n  Break-even premium (GAAP):     {_pct(be_gaap) if not math.isnan(be_gaap) else 'No breakeven in 0–200% range'}")
    print(f"  Break-even premium (Cash EPS): {_pct(be_cash) if not math.isnan(be_cash) else 'No breakeven in 0–200% range'}")
    print(f"  Deal offer premium:            {premium_pct:+.1f}%")

    verdict_gaap = "ACCRETIVE" if not math.isnan(be_gaap) and premium_pct <= be_gaap else "DILUTIVE"
    print(f"\n  ▶ Year 1 GAAP verdict: {verdict_gaap} at {premium_pct:.0f}% premium")
    print(f"  ▶ Year 3 GAAP verdict: {'ACCRETIVE' if pf['years'][2]['gaap_accretion_pct'] >= 0 else 'DILUTIVE'} ({pf['years'][2]['gaap_accretion_pct']:+.1f}%)")

    # ── 6. Sensitivity tables ─────────────────────────────────────────────────
    print(f"\n[6/6] Building sensitivity tables...")
    sens = build_sensitivity(acq, tgt, tx, syn, pf)
    print(f"  ✓ Table 1: 5×5 EPS impact vs premium × synergy %")
    print(f"  ✓ Table 2: 5×5 EPS impact vs premium × cash %")
    print(f"  ✓ Table 3: 3×3 implied multiples vs premium")

    # ── 7. Excel output ───────────────────────────────────────────────────────
    if output_path is None:
        out_dir = Path(__file__).parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        date_str = date.today().strftime("%Y%m%d")
        output_path = str(out_dir / f"{acquirer.upper()}_acquires_{target.upper()}_{date_str}.xlsx")

    print(f"\nBuilding 8-tab Excel workbook...")
    build_ma_excel(acq, tgt, tx, syn, pf, sens, be_gaap, be_cash, output_path)
    print(f"  ✓ Saved: {output_path}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  MERGER CONSEQUENCES SUMMARY")
    print(f"  {acq.lbo.company_name} acquires {tgt.lbo.company_name}")
    print(f"{'='*65}")
    print(f"  Offer:        ${tx['offer_price']:.2f}/share ({premium_pct:.0f}% premium) | {_fmt_m(tx['total_equity_value'])} equity value")
    print(f"  Total EV:     {_fmt_m(tx['total_ev'])} ({tx['implied_ev_ebitda']:.1f}x EV/EBITDA)")
    print(f"  Mix:          {cash_pct:.0f}% cash ({_fmt_m(tx['cash_consideration'])}) / {tx['stock_pct']:.0f}% stock ({tx['new_shares_issued']:,.1f}M new shares)")
    print(f"  Synergies:    {_fmt_m(syn['total_pretax_runrate'])}/yr pretax | NPV {_fmt_m(syn['synergy_npv'])}")
    print(f"  Year 1 GAAP:  {pf['years'][0]['gaap_accretion_pct']:+.1f}% ({verdict_gaap})")
    print(f"  Year 3 GAAP:  {pf['years'][2]['gaap_accretion_pct']:+.1f}%")
    print(f"  Break-even:   {_pct(be_gaap)} premium (GAAP) | {_pct(be_cash)} (Cash EPS)")
    print(f"  Output:       {output_path}")
    print()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M&A merger consequences accretion/dilution model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("acquirer", help="Acquirer ticker (e.g. MSFT)")
    parser.add_argument("target",   help="Target ticker (e.g. AAPL)")
    parser.add_argument("--premium",    type=float, default=30.0,
                        help="Offer premium %% (default: 30)")
    parser.add_argument("--cash-pct",  type=float, default=50.0,
                        help="Cash %% of consideration (default: 50)")
    parser.add_argument("--synergies", type=float, default=None,
                        help="Override run-rate synergies $M")
    parser.add_argument("--output",    type=str,   default=None,
                        help="Output file path")

    args = parser.parse_args()

    try:
        run(
            acquirer=args.acquirer,
            target=args.target,
            premium_pct=args.premium,
            cash_pct=args.cash_pct,
            synergies_m=args.synergies,
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
