# CLAUDE.md — Portfolio Analyzer

## 1. PROJECT SUMMARY
Professional stock analyzer CLI (`python3 main.py TICKER`). Stack: Python 3.9, yfinance, FMP REST API, anthropic SDK (claude-sonnet-4-6), openpyxl, python-dotenv, NewsAPI, requests. Pipeline: yfinance + FMP parallel fetch → compute stats + DCF → peer competitive fetch (yfinance Sector/Industry + FMP /search-name fallback, parallel) → Claude API analysis (Sonnet 4.6, MAX_TOKENS=4096) → 3 parallel research agents → markdown report + 13-sheet Goldman-formatted Excel workbook. Secrets in `.env` (ANTHROPIC_API_KEY, NEWS_API_KEY, FMP_API_KEY) — never committed. User is a finance student; explain financial concepts when introducing new analysis features, skip coding basics.

**Report output:** `reports/TICKER/TICKER_YYYYMMDD_HHMM.{xlsx,md}` (timestamped archive) + `reports/TICKER/TICKER_latest.{xlsx,md}` (always current). Ticker subfolder created automatically.

## 2. FILE MAP
Read ONLY the file listed. Never open additional files for a single-file task.

| Task | File | Key identifiers |
|---|---|---|
| CLI args, pipeline order, module integration | `main.py` | `main()`, lazy imports, `n_sheets` counter, timestamped output paths |
| yfinance + FMP data fetch | `fetcher.py` | `fetch_stock_data()`, `fetch_news()`, `INFO_FIELDS` line 12. FMP: `_fmp_get()`, `_fmp_to_income_df()`. FMP owns: income-statement (primary), profile (additive: fmp_ceo/employees/city/state/exchange/ipo_date), quote (additive: fmp_change_pct). yfinance owns: price history, beta, S&P 500, balance sheet, cashflow, all valuation fields. FMP calls fire in parallel (ThreadPoolExecutor, max_workers=5), timeout=10s each, silent fallback to yfinance on failure. |
| Returns, volatility, margins, ratios, financials | `analyzer.py` (258 lines) | `compute_stats()`, `compute_financials()`. All monetary values in **millions**. |
| Claude prompt, payload assembly, markdown, sentiment | `reporter.py` (491 lines) | `build_report()`, `_build_payload()`, `ANALYSIS_STRUCTURE` (14 sections) |
| Any Excel: sheets, charts, colors, formatting | `excel.py` (887 lines) | `build_excel()`, design constants top-of-file, `_header_style()` |
| DCF model, WACC, sensitivity table | `dcf.py` | `run_dcf()`. Constants: RF=4.5, ERP=5.5, TG=2.5, N=5 |
| Research agents: thesis, comps, earnings | `research.py` (195 lines) | `run_research_pipeline()`. Model: haiku-4-5-20251001, timeout=60s |
| Competitive landscape, peer metrics, moat assessment | `competitive.py` | `run_competitive()`. yfinance Sector/Industry API requires **lowercase** names. FMP `/search-name` fires as fallback when yfinance returns 0 peers; FMP `/profile` as fallback when yfinance returns empty info for a peer. Returns target, peers, peer_medians, rankings, claude (moat assessment from reporter.py). |
| Adding a new Phase 3/4 module | new `.py` + `main.py` + `reporter.py` + `excel.py` | Follow pattern in ROADMAP section exactly |

**Current Excel sheets (13):** Snapshot, Price Chart, Analysis, Bull vs Bear, Income Statement, Balance Sheet, Cash Flow, News & Sentiment, DCF Model, Investment Thesis, Comps Analysis, Earnings Preview, Competitive Analysis.

## 3. COMMON COMMANDS
```bash
# Always start here — no API call, no cost
python3 main.py AAPL --dry-run

# Verify payload token size
python3 main.py AAPL --dry-run 2>&1 | grep -i chars

# Full run (costs API tokens)
python3 main.py AAPL

# Syntax check all modules
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['main.py','fetcher.py','analyzer.py','reporter.py','excel.py','dcf.py','research.py']]; print('syntax ok')"

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
- Claude payload target: ≤ 800 tokens. Verify: `python3 main.py AAPL --dry-run 2>&1 | grep -i chars`.

**Data and financial rules:**
- All monetary values in `analyzer.py` are in millions. DCF uses raw dollars internally, converts to millions for output.
- Never hardcode ticker-specific data. Every number must come from `stats` or `fin_data` at runtime.
- DCF halts silently if WACC > 20% or terminal growth ≥ WACC — never produce negative EV without a logged warning.
- `ANALYSIS_STRUCTURE` in `reporter.py` defines 14 mandatory sections. Never remove or rename them.
- Research pipeline: every agent returns `_placeholder(kind, error)` on failure — pipeline never raises.

## 6. ROADMAP

**Phase 2: Complete.** 12 sheets, DCF model, 3-agent parallel research pipeline.

**Phase 3 (next):**
- `competitive_analysis.py` → Excel sheet 13 (Competitive Analysis)
- `analyst_coverage.py` → Excel sheet 14 (Analyst Coverage)

**Phase 4:**
- `pitch.py` → `.pptx` pitch deck output
- `pdf.py` → equity research PDF
- `briefing.py` → daily news digest

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
- **Never add an Excel sheet without updating `n_sheets` in `main.py`** — the sheet count print would be wrong.
- **Never read more than one file to answer a formatting question** — the answer is always in `excel.py`.
- **Never skip `--dry-run` as the first test of any change** — always confirm the pipeline runs before spending API tokens.

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
