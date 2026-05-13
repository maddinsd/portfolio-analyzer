from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analyzer import analyze
from fetcher import fetch_all
from reporter import assemble_report, build_payload, call_claude, write_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="portfolio-analyzer",
        description="Fetch holdings, compute stats, and produce a markdown portfolio report.",
    )
    parser.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. AAPL MSFT NVDA")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the Claude API call and print the JSON payload that would be sent.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path(__file__).parent / "reports",
        help="Directory to write reports into (default: ./reports).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = [t.upper() for t in args.tickers]

    try:
        data = fetch_all(tickers)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    stats = analyze(data)
    payload = build_payload(stats)

    if args.dry_run:
        print(json.dumps(stats, indent=2))
        print(f"\nPayload size: {len(payload)} chars", file=sys.stderr)
        return 0

    try:
        analysis = call_claude(payload)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    report = assemble_report(stats, analysis)
    path = write_report(report, args.reports_dir)
    print(f"Report written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
