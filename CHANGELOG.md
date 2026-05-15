# Changelog

All notable changes to this project are documented here.

---

## v9.0 — Education Layer
**2026-05-15**

- Added `--education` flag to generate contextual learning materials alongside the analysis
- Added `--audience {student,professional}` flag to adjust vocabulary level
- **`education/content_engine.py`** — exactly 3 Claude Sonnet API calls generate all education content (Excel comments as JSON, PPT notes as JSON, companion PDF text)
- **`education/excel_educator.py`** — adds 30 cell comments to workbook via header text matching (no hardcoded cell addresses)
- **`education/pptx_educator.py`** — adds 12 speaker notes to pitch deck slides
- **`education/pdf_educator.py`** — builds 12-page companion PDF with 40-term glossary using reportlab
- All outputs branded University of Cincinnati | Carl H. Lindner College of Business
- UC logo (`assets/uc_logo.png`) embedded on PDF cover page

---

## v8.0 — M&A Merger Consequences Model
**2026-05-10**

- Added `ma/` directory with 8-tab Goldman-quality merger consequences model
- **`ma/ma_fetcher.py`** — wraps `lbo_fetcher`; adds EPS, P/E, net income, 52-week range, analyst target, book equity
- **`ma/ma_engine.py`** — transaction, Purchase Price Allocation, GAAP + Cash EPS accretion/dilution, synergy ramp, break-even premium binary search, 5×5 sensitivity
- **`ma/ma_excel.py`** — 8-tab workbook: Cover, Assumptions, Transaction, Acquirer, Target, Pro Forma, Accretion, Sensitivity
- **`ma/ma_model.py`** — CLI: `python3 ma/ma_model.py MSFT AAPL --premium 30 --cash-pct 60 --synergies 3000`
- Standalone — no changes to main pipeline
- Output: `ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx`

---

## v7.0 — LBO Model
**2026-05-01**

- Added `lbo/` directory with 9-tab Goldman-style leveraged buyout model
- **`lbo/lbo_fetcher.py`** — FMP income/balance/cash flow with yfinance fallback for EBITDA/capex
- **`lbo/lbo_engine.py`** — two-pass debt schedule (amortization + FCF sweep), integrated 3-statements, Newton-Raphson IRR, 5×5 sensitivity tables, goodwill as balance sheet plug
- **`lbo/lbo_excel.py`** — 9-tab workbook: Cover, Assumptions, Transaction, IS, BS, CF, Debt Schedule, Returns, Sensitivity
- **`lbo/lbo_model.py`** — CLI: `python3 lbo/lbo_model.py AAPL --entry-multiple 8 --hold-years 5`
- Standalone — no changes to main pipeline
- Output: `lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx`

---

## v6.0 — Automation Layer
**2026-04-20**

- Added `automation/` directory with four scheduled tools
- **`automation/morning_briefing.py`** — Claude-written morning briefing for watchlist movers (scheduled 7am ET)
- **`automation/notification_tool.py`** — hourly price alert monitor with `.alert_cache.json` deduplication
- **`automation/earnings_calendar.py`** — 24-hour earnings preview for watchlist companies
- **`automation/ic_memo.py`** — on-demand Investment Committee Memorandum generator
- **`automation/common.py`** — shared utilities: quotes, notifications, headlines
- Phone notifications via ntfy.sh topic `sam-madding-finance-alerts`
- Three Claude Code routines created for automated scheduling
- Watchlist configuration via `automation/watchlist.json`

---

## v5.0 — Insider Transactions (Sheet 17)
**2026-04-10**

- **`insider_tracker.py`** — EDGAR Form 4 XML extraction; conviction scoring (1.0–10.0); 90-day transaction history
- Keep codes: P (open-market buy), S (open-market sale) only; excludes awards, option exercises, 10b5-1 plans
- Conviction scoring: CEO buy (+2.0), CFO buy (+1.5), director buy (+0.5), cluster buy (+1.0), CEO sell (−1.5)
- Added Sheet 17 — Insider Transactions to Excel workbook
- Insider data passed to Claude payload (abbreviated as `"insider"` key)

---

## v5.0 — SEC EDGAR Parser (Sheet 16)
**2026-04-08**

- **`sec_parser.py`** — direct EDGAR REST API (no third-party library); CIK lookup → submissions → filing HTML
- Extracts Item 1 (business overview), Item 1A (top 5 risks by length), Item 7 (MD&A summary + tone signals)
- Rate pacing: 150ms between EDGAR requests; User-Agent header per SEC ToS
- Added Sheet 16 — SEC Filings to Excel workbook
- SEC data passed to Claude payload as `"edgar"` key (not `"sec"` — reserved for sector)

---

## v4.0 — PDF Report + Pitch Deck
**2026-03-25**

- **`report_pdf.py`** — 10-page equity research PDF using reportlab 4.x + matplotlib; triggered by `--pdf`
- **`pitch.py`** — 12-slide PowerPoint pitch deck using python-pptx; triggered by `--pitch`
- `--full` flag combines `--pdf + --pitch` in one run
- Football field valuation drawn manually in pitch deck (shapes, no chart object)
- PDF includes: cover, exec summary, financials charts, valuation football field, research, risks, appendix

---

## v4.0 — Earnings & Transcripts (Sheet 15)
**2026-03-20**

- **`transcript_parser.py`** — 8-quarter EPS beat/miss history from yfinance + quarterly revenue from FMP
- Algorithmic tone score (−1 to +1) from guidance language patterns
- Added Sheet 15 — Earnings & Transcripts to Excel workbook
- Earnings data passed to Claude payload (`"transcript"` key)

---

## v3.0 — Analyst Coverage (Sheet 14)
**2026-03-10**

- **`analyst_coverage.py`** — FMP analyst recommendations, price targets, EPS estimates
- Consensus rating with bull ratio calculation; mean/high/low targets from last 10 analyst reports
- Added Sheet 14 — Analyst Coverage to Excel workbook
- Analyst data passed to Claude payload (`"cov"` key)

---

## v3.0 — Competitive Analysis (Sheet 13)
**2026-03-05**

- **`competitive.py`** — peer identification via yfinance sector/industry, FMP fallback
- Benchmarks: revenue growth, gross margin, operating margin, ROE, forward P/E
- Tercile ranking (top/mid/bottom vs peer distribution)
- Moat assessment from Claude (piggybacked on main reporter.py API call)
- Added Sheet 13 — Competitive Analysis to Excel workbook

---

## v2.0 — Research Pipeline + DCF
**2026-02-15**

- **`research.py`** — three parallel research agents (Haiku): Investment Thesis, Comps Analysis, Earnings Preview
- **`dcf.py`** — two-stage DCF with CFA-standard WACC construction; 5×5 sensitivity table
- Added Sheets 9–12: DCF Model, Investment Thesis, Comps Analysis, Earnings Preview
- Claude payload increased to 14-section analysis structure
- `ThreadPoolExecutor(max_workers=5)` for parallel analysis modules

---

## v1.0 — Initial Release
**2026-01-20**

- `main.py` — CLI entry point with `--dry-run` flag
- `fetcher.py` — yfinance + FMP parallel data fetch; SEC EDGAR free tier
- `analyzer.py` — returns, volatility, margins, ratios (all values in millions)
- `reporter.py` — Claude Sonnet analysis, markdown report
- `excel.py` — Excel workbook with 8 sheets: Snapshot, Price Chart, Analysis, Bull vs Bear, Income Statement, Balance Sheet, Cash Flow, News & Sentiment
- `dcf.py` — basic DCF model
- Output: timestamped reports in `reports/TICKER/`
