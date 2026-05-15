# CLAUDE.md — Portfolio Analyzer

## 1. PROJECT SUMMARY
Professional stock analyzer CLI (`python3 main.py TICKER`). Stack: Python 3.9, yfinance, FMP REST API, SEC EDGAR REST API (free, no key), anthropic SDK (claude-sonnet-4-6), openpyxl, python-dotenv, NewsAPI, requests. Pipeline: yfinance + FMP parallel fetch → compute stats + DCF → peer competitive fetch → analyst coverage fetch → earnings beat/miss parse → SEC EDGAR filing parse → Claude API analysis (Sonnet 4.6, MAX_TOKENS=4096) → 3 parallel research agents → markdown report + 16-sheet Goldman-formatted Excel workbook. Secrets in `.env` (ANTHROPIC_API_KEY, NEWS_API_KEY, FMP_API_KEY) — never committed. User is a finance student; explain financial concepts when introducing new analysis features, skip coding basics.

**Report output:** `reports/TICKER/TICKER_YYYYMMDD_HHMM.{xlsx,md}` (timestamped archive) + `reports/TICKER/TICKER_latest.{xlsx,md}` (always current). With `--pitch`: also `*_pitch.pptx`. With `--pdf`: also `*_research.pdf`. `--full` sets both. Ticker subfolder created automatically.

## 2. FILE MAP
Read ONLY the file listed. Never open additional files for a single-file task.

| Task | File | Key identifiers |
|---|---|---|
| CLI args, pipeline order, module integration | `main.py` | `main()`, lazy imports, `n_sheets` counter, timestamped output paths. Uses `ThreadPoolExecutor(max_workers=5)` to run competitive, analyst_coverage, transcript_parser, sec_parser, and insider_tracker in parallel. |
| yfinance + FMP data fetch | `fetcher.py` | `fetch_stock_data()`, `fetch_news()`, `INFO_FIELDS` line 12. FMP: `_fmp_get()`, `_fmp_to_income_df()`. FMP owns: income-statement (primary), profile (additive: fmp_ceo/employees/city/state/exchange/ipo_date), quote (additive: fmp_change_pct). yfinance owns: price history, beta, S&P 500, balance sheet, cashflow, all valuation fields. FMP calls fire in parallel (ThreadPoolExecutor, max_workers=5), timeout=10s each, silent fallback to yfinance on failure. |
| Returns, volatility, margins, ratios, financials | `analyzer.py` (258 lines) | `compute_stats()`, `compute_financials()`. All monetary values in **millions**. |
| Claude prompt, payload assembly, markdown, sentiment | `reporter.py` | `build_report()`, `_build_payload()`, `ANALYSIS_STRUCTURE` (14 sections). Accepts `transcript_result` + `sec_result` + `insider_result` params. Payload: `edgar` key (10k/10q dates, tone, top 3 risks, mda snippet), `transcript` key (streak, beats, tone, score, surp, next), `insider` key (signal, score, bought/sold, cluster, top_tx). `tgt`/`nAn` omitted when `cov` present (duplicates). `rel` removed (computable). `dcf.px` removed (duplicates `px`). |
| Any Excel: sheets, charts, colors, formatting | `excel.py` | `build_excel()`, design constants top-of-file. Accepts `transcript_result` + `sec_result` params; calls `_build_transcript_sheet()` and `_build_sec_sheet()`. |
| DCF model, WACC, sensitivity table | `dcf.py` | `run_dcf()`. Constants: RF=4.5, ERP=5.5, TG=2.5, N=5 |
| Research agents: thesis, comps, earnings | `research.py` (195 lines) | `run_research_pipeline()`. Model: haiku-4-5-20251001, timeout=60s |
| Competitive landscape, peer metrics, moat assessment | `competitive.py` | `run_competitive()`. yfinance Sector/Industry API requires **lowercase** names. FMP `/search-name` fires as fallback when yfinance returns 0 peers; FMP `/profile` as fallback when yfinance returns empty info for a peer. Returns target, peers, peer_medians, rankings, claude (moat assessment from reporter.py). |
| Analyst coverage: consensus, price targets, EPS estimates | `analyst_coverage.py` | `run_analyst_coverage()`. FMP: `/analyst-stock-recommendations` (buy/hold/sell counts), `/price-target` (mean/high/low from last 10), `/analyst-estimates` (quarterly EPS + revenue). Falls back to yfinance info for targetMeanPrice/numberOfAnalystOpinions if FMP returns nothing. Returns consensus_rating, bull_ratio, mean/high/low_target, upside_pct, target_spread_pct, estimates, recent_targets. claude assessment piggybacked on reporter.py API call (cov JSON field). |
| 12-slide PowerPoint pitch deck | `pitch.py` (1220 lines) | `run_pitch(ticker, stats, fin_data, dcf_result, research, comp_result, cov_result, out_path)`. Uses python-pptx 1.0.x. Design constants top-of-file match excel.py palette. No API calls. Triggered by `--pitch` flag in main.py. Football field on slide 8 drawn manually (shapes, no chart). |
| Goldman-style equity research PDF | `report_pdf.py` | `run_pdf(ticker, stats, fin_data, dcf_result, research, comp_result, cov_result, out_path)`. Uses reportlab 4.x + matplotlib (Agg). No API calls. Triggered by `--pdf` flag. `--full` = `--pdf + --pitch`. Output: `*_research.pdf` + `*_latest_research.pdf`. 9–10 pages: cover, exec summary, financials (charts), valuation (football field), research, risks, appendix. |
| Earnings beat/miss history, tone score | `transcript_parser.py` | `run_transcript_parser(ticker, stats, fin_data)`. yfinance `earnings_dates` → 8Q EPS beat/miss. FMP `income-statement` (limit=5) → quarterly revenue actuals. Algorithmic tone score (−1 to +1). No API calls. Returns beat_miss_history, beat_streak, miss_streak, beat_count, tone_score, tone_label, guidance_signals, next_earnings_date. |
| SEC EDGAR filings: 10-K risk factors, MD&A tone, business overview | `sec_parser.py` | `run_sec_parser(ticker, stats, fin_data)`. No API key — requires `User-Agent` header + ≥150ms delay. CIK lookup via `company_tickers.json`; filings via `submissions/CIK{10}.json`; HTML via Archives URL. Extracts Item 1 (business), Item 1A (top 5 risks by length), Item 7 (MD&A summary + tone). Algorithmic only — no Claude calls. Payload key: `"edgar"` (NOT `"sec"` — that key is taken by sector). Returns cik, latest_10k_date, latest_10q_date, filing_url_10k, filing_url_10q, filing_history, top_risks, mda_summary, business_summary, tone_signals. |
| Insider transactions: Form 4 buy/sell signals, conviction scoring | `insider_tracker.py` | `run_insider_tracker(ticker, stats, fin_data)`. EDGAR Form 4 XML via `submissions/CIK{10}.json` + Archives URL. KEEP codes: P (open market buy), S (open market sale). EXCLUDE: A/M/F/G/D/C/I/V. 10b5-1 flag from `aff10b5One` XML field — excluded from signal scoring. Conviction score 1.0–10.0 (base 5.0 ± CEO/CFO/Director buy bonuses + cluster bonus ± CEO sell/multi-director sell penalties). Returns transactions_90d, net_signal_90d, total_bought/sold_90d, unique_buyers/sellers_90d, cluster_signal, conviction_score/label, monthly_net_12m, top_insiders. Payload key: `"insider"`. |
| Phase 6 automation tools (standalone, no pipeline changes) | `automation/` dir | See automation section below |
| LBO model (standalone, no pipeline changes) | `lbo/lbo_model.py` | Entry: `python3 lbo/lbo_model.py TICKER [--entry-multiple N] [--hold-years N] [--debt-pct N]`. Orchestrates fetcher→engine→excel. Outputs `lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx`. 9-tab workbook. |
| LBO data fetch | `lbo/lbo_fetcher.py` | `fetch_lbo_inputs(ticker) -> LBOInputs`. FMP for IS/BS/CF (with yfinance fallback for totalRevenue/ebitda/capex when FMP 403). Returns `LBOInputs` dataclass. TLB rate: min(8.5%, SOFR+300bps). |
| LBO calculations: transaction, debt schedule, 3-statements, returns, sensitivity | `lbo/lbo_engine.py` | `LBOAssumptions` dataclass + 5 builder functions. Two-pass debt schedule (1st pass no sweep → 2nd pass with FCF sweep). Goodwill as BS plug (equity+debt−cash−ppe−ar). Newton-Raphson IRR. 5×5 sensitivity tables. |
| LBO Excel output (9-tab workbook) | `lbo/lbo_excel.py` | `build_lbo_excel(data, output_path)`. Tabs: Cover, Assumptions, Transaction, IS, BS, CF, Debt Schedule, Returns, Sensitivity. Color: blue inputs `0000FF`, black formulas `000000`. IRR/MOIC color-coded: green≥20%/2.5x, yellow 15-20%/2.0-2.5x, red below. |
| M&A data layer | `ma/ma_fetcher.py` | `fetch_ma_data(ticker) -> MACompanyData`. Imports from `lbo.lbo_fetcher` — NEVER rewrite fetching. Adds: EPS, P/E, net_income, 52wk range, analyst target, book equity, credit proxy. |
| M&A engine: transaction, synergies, pro forma, sensitivity | `ma/ma_engine.py` | `build_transaction()`, `build_synergies()`, `build_pro_forma()`, `build_sensitivity()`, `compute_breakeven()`. EPS math: pf_ni_gaap / pf_shares. Cash EPS adds back intangibles amort. Break-even via binary search. 5×5 sensitivity center = base case. |
| M&A Excel output (8-tab workbook) | `ma/ma_excel.py` | `build_ma_excel(acq, tgt, tx, syn, pf, sens, be_gaap, be_cash, output_path)`. Tabs: Cover, Assumptions, Transaction, Acquirer, Target, Pro Forma, Accretion, Sensitivity. Green=accretive, red=dilutive. |
| M&A model CLI | `ma/ma_model.py` | Entry: `python3 ma/ma_model.py ACQUIRER TARGET [--premium PCT] [--cash-pct PCT] [--synergies M]`. Orchestrates fetcher→engine→excel. Output: `ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx`. |
| Education layer: 3 API calls → Excel comments + PPT notes + companion PDF | `education/` dir | `content_engine.py`: exactly 3 Sonnet calls (Excel comments JSON, PPT notes JSON, PDF text). `excel_educator.py`: `add_excel_comments(xlsx, comments)` — header text matching, never hardcoded addresses. `pptx_educator.py`: `add_ppt_notes(pptx, notes)` — adds to existing slides. `pdf_educator.py`: `build_companion_pdf(ticker, content, path)` — 12-section guide + 40-term glossary via reportlab. Triggered by `--education` flag; `--audience student\|professional` controls tone. |
| Adding a new module | new `.py` + `main.py` + `reporter.py` + `excel.py` | Follow pattern in ROADMAP section exactly |

**Automation directory (`automation/`):** Standalone scheduled tools — do NOT modify main pipeline. `watchlist.json` (tickers + thresholds), `common.py` (shared utils: quotes, notifications, headlines), `morning_briefing.py` (7am daily briefing → `briefings/`), `notification_tool.py` (hourly market alerts → `.alert_cache.json`), `ic_memo.py` (on-demand IC memo → `ic_memos/`), `earnings_calendar.py` (earnings tracking + previews → `calendars/`). Phone notifications via ntfy.sh topic `sam-madding-finance-alerts`. Schedules: `morning-market-briefing` (`0 11 * * 1-5`), `market-alert-monitor` (`0 13-20 * * 1-5`), `earnings-calendar-monitor` (`30 11 * * 1-5`).

**Current Excel sheets (17):** Snapshot, Price Chart, Analysis, Bull vs Bear, Income Statement, Balance Sheet, Cash Flow, News & Sentiment, DCF Model, Investment Thesis, Comps Analysis, Earnings Preview, Competitive Analysis, Analyst Coverage, Earnings & Transcripts, SEC Filings, Insider Transactions.

## 3. COMMON COMMANDS
```bash
# Always start here — no API call, no cost
python3 main.py AAPL --dry-run

# Verify payload token size
python3 main.py AAPL --dry-run 2>&1 | grep -i chars

# Full run (costs API tokens)
python3 main.py AAPL

# Full run with all outputs: Excel + PDF + pitch deck
python3 main.py AAPL --full

# PDF only (dry-run safe)
python3 main.py AAPL --dry-run --pdf

# Syntax check all modules
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['main.py','fetcher.py','analyzer.py','reporter.py','excel.py','dcf.py','research.py','competitive.py','analyst_coverage.py','transcript_parser.py','pitch.py','report_pdf.py','sec_parser.py','insider_tracker.py','automation/common.py','automation/morning_briefing.py','automation/notification_tool.py','automation/ic_memo.py','automation/earnings_calendar.py','education/content_engine.py','education/excel_educator.py','education/pptx_educator.py','education/pdf_educator.py']]; print('syntax ok')"

# Education layer (costs 3 Sonnet API calls)
python3 main.py AAPL --education --audience student
python3 main.py AAPL --full --education --audience professional   # all outputs + education

# Phase 6 automation tools (run manually to test)
python3 automation/morning_briefing.py
python3 automation/notification_tool.py
python3 automation/earnings_calendar.py
python3 automation/ic_memo.py AAPL --recommendation BUY --conviction HIGH

# M&A merger model (standalone)
python3 ma/ma_model.py MSFT GOOGL --premium 25 --cash-pct 60 --synergies 3000
python3 ma/ma_model.py ACQUIRER TARGET  # 30% premium, 50% cash, bottom-up synergies

# Syntax check M&A files
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['ma/ma_fetcher.py','ma/ma_engine.py','ma/ma_excel.py','ma/ma_model.py']]; print('ma syntax ok')"

# LBO model (standalone)
python3 lbo/lbo_model.py AAPL --entry-multiple 8 --hold-years 5 --debt-pct 0.60
python3 lbo/lbo_model.py AAPL   # uses current market multiple (usually warns: too expensive)

# Syntax check LBO files
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['lbo/lbo_fetcher.py','lbo/lbo_engine.py','lbo/lbo_excel.py','lbo/lbo_model.py']]; print('lbo syntax ok')"

# Commit and push
git add -p && git commit -m "message" && git push
```

## 4. EFFICIENCY RULES
Apply every session without exception.

1. **Read only the FILE MAP target.** One task = one file. Never open the full codebase.
2. **Always `--dry-run` before full runs.** Dry run = no Claude API call, no cost, 5-10s. Full run = 25-35s + API tokens.
3. **Never re-explain architecture.** PROJECT SUMMARY + FILE MAP contain it. Ask the user for clarification instead of reading files to infer context.
4. **For Excel questions, read only `excel.py`.** Design constants are at the top of the file. Never open reporter.py or analyzer.py for formatting context.
5. **For new Excel sheets, copy the closest existing `_build_*_sheet()` function** as a template. Never redesign layout from scratch.
6. **Do not run the full pipeline to test a single module.** Use `--dry-run` or isolated function tests.
7. **For research.py changes, test with `--dry-run` first** — each full research run costs 3 Haiku API calls and 19-35s wall time.

## 5. QUALITY STANDARDS
Non-negotiable. Never relax these.

**Excel design system** (defined in `excel.py` top-of-file constants):
- Font: Calibri. Colors: `_NAVY="003366"`, `_BLUE="1F4E79"`, `_STEEL="2D5F8A"`, `_GRN_BG="E2F0D9"`, `_RED_BG="FFE0E0"`.
- Alternating row fills on all data tables. `_BORDER` applied to every data cell. Headers via `_header_style()`.
- Never introduce new colors or fonts. Match existing sheet style exactly when adding sheets.

**API and model rules:**
- Sonnet 4.6 (`claude-sonnet-4-6`) for main analysis (`reporter.py`) and research agents (`research.py`). Sonnet minimum for any analysis output — never Haiku.
- Haiku (`claude-haiku-4-5-20251001`) for the finance intent hook classification only (`~/.claude/hooks/finance_intent.py`).
- Never use Opus in any module — cost control.
- MAX_TOKENS=4096 in `reporter.py`. Do not lower; truncation breaks the 14-section structure.
- Claude payload target: ≤ 900 tokens (increased from 800 to accommodate transcript data). Verify: `python3 main.py AAPL --dry-run 2>&1 | grep -i chars`.

**Data and financial rules:**
- All monetary values in `analyzer.py` are in millions. DCF uses raw dollars internally, converts to millions for output.
- Never hardcode ticker-specific data. Every number must come from `stats` or `fin_data` at runtime.
- DCF halts silently if WACC > 20% or terminal growth ≥ WACC — never produce negative EV without a logged warning.
- `ANALYSIS_STRUCTURE` in `reporter.py` defines 14 mandatory sections. Never remove or rename them.
- Research pipeline: every agent returns `_placeholder(kind, error)` on failure — pipeline never raises.

## 6. ROADMAP

**Phase 2: Complete.** 12 sheets, DCF model, 3-agent parallel research pipeline.

**Phase 3: Complete.** 14 sheets, competitive analysis (sheet 13), analyst coverage (sheet 14).

**Phase 4: Complete.**
- `pitch.py` — 12-slide pitch deck (`--pitch`)
- `report_pdf.py` — equity research PDF (`--pdf`; `--full` = pdf + pitch)
- `transcript_parser.py` — earnings beat/miss + tone score (sheet 15)

**Phase 5: Complete.**
- `transcript_parser.py` — earnings beat/miss + tone score (sheet 15)
- `sec_parser.py` — SEC EDGAR 10-K/10-Q parser: risk factors, MD&A tone, business overview (sheet 16)
- `insider_tracker.py` — Form 4 insider transactions: buy/sell signals, conviction scoring (sheet 17)

**Phase 6: Complete.** `automation/` directory: morning briefing (7am daily), market alert monitor (hourly during market hours), IC memo generator (on-demand), earnings calendar (daily + weekly). Three Claude Code routines created. Phone notifications via ntfy.sh.

**Phase 7: Complete.** `lbo/` directory: 9-tab Goldman-quality LBO model. Fetcher (FMP+yfinance fallback), engine (debt schedule, 3-statements, returns, sensitivity), Excel output. Standalone — does not touch main pipeline. Output: `lbo/outputs/TICKER_YYYYMMDD_lbo.xlsx`.

**Phase 8: Complete.** `ma/` directory: 8-tab Goldman-quality M&A merger model. Fetcher wraps lbo_fetcher, engine builds transaction/synergies/pro forma/sensitivity, Excel output. CLI: `python3 ma/ma_model.py ACQUIRER TARGET`. Output: `ma/outputs/ACQ_acquires_TGT_YYYYMMDD.xlsx`.

**Phase 9: Complete.** `education/` directory: 3-Sonnet-call content engine, Excel cell comments (header text matching), PowerPoint speaker notes, companion PDF (12-section guide + 40-term glossary). `--education` flag + `--audience student|professional`. Adds to existing outputs — never regenerates.

**Phase 10 (next):**
- Output cleanup complete: UC branding throughout all outputs (PDF, PPTX, Education PDF, IC memo). Goldman Sachs references removed from all user-visible strings. Logo at `assets/uc_logo.png` embedded in PDF cover.
- `briefing.py` → daily news digest with Claude summary

**Pattern every new module must follow (do not deviate):**
1. Standalone `.py` file, single responsibility, no cross-imports between modules.
2. Entry function signature: `run_[module](ticker: str, stats: dict, fin_data: dict) -> dict`
3. Returns `{"error": None, ...results}` on success or `{"error": "reason"}` on failure. Never raises.
4. `main.py`: call after existing pipeline stages, store as `[module]_result`, add to `n_sheets` counter, pass to `build_excel()` and `build_report()`.
5. `excel.py`: add `_build_[module]_sheet(wb, result)`, call from `build_excel()`. Check `result.get("error")` before rendering.
6. `reporter.py`: add `_[module]_md_section(result)`, call from `build_report()`. Render "*Analysis unavailable.*" on placeholder.

## 7. NEVER DO

- **Never commit `.env`** — live API keys (ANTHROPIC_API_KEY, NEWS_API_KEY, FMP_API_KEY). Confirmed in `.gitignore`. Verify: `git check-ignore .env`.
- **Never use key starting `sk-ant-api03-uKs9Y6Ca`** — revoked/compromised.
- **Never lower MAX_TOKENS below 4096** in `reporter.py` — truncates analysis sections.
- **Never use Haiku for analysis output** — Sonnet minimum. Haiku is only for the intent hook classifier.
- **Never expose FMP_API_KEY** in logs, print statements, or error messages — read via `os.environ.get("FMP_API_KEY")` inside functions only.
- **Never let an FMP failure crash the pipeline** — every `_fmp_get()` call is wrapped in try/except and returns None on any error. Callers check `if result:` before using.
- **Never add an FMP call without timeout=10** — enforced in `_fmp_get()` via `requests.get(..., timeout=10)`.
- **Never fetch the same field from both FMP and yfinance** — clear ownership: FMP owns income-statement + profile + quote enrichment; yfinance owns everything else.
- **Never call Claude API from a hook** — `~/.claude/hooks/finance_intent.py` uses Haiku for classification only; never for analysis or report generation.
- **Never use `sys.exit()` inside a module** — only `main.py` and `fetcher.py` may exit the process. All other modules return error dicts.
- **Never overwrite `~/.claude/settings.json`** — always read then merge. New keys only; never replace the file.
- **Never add an Excel sheet without updating `n_sheets` in `main.py`** — the sheet count print would be wrong. Current: 17 sheets max (9 base + DCF + 3 research + comp + cov + transcript + sec + insider).
- **Never request EDGAR without the User-Agent header** — violates SEC ToS and gets IP blocked. Header: `{"User-Agent": "SamuelMadding/1.0 sdmadding@icloud.com"}`.
- **Never add delays shorter than 150ms between EDGAR requests** — EDGAR rate limit is 10 req/sec; 150ms keeps well under it.
- **Never pass raw 10-K text to Claude** — extract and summarize first. `sec_parser.py` is algorithmic-only; no API calls.
- **Never use `"sec"` as a payload key for SEC filing data** — that key is already taken by `info.get("sector")`. Use `"edgar"` instead.
- **Never count option exercises (M), awards (A), tax witholding (F), or 10b5-1 sales as buy/sell signals** — `insider_tracker.py` KEEP codes are P and S only; 10b5-1 flag (`aff10b5One`) excludes transactions from conviction scoring.
- **FMP insider-trading endpoints are 403 (legacy plan)** — `insider_tracker.py` uses EDGAR Form 4 XML exclusively.
- **Never read more than one file to answer a formatting question** — the answer is always in `excel.py`.
- **Never skip `--dry-run` as the first test of any change** — always confirm the pipeline runs before spending API tokens.
- **Never exceed 3 Claude API calls in the education layer** — all content is generated in `education/content_engine.py` in exactly 3 Sonnet calls. Never add a 4th. Never use Haiku for education output.
- **Never use Goldman Sachs branding** — institution is always "University of Cincinnati | Carl H. Lindner College of Business". Short form: "University of Cincinnati | Lindner College of Business". Footer: "University of Cincinnati | Lindner College of Business — For Educational Purposes Only". Logo: `assets/uc_logo.png`.
- **Never use "Samuel Madding, CFA Candidate"** — analyst name is "Samuel Madding" only, no title, no credential abbreviation.
- **UC accent color: `#E00122`** (UC red) — use alongside existing navy `#003366`. Defined as `_UC_RED` in `report_pdf.py` and available for use in other modules.

## 8. SELF-UPDATE INSTRUCTIONS

Update this file at the end of any session where project structure changed. Write for Claude, not humans — dense and specific.

**Triggers and required actions:**

| Trigger | Action |
|---|---|
| New `.py` file added | Add row to FILE MAP: responsibility, entry function, key constants |
| New Excel sheet added | Update FILE MAP excel.py row note + increment sheet count in PROJECT SUMMARY + update `n_sheets` note in NEVER DO |
| Phase completed | Move to "Complete" in ROADMAP, update "next" pointer |
| New cross-file constant or model added | Add to QUALITY STANDARDS |
| CLAUDE.md exceeds 2500 tokens | Trim completed ROADMAP phases first, then verbose QUALITY STANDARDS notes. Never trim FILE MAP, EFFICIENCY RULES, or NEVER DO. |

**Token budget:** Estimate after every edit. Target: ≤ 2500 tokens (~1875 words). If over budget, remove completed roadmap history before anything else.

**Commit after every update:**
```bash
git add CLAUDE.md && git commit -m "update CLAUDE.md: [what changed]" && git push
```
