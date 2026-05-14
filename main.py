from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(prog="stock-analyzer")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude call, print payload")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    from fetcher import fetch_stock_data, fetch_news
    from analyzer import compute_stats, compute_financials
    from reporter import build_report
    from excel import build_excel

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

    md_path = reports_dir / f"{ticker}.md"
    xl_path = reports_dir / f"{ticker}.xlsx"

    print("Generating analysis...")
    markdown, news_sentiment = build_report(ticker, stats, fin_data, news, dry_run=args.dry_run)
    md_path.write_text(markdown, encoding="utf-8")
    print(f"Saved: {md_path}")

    print("Building Excel report...")
    build_excel(ticker, stats, fin_data, data["price_history"], data["sp500_history"],
                markdown, news_sentiment, str(xl_path))
    print(f"Saved: {xl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
