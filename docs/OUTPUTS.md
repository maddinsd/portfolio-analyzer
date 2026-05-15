# Output Reference Guide

Every file produced by the portfolio analyzer — what it contains, where it's saved, and how to read it.

---

## File Locations

All outputs are saved to `reports/TICKER/` with two copies:

| File | Purpose |
|------|---------|
| `TICKER_YYYYMMDD_HHMM.xlsx` | Timestamped archive |
| `TICKER_latest.xlsx` | Always points to the most recent run |
| `TICKER_YYYYMMDD_HHMM_research.pdf` | Timestamped PDF archive |
| `TICKER_latest_research.pdf` | Always current |
| `TICKER_YYYYMMDD_HHMM_pitch.pptx` | Timestamped pitch archive |
| `TICKER_latest_pitch.pptx` | Always current |
| `TICKER_YYYYMMDD_HHMM_education_student.pdf` | Companion guide |

LBO outputs: `lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx`  
M&A outputs: `ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx`

---

## Excel Workbook (17 Sheets)

Triggered by: `python3 main.py TICKER` (no flag required)

### Sheet 1 — Snapshot

Company overview card. Contains: current price, 52-week range, market cap, P/E, EV/EBITDA, beta, dividend yield, analyst consensus, DCF intrinsic value, upside/downside to DCF, sector, industry, headquarters.

All figures pulled live at runtime — no hardcoded data.

### Sheet 2 — Price Chart

12-month price history chart. Plots daily closing prices with a 50-day moving average overlay. Formatted as a line chart in the navy/steel color palette. X-axis shows monthly dates; Y-axis shows price in USD.

### Sheet 3 — Analysis

The 14-section Claude analysis, formatted into a readable two-column layout. Left column: section header. Right column: analysis text. Sections: Investment Thesis, Valuation, Financial Health, Competitive Position, Growth Drivers, Risk Factors, Analyst Consensus, Insider Activity, Earnings Quality, SEC Filings, News Sentiment, Technical Signals, Bull vs Bear, Recommendation.

If `--dry-run` is used, this sheet contains a placeholder message (no API call made).

### Sheet 4 — Bull vs Bear

Side-by-side card: three bull case arguments (green background) vs three bear case arguments (red background). Drawn from the Bull vs Bear section of the Claude analysis.

### Sheet 5 — Income Statement

Five-year income statement. Rows: Revenue, Cost of Revenue, Gross Profit, Gross Margin %, Operating Expenses, EBIT, EBITDA, Net Income, EPS. Data sourced from FMP (primary) with yfinance fallback. All values in millions USD unless noted. Alternating row shading. Margin rows displayed as percentages.

### Sheet 6 — Balance Sheet

Most recent annual balance sheet. Rows: Cash & Equivalents, Short-Term Investments, Total Current Assets, PP&E, Total Assets, Total Current Liabilities, Long-Term Debt, Total Liabilities, Total Equity. Values in millions USD.

### Sheet 7 — Cash Flow

Five-year cash flow statement. Rows: Operating Cash Flow, Capital Expenditures, Free Cash Flow, Investing Activities, Financing Activities. All values in millions USD.

### Sheet 8 — News & Sentiment

Latest 5 headlines with sentiment scoring. Each row: headline text, source, publication date, sentiment label (Positive/Neutral/Negative), sentiment score (−1.0 to +1.0). Aggregate sentiment summary at the bottom. Sourced from NewsAPI.

### Sheet 9 — DCF Model

Two-stage discounted cash flow model. Structure:

**Assumptions table** — WACC components (risk-free rate, beta, equity risk premium, cost of equity, cost of debt, tax rate, debt weight), terminal growth rate, projection years.

**FCF forecast** — Years 1–5 with revenue growth decay, operating margin, D&A, capex, working capital change, unlevered FCF.

**Terminal value** — Gordon Growth Model: `FCF_5 × (1 + TG) / (WACC − TG)`

**Valuation summary** — PV of FCF years 1–5, PV of terminal value, enterprise value, net debt, equity value, shares outstanding, intrinsic value per share, current price, upside/downside.

**5×5 sensitivity table** — WACC (±2% around base in 0.5% steps) vs terminal growth rate (1.5% to 3.5%). Color-coded: green = >20% upside, yellow = 0–20%, red = downside.

### Sheet 10 — Investment Thesis

Long-form investment thesis from the parallel research agent. Covers: primary thesis, key catalysts, valuation argument, time horizon, risk-adjusted return estimate. 300–500 words. Model: claude-haiku-4-5-20251001 for speed.

### Sheet 11 — Comps Analysis

Comparable company analysis. Peer group (3–5 companies from same sector/industry). Columns: ticker, company name, market cap, EV, P/E, EV/EBITDA, EV/Revenue, revenue growth, gross margin, operating margin, ROE. Final rows: peer median, subject company, premium/discount to median. Color-coded: green = above median, red = below.

### Sheet 12 — Earnings Preview

Forward-looking earnings preview from the parallel research agent. Covers: next earnings date, analyst consensus EPS/revenue estimate, key items to watch, recent estimate revision trend, historical beat/miss rate. 200–300 words.

### Sheet 13 — Competitive Analysis

Full competitive landscape from `competitive.py`. Sections: peer identification methodology, metric-by-metric benchmarking (revenue growth, gross margin, operating margin, ROE, forward P/E), tercile rankings (top/mid/bottom vs peers), moat assessment (Claude-generated 3–4 sentence qualitative assessment), implied P/E premium or discount.

### Sheet 14 — Analyst Coverage

Sell-side consensus data from `analyst_coverage.py`. Contains: Buy/Hold/Sell counts, bull ratio (Buy / total), consensus rating label, mean/high/low price targets, upside to mean target, target spread, individual analyst targets (last 10), quarterly EPS estimates vs actuals (next 2 quarters), revenue estimates. Sources: FMP `/analyst-stock-recommendations`, `/price-target`, `/analyst-estimates`.

### Sheet 15 — Earnings & Transcripts

Eight-quarter earnings beat/miss history from `transcript_parser.py`. Each row: quarter, reported EPS, consensus EPS, surprise amount, surprise %, beat/miss label. Summary: beat streak, total beats in 8 quarters, algorithmic tone score (−1 to +1), tone label (Positive/Neutral/Negative), next earnings date. Color-coded rows: green = beat, red = miss.

### Sheet 16 — SEC Filings

EDGAR data from `sec_parser.py`. Contains: CIK number, latest 10-K date, latest 10-Q date, filing URLs. Risk factors: top 5 risk factors from Item 1A (ranked by length, which correlates with severity). MD&A summary: 300-word excerpt from Item 7. MD&A tone signals: list of bearish/bullish language patterns detected. Business overview: 200-word excerpt from Item 1. No API calls — fully algorithmic extraction.

### Sheet 17 — Insider Transactions

Form 4 insider data from `insider_tracker.py`. Recent transactions (last 90 days): insider name, title, transaction type (Buy/Sell), shares, price, value, date. Summary: net signal (Bullish/Neutral/Bearish), conviction score (1.0–10.0), total shares bought/sold, unique buyers/sellers. 12-month net monthly chart. Note: only open-market buys (P) and sells (S) counted; option exercises, awards, and 10b5-1 plans excluded from conviction scoring.

---

## Equity Research PDF (10 pages)

Triggered by: `python3 main.py TICKER --pdf` or `--full`

Output: `TICKER_latest_research.pdf`

| Page | Content |
|------|---------|
| 1 | Cover — company name, ticker, current price, recommendation, analyst, UC branding, date |
| 2 | Executive Summary — thesis, key metrics card, recommendation box |
| 3–4 | Financial Analysis — revenue/earnings bar charts, margin trend line chart |
| 5 | Valuation — football field (horizontal bar chart), DCF summary, comps summary |
| 6–7 | Research Analysis — investment thesis, competitive position, growth drivers |
| 8 | Risk Factors — top 5 risks from SEC filing + analyst-identified risks |
| 9 | Analyst Coverage — consensus table, price target distribution |
| 10 | Appendix — DCF assumptions table, peer comps table |

Font: Times New Roman throughout. Color palette: UC navy (#003366), UC red (#E00122), steel blue (#2D5F8A). Each page has a header with the company name and ticker, footer with page number and UC affiliation.

---

## Pitch Deck (12 slides)

Triggered by: `python3 main.py TICKER --pitch` or `--full`

Output: `TICKER_latest_pitch.pptx`

| Slide | Title | Content |
|-------|-------|---------|
| 1 | Cover | Company name, ticker, current price, date, UC branding |
| 2 | Investment Summary | Rating card (BUY/HOLD/SELL), 3 thesis points, target price |
| 3 | Company Overview | Business description, revenue breakdown, key markets |
| 4 | Financial Snapshot | Revenue/EPS 5-year bar chart, key ratios table |
| 5 | DCF Valuation | WACC inputs, FCF bridge, intrinsic value vs current price |
| 6 | Comparable Companies | Comps table with peer median and subject company row |
| 7 | Competitive Analysis | Moat assessment, peer ranking chart, key differentiators |
| 8 | Football Field | Horizontal bar chart: DCF range, comps range, 52-week range, analyst targets |
| 9 | Risk Assessment | Top 5 risks from SEC filing + analyst risks, probability/impact matrix |
| 10 | Analyst Coverage | Consensus chart, price target distribution, recent estimate revisions |
| 11 | Earnings History | 8-quarter beat/miss bar chart, tone score, next earnings preview |
| 12 | Appendix | DCF sensitivity table, income statement summary |

Color palette matches Excel: navy (#003366), blue (#1F4E79), steel (#2D5F8A). No API calls at runtime — all content from pipeline data.

---

## Education Package

Triggered by: `python3 main.py TICKER --education [--audience student|professional]`

Three outputs added to the same run:

**Excel comments** — 30 cell comments added to the workbook explaining each financial metric in context. Comments reference the company's actual numbers ("Apple's gross margin of 44% means..."), not generic definitions. Author: University of Cincinnati.

**PPT speaker notes** — 12 slide notes added to the pitch deck. Each note includes: what this slide shows, how to interpret the key metric, what to watch for, and a follow-up question for discussion.

**Companion PDF** — 12-page PDF guide. Sections correspond to the analysis structure (DCF, comps, competitive analysis, etc.). Each section explains the methodology, how to interpret the output for this specific company, and key takeaways. Includes a 40-term glossary. Audience flag adjusts vocabulary: `student` uses introductory language, `professional` uses institutional terminology.

---

## LBO Model (Standalone)

Triggered by: `python3 lbo/lbo_model.py TICKER [options]`

Output: `lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx`

| Tab | Content |
|-----|---------|
| Cover | Transaction summary, key returns (IRR, MOIC), deal parameters |
| Assumptions | Entry multiple, debt structure, hold period, exit multiple |
| Transaction | Sources & Uses table, purchase price bridge, opening balance sheet |
| Income Statement | 5-year P&L with EBITDA build, interest expense, taxes, net income |
| Balance Sheet | 5-year balance sheet with goodwill, debt balances, equity |
| Cash Flow | 5-year FCF with debt paydown calculation |
| Debt Schedule | Amortization + excess cash sweep for each tranche (TLB, Senior Notes, Sub Debt) |
| Returns | Exit enterprise value, proceeds waterfall, IRR and MOIC |
| Sensitivity | Two 5×5 tables: IRR and MOIC vs entry multiple × exit multiple |

Color convention: blue inputs (0000FF), black formulas (000000). IRR color-coded: green ≥ 20%, yellow 15–20%, red < 15%.

---

## M&A Merger Consequences Model (Standalone)

Triggered by: `python3 ma/ma_model.py ACQUIRER TARGET [options]`

Output: `ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx`

| Tab | Content |
|-----|---------|
| Cover | Deal summary, accretion/dilution at a glance, key assumptions |
| Assumptions | Premium, consideration mix, synergy ramp, discount rate |
| Transaction | Purchase price, consideration split, new shares issued, exchange ratio |
| Acquirer | Standalone financials and EPS |
| Target | Standalone financials and EPS |
| Pro Forma | Combined income statement with synergies, PPA amortization, interest on acquisition debt |
| Accretion | GAAP EPS and Cash EPS accretion/dilution for Years 1, 2, 3 |
| Sensitivity | 5×5 table: accretion/dilution vs offer premium × synergy realization |

Green = accretive, red = dilutive.

---

## Automation Outputs

| Tool | Output Location | Trigger |
|------|----------------|---------|
| Morning briefing | `automation/briefings/` | 7am ET weekdays (scheduled) or `python3 automation/morning_briefing.py` |
| Market alerts | Phone notification (ntfy.sh) | Hourly 9am–4pm ET weekdays |
| Earnings calendar | `automation/calendars/` | Daily weekdays (scheduled) |
| IC memo | `automation/ic_memos/` | `python3 automation/ic_memo.py TICKER --recommendation BUY` |

IC memos are saved as `TICKER_YYYYMMDD_ic_memo.md`. Each memo is a formal Investment Committee Memorandum with executive summary, investment thesis, valuation, financial snapshot, risk assessment, competitive position, analyst coverage, insider activity, and recommendation.
