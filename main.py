from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(prog="stock-analyzer")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude call, print payload")
    parser.add_argument("--pitch",   action="store_true", help="Generate 12-slide PowerPoint pitch deck")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # ── Output paths ──────────────────────────────────────────────────────────
    # Timestamped archive:  reports/AAPL/AAPL_20260514_1630.{xlsx,md}
    # Quick-access latest:  reports/AAPL/AAPL_latest.{xlsx,md}
    reports_dir = Path(__file__).parent / "reports"
    ticker_dir  = reports_dir / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    stamp    = datetime.now().strftime("%Y%m%d_%H%M")
    stem     = f"{ticker}_{stamp}"
    md_path  = ticker_dir / f"{stem}.md"
    xl_path  = ticker_dir / f"{stem}.xlsx"
    md_latest = ticker_dir / f"{ticker}_latest.md"
    xl_latest = ticker_dir / f"{ticker}_latest.xlsx"

    from fetcher import fetch_stock_data, fetch_news
    from analyzer import compute_stats, compute_financials
    from reporter import build_report
    from excel import build_excel
    from dcf import run_dcf
    from research import run_research_pipeline
    from competitive import run_competitive
    from analyst_coverage import run_analyst_coverage
    from pitch import run_pitch

    print(f"Fetching data for {ticker}...")
    data = fetch_stock_data(ticker)

    print("Fetching news...")
    company_name = data["info"].get("shortName") or data["info"].get("longName") or ticker
    news = fetch_news(ticker, company_name)
    if news:
        print(f"  Found {len(news)} article(s).")
    else:
        print("  No articles found.")

    print("Computing statistics...")
    stats    = compute_stats(data)
    fin_data = compute_financials(data)

    print("Running DCF model...")
    dcf_result = run_dcf(data, fin_data)
    if dcf_result.get("error"):
        print(f"  DCF skipped: {dcf_result['error']}")
    else:
        print(f"  WACC: {dcf_result['inputs']['wacc']:.2f}%")
        print(f"  Intrinsic value: ${dcf_result['valuation']['intrinsic']:.2f}")

    research = None
    if not args.dry_run:
        print("Spawning research pipeline (3 agents in parallel)...")
        research = run_research_pipeline(ticker, stats, fin_data)

    print("Mapping competitive landscape...")
    comp_result = run_competitive(ticker, stats, fin_data)
    if comp_result.get("error"):
        print(f"  Competitive: {comp_result['error']}")
    else:
        n_peers = len(comp_result.get("peers", []))
        print(f"  Found {n_peers} peers via {comp_result.get('source')}")

    print("Fetching analyst coverage...")
    analyst_cov_result = run_analyst_coverage(ticker, stats, fin_data)
    if analyst_cov_result.get("error"):
        print(f"  Analyst coverage: {analyst_cov_result['error']}")
    else:
        n_an = analyst_cov_result.get("total_analysts", 0)
        cons = analyst_cov_result.get("consensus_rating", "—")
        print(f"  {n_an} analysts · consensus: {cons}")

    print("Generating analysis...")
    markdown, news_sentiment, comp_assessment, cov_assessment = build_report(
        ticker, stats, fin_data, news, dcf_result, research, comp_result,
        analyst_cov_result, dry_run=args.dry_run
    )
    if comp_assessment and not comp_result.get("error"):
        comp_result["claude"] = comp_assessment
    if cov_assessment and not analyst_cov_result.get("error"):
        analyst_cov_result["claude"] = cov_assessment
    md_path.write_text(markdown, encoding="utf-8")
    shutil.copy2(md_path, md_latest)
    print(f"Saved: {md_path}")
    print(f"  → {md_latest.name}")

    n_sheets = 9
    if dcf_result and not dcf_result.get("error"):
        n_sheets += 1
    if research:
        n_sheets += 3
    if comp_result:          # sheet always created (shows error note if failed)
        n_sheets += 1
    if analyst_cov_result:   # sheet always created (shows error note if failed)
        n_sheets += 1
    print(f"Building Excel report ({n_sheets} sheets)...")
    build_excel(ticker, stats, fin_data, data["price_history"], data["sp500_history"],
                markdown, news_sentiment, dcf_result, research, comp_result,
                analyst_cov_result, str(xl_path))
    shutil.copy2(xl_path, xl_latest)
    print(f"Saved: {xl_path}")
    print(f"  → {xl_latest.name}")

    if args.pitch:
        pitch_path   = ticker_dir / f"{stem}_pitch.pptx"
        pitch_latest = ticker_dir / f"{ticker}_latest_pitch.pptx"
        print("Building pitch deck (12 slides)...")
        pitch_result = run_pitch(
            ticker, stats, fin_data,
            dcf_result=dcf_result,
            research=research,
            comp_result=comp_result,
            cov_result=analyst_cov_result,
            out_path=str(pitch_path),
        )
        if pitch_result.get("error"):
            print(f"  Pitch deck failed: {pitch_result['error']}")
        else:
            shutil.copy2(pitch_path, pitch_latest)
            print(f"Saved: {pitch_path}")
            print(f"  → {pitch_latest.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
