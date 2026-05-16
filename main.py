from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _notify_complete(ticker: str, title: str, body: str) -> None:
    try:
        import requests
        requests.post(
            "https://ntfy.sh/sam-madding-finance-alerts",
            data=body.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": "default",
                "Tags": "chart_with_upwards_trend",
            },
            timeout=10,
        )
    except Exception:
        pass


def main() -> int:
    _t0 = time.time()
    parser = argparse.ArgumentParser(prog="stock-analyzer")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude call, print payload")
    parser.add_argument("--pitch",   action="store_true", help="Generate 12-slide PowerPoint pitch deck")
    parser.add_argument("--pdf",     action="store_true", help="Generate equity research PDF report")
    parser.add_argument("--full",      action="store_true", help="Generate Excel + PDF + pitch deck")
    parser.add_argument("--education", action="store_true", help="Add educational comments/notes and companion PDF")
    parser.add_argument("--audience",  default="student",   choices=["student", "professional"],
                        help="Education audience level (default: student)")
    args = parser.parse_args()
    if args.full:
        args.pdf   = True
        args.pitch = True

    ticker = args.ticker.upper()

    # ── Output paths ──────────────────────────────────────────────────────────
    # One file per output type, numbered for Finder sort order.
    # reports/AAPL/01_AAPL_Excel_Report.xlsx
    # reports/AAPL/02_AAPL_Research_Report.pdf
    # reports/AAPL/03_AAPL_Pitch_Deck.pptx
    # reports/AAPL/04_AAPL_Education_Guide.pdf
    # reports/AAPL/05_AAPL_Analysis.md
    reports_dir = Path.home() / "Desktop" / "reports"
    ticker_dir  = reports_dir / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    xl_path    = ticker_dir / f"01_{ticker}_Excel_Report.xlsx"
    pdf_path   = ticker_dir / f"02_{ticker}_Research_Report.pdf"
    pitch_path = ticker_dir / f"03_{ticker}_Pitch_Deck.pptx"
    edu_path   = ticker_dir / f"04_{ticker}_Education_Guide.pdf"
    md_path    = ticker_dir / f"05_{ticker}_Analysis.md"

    from fetcher import fetch_stock_data, fetch_news
    from analyzer import compute_stats, compute_financials
    from reporter import build_report
    from excel import build_excel
    from dcf import run_dcf
    from research import run_research_pipeline
    from competitive import run_competitive
    from analyst_coverage import run_analyst_coverage
    from transcript_parser import run_transcript_parser
    from sec_parser import run_sec_parser
    from insider_tracker import run_insider_tracker
    from pitch import run_pitch
    from report_pdf import run_pdf

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

    # ── Run all independent modules in parallel ───────────────────────────────
    print("Running analysis modules in parallel"
          " (competitive · coverage · earnings · SEC filings · insider transactions)...")
    with ThreadPoolExecutor(max_workers=5) as pool:
        fut_comp    = pool.submit(run_competitive,        ticker, stats, fin_data)
        fut_cov     = pool.submit(run_analyst_coverage,   ticker, stats, fin_data)
        fut_tr      = pool.submit(run_transcript_parser,  ticker, stats, fin_data)
        fut_sec     = pool.submit(run_sec_parser,         ticker, stats, fin_data)
        fut_insider = pool.submit(run_insider_tracker,    ticker, stats, fin_data)
        comp_result        = fut_comp.result()
        analyst_cov_result = fut_cov.result()
        transcript_result  = fut_tr.result()
        sec_result         = fut_sec.result()
        insider_result     = fut_insider.result()

    if comp_result.get("error"):
        print(f"  Competitive: {comp_result['error']}")
    else:
        n_peers = len(comp_result.get("peers", []))
        print(f"  Competitive: {n_peers} peers via {comp_result.get('source')}")

    if analyst_cov_result.get("error"):
        print(f"  Coverage: {analyst_cov_result['error']}")
    else:
        n_an = analyst_cov_result.get("total_analysts", 0)
        cons = analyst_cov_result.get("consensus_rating", "—")
        print(f"  Coverage: {n_an} analysts · consensus: {cons}")

    if transcript_result.get("error"):
        print(f"  Earnings: {transcript_result['error']}")
    else:
        beats = transcript_result.get("beat_count", 0)
        total = transcript_result.get("total_quarters", 0)
        streak= transcript_result.get("beat_streak", 0)
        tone  = transcript_result.get("tone_label", "—")
        print(f"  Earnings: {beats}/{total} beats · streak: {streak} · tone: {tone}")

    if sec_result.get("error"):
        print(f"  SEC: {sec_result['error']}")
    else:
        n_risks  = len(sec_result.get("top_risks", []))
        sec_tone = sec_result.get("tone_signals", {}).get("tone_label", "—")
        k_date   = sec_result.get("latest_10k_date", "—")
        print(f"  SEC: 10-K {k_date} · {n_risks} risks · MD&A tone: {sec_tone}")

    if insider_result.get("error"):
        print(f"  Insider: {insider_result['error']}")
    else:
        ins_signal  = insider_result.get("net_signal_90d", "—")
        ins_score   = insider_result.get("conviction_score", 0.0)
        ins_buyers  = insider_result.get("unique_buyers_90d", 0)
        ins_sellers = insider_result.get("unique_sellers_90d", 0)
        print(f"  Insider: {ins_signal} · conviction {ins_score:.1f}/10"
              f" · {ins_buyers} buyers / {ins_sellers} sellers (90d)")

    print("Generating analysis...")
    markdown, news_sentiment, comp_assessment, cov_assessment = build_report(
        ticker, stats, fin_data, news, dcf_result, research, comp_result,
        analyst_cov_result, transcript_result, sec_result,
        insider_result=insider_result, dry_run=args.dry_run
    )
    if comp_assessment and not comp_result.get("error"):
        comp_result["claude"] = comp_assessment
    if cov_assessment and not analyst_cov_result.get("error"):
        analyst_cov_result["claude"] = cov_assessment
    md_path.write_text(markdown, encoding="utf-8")
    print(f"Saved: {md_path.name}")

    n_sheets = 7
    if dcf_result and not dcf_result.get("error"):
        n_sheets += 1
    if research:
        n_sheets += 3
    if comp_result:          # sheet always created (shows error note if failed)
        n_sheets += 1
    if analyst_cov_result:   # sheet always created (shows error note if failed)
        n_sheets += 1
    if transcript_result:    # sheet always created (shows error note if failed)
        n_sheets += 1
    if sec_result:           # sheet always created (shows error note if failed)
        n_sheets += 1
    if insider_result:       # sheet always created (shows error note if failed)
        n_sheets += 1
    print(f"Building Excel report ({n_sheets} sheets)...")
    build_excel(ticker, stats, fin_data, data["price_history"], data["sp500_history"],
                markdown, news_sentiment, dcf_result, research, comp_result,
                analyst_cov_result, transcript_result, sec_result,
                insider_result=insider_result, output_path=str(xl_path))
    print(f"Saved: {xl_path.name}")

    pitch_result = {"error": "not requested"}
    if args.pitch:
        print("Building pitch deck (12 slides)...")
        pitch_result = run_pitch(
            ticker, stats, fin_data,
            dcf_result=dcf_result,
            research=research,
            comp_result=comp_result,
            cov_result=analyst_cov_result,
            transcript_result=transcript_result,
            out_path=str(pitch_path),
        )
        if pitch_result.get("error"):
            print(f"  Pitch deck failed: {pitch_result['error']}")
        else:
            print(f"Saved: {pitch_path.name}")

    if args.pdf:
        print("Building equity research PDF...")
        pdf_result = run_pdf(
            ticker, stats, fin_data,
            dcf_result=dcf_result,
            research=research,
            comp_result=comp_result,
            cov_result=analyst_cov_result,
            transcript_result=transcript_result,
            sec_result=sec_result,
            out_path=str(pdf_path),
        )
        if pdf_result.get("error"):
            print(f"  PDF failed: {pdf_result['error']}")
            if pdf_result.get("traceback"):
                print(pdf_result["traceback"][:800])
        else:
            print(f"Saved: {pdf_path.name}")

    if args.education:
        from education.content_engine import run_content_engine
        from education.excel_educator import add_excel_comments
        from education.pptx_educator import add_ppt_notes
        from education.pdf_educator import build_companion_pdf

        audience = args.audience
        print(f"\nRunning education layer ({audience} audience) — 6 API calls...")
        edu_content = run_content_engine(
            ticker, stats, fin_data, dcf_result, audience,
            comp_result=comp_result,
            cov_result=analyst_cov_result,
            transcript_result=transcript_result,
            sec_result=sec_result,
        )
        if edu_content.get("error"):
            print(f"  Education content failed: {edu_content['error']}")
        else:
            n_comments = add_excel_comments(str(xl_path), edu_content["excel_comments"], audience)
            print(f"  Excel: {n_comments} comments added → {xl_path.name}")

            if args.pitch and not pitch_result.get("error"):
                n_slides = add_ppt_notes(str(pitch_path), edu_content["ppt_notes"])
                print(f"  PowerPoint: {n_slides} slides annotated → {pitch_path.name}")

            pdf_res = build_companion_pdf(ticker, edu_content, str(edu_path), audience)
            if pdf_res.get("error"):
                print(f"  Companion PDF failed: {pdf_res['error']}")
            else:
                print(f"  Companion PDF saved → {edu_path.name}")

    # ── Completion notification ───────────────────────────────────────────────
    elapsed = time.time() - _t0
    mins, secs = divmod(int(elapsed), 60)
    runtime_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    if args.dry_run:
        _notify_complete(
            ticker,
            f"{ticker} Dry Run Complete",
            "Dry run finished — no API calls made. Run without --dry-run for full analysis.",
        )
    elif os.path.exists(str(xl_path)):
        price  = stats.get("current_price")
        mktcap = data["info"].get("marketCap")
        rating = analyst_cov_result.get("consensus_rating", "—") if not analyst_cov_result.get("error") else "—"
        tgt    = analyst_cov_result.get("mean_target") if not analyst_cov_result.get("error") else None

        price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else "—"
        tgt_str   = f"${tgt:,.0f}"   if isinstance(tgt,   (int, float)) else "—"
        if isinstance(mktcap, (int, float)):
            if mktcap >= 1e12:
                cap_str = f"${mktcap / 1e12:.1f}T"
            elif mktcap >= 1e9:
                cap_str = f"${mktcap / 1e9:.1f}B"
            elif mktcap >= 1e6:
                cap_str = f"${mktcap / 1e6:.1f}M"
            elif mktcap >= 1e3:  # stored in millions
                cap_str = f"${mktcap / 1e3:.1f}B"
            else:
                cap_str = f"${mktcap:.0f}M"
        else:
            cap_str = "—"

        files_parts = [f"Excel ({n_sheets} sheets)"]
        if args.pdf:
            files_parts.append("PDF")
        if args.pitch:
            files_parts.append("Pitch Deck")
        if args.education:
            files_parts.append("Education Guide")

        body = (
            f"{company_name} ({ticker})\n"
            f"Rating: {rating} | Target: {tgt_str}\n"
            f"Price: {price_str} | Market Cap: {cap_str}\n"
            f"Files: {', '.join(files_parts)}\n"
            f"Saved to Desktop/reports/{ticker}/\n"
            f"Runtime: {runtime_str}"
        )
        _notify_complete(ticker, f"{ticker} Analysis Complete", body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
