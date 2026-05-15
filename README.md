# Portfolio Analyzer

**A single command produces a complete equity research package** — 17-sheet financial model, 12-slide pitch deck, 10-page research report, and standalone LBO/M&A models — using live market data and parallel AI agents. What takes a junior analyst 3–4 hours manually runs in under 30 seconds.

```bash
python3 main.py AAPL --full
```

Built by **Samuel Madding** | University of Cincinnati — Carl H. Lindner College of Business  
Developed as a demonstration of applied AI and financial modeling skills targeting equity research roles.

---

## What It Produces

| Output | Description | Trigger |
|--------|-------------|---------|
| **Excel workbook** | 17 sheets: snapshot, financials, DCF, comps, competitive analysis, earnings history, SEC filings, insider transactions | `python3 main.py AAPL` |
| **Research PDF** | 10-page institutional-style equity research report with charts and football field | `--pdf` |
| **Pitch deck** | 12-slide PowerPoint with rating card, DCF, comps table, football field | `--pitch` |
| **Education guide** | Excel cell comments, slide speaker notes, 12-page companion PDF with 40-term glossary | `--education` |
| **LBO model** | 9-tab leveraged buyout model: transaction, debt schedule, 3-statements, returns, sensitivity | `python3 lbo/lbo_model.py AAPL` |
| **M&A model** | 8-tab merger consequences model: accretion/dilution (GAAP + Cash EPS), synergies, break-even analysis | `python3 ma/ma_model.py MSFT AAPL` |

All outputs are timestamped and archived in `reports/TICKER/` automatically.

---

## How It Works

```
python3 main.py AAPL --full
       │
       ├─ [1] Data fetch (parallel, 5 threads)
       │    ├─ yfinance: price history, balance sheet, cash flows, market data
       │    ├─ FMP API: income statement (5yr), management profile, analyst ratings
       │    └─ NewsAPI: latest 5 headlines
       │
       ├─ [2] Compute statistics & run DCF model
       │
       ├─ [3] Parallel analysis modules (5 threads simultaneously)
       │    ├─ Competitive analysis — peer identification, metric benchmarking, moat scoring
       │    ├─ Analyst coverage — consensus rating, price targets, EPS estimates
       │    ├─ Earnings parser — 8-quarter beat/miss history, tone scoring
       │    ├─ SEC EDGAR parser — 10-K risk factors, MD&A tone (no API key required)
       │    └─ Insider tracker — Form 4 buy/sell signals, conviction scoring
       │
       ├─ [4] Claude analysis (claude-sonnet-4-6)
       │    └─ 14-section structured analysis + 3 parallel research agents
       │
       └─ [5] Output generation
            ├─ Markdown report
            ├─ 17-sheet Excel workbook
            ├─ 10-page equity research PDF
            └─ 12-slide pitch deck
```

Total runtime: ~30 seconds (network-bound). Claude API call: ~8 seconds.

---

## Data Sources

**yfinance** — Price history, beta, 52-week range, balance sheet, cash flow statement, insider ownership, dividend history. Free, no key required.

**Financial Modeling Prep (FMP)** — Income statement (5 years historical + 5 quarters), company profile (CEO, employee count, HQ location), analyst recommendations (Buy/Hold/Sell counts), price targets from individual analysts, quarterly EPS and revenue estimates. Free tier + paid key.

**SEC EDGAR** (free government API, no key) — CIK lookup, 10-K annual filing extraction, 10-Q quarterly filing, Form 4 insider transactions. Requires a `User-Agent` header identifying the requester per SEC terms of service. Rate limited to 10 requests/second; this tool paces at ≤7/second.

**NewsAPI** — Latest 5 headlines for the company and ticker symbol for news sentiment analysis.

**Anthropic Claude API** — Powers the 14-section structured analysis and three parallel research agents (investment thesis, comps analysis, earnings preview). Model: `claude-sonnet-4-6`. Token budget: ≤900 tokens input, 4,096 tokens output.

---

## Financial Models

### DCF Model (`dcf.py`)
Two-stage discounted cash flow using the same methodology taught in the CFA curriculum:
- **WACC** calculated from beta (CAPM), risk-free rate (4.5% — current 10Y Treasury), equity risk premium (5.5% historical average)
- **5-year explicit forecast** of free cash flow with revenue growth decay
- **Terminal value** using Gordon Growth Model at 2.5% perpetuity growth
- **5×5 sensitivity table**: WACC ±2% vs terminal growth rate 1.5%–3.5%
- Halts gracefully if WACC > 20% or terminal growth ≥ WACC (prevents nonsensical negative EVs)

### Comparable Company Analysis
Automatically identifies 3–5 peers from the same sector using yfinance's industry classification, with FMP as fallback when yfinance returns no results. Benchmarks: revenue growth, gross margin, operating margin, ROE, forward P/E. Each metric ranked relative to peer distribution (top/mid/bottom tercile). Computes implied P/E premium or discount to peer median.

### LBO Model (`lbo/`)
9-tab Goldman-style leveraged buyout model built entirely from live data:
- **Sources & Uses** with sponsor equity, term loan B, senior notes, subordinated debt
- **Debt schedule** with two-pass FCF sweep (first pass builds amortization schedule, second pass applies excess cash sweep)
- **Integrated 3-statement model** (income statement, balance sheet, cash flow)
- **Newton-Raphson IRR** — custom implementation, no numpy-financial dependency
- **5×5 sensitivity tables**: entry multiple × exit multiple, entry multiple × debt ratio
- Opening balance sheet uses goodwill as a plug to guarantee balance at close

### M&A Merger Consequences Model (`ma/`)
8-tab accretion/dilution model for any acquirer/target pair:
- **Consideration mix**: Cash + stock in any ratio; computes new shares issued, exchange ratio, pro forma share count
- **Purchase Price Allocation**: 30% of acquisition premium to intangibles, 70% to goodwill; straight-line amortization over 10 years
- **EPS analysis**: GAAP EPS (includes D&A step-up) and Cash EPS (adds back amortization) for Years 1, 2, 3
- **Synergy model**: Revenue, COGS, SG&A synergies with 50%/75%/100% ramp; NPV calculation at 8% discount rate
- **Break-even premium**: Binary search finds the offer premium at which deal exactly breaks even on EPS
- **5×5 sensitivity**: Accretion/dilution vs offer premium × synergy realization

---

## Automation Layer (`automation/`)

Four scheduled tools that run automatically without manual intervention:

**Morning Briefing** (7am ET weekdays) — Scans the watchlist, retrieves overnight price moves, generates a Claude-written briefing for positions with significant moves. Saves to `automation/briefings/` and sends a push notification to your phone.

**Market Alert Monitor** (hourly, 9am–4pm ET weekdays) — Checks live prices against user-defined thresholds. Fires a phone notification when a position crosses a price alert or moves more than a configurable percentage intraday.

**Earnings Calendar** (daily weekdays) — Tracks upcoming earnings dates for watchlist companies. Sends a preview report 24 hours before each earnings release with analyst consensus, recent beat/miss history, and EPS surprise trend.

**IC Memo Generator** (on-demand) — Produces a formal Investment Committee Memorandum for any ticker with a specified recommendation (BUY/HOLD/SELL) and conviction level. Used for practice writing institutional-quality investment memos.

Phone notifications use [ntfy.sh](https://ntfy.sh) — a free, open-source push notification service requiring no account setup beyond subscribing to a topic.

---

## Key Technical Decisions

**Parallel execution everywhere** — The five analysis modules (competitive, analyst coverage, earnings, SEC, insider) all run simultaneously using `ThreadPoolExecutor(max_workers=5)`. FMP API calls also fire in parallel. This cuts total runtime by ~60% versus sequential execution. The tradeoff: errors in one thread must not crash others, so every module returns `{"error": "reason"}` on failure rather than raising.

**Token budget management** — The Claude payload is capped at ≤900 tokens. This required a deliberate encoding strategy: all financial data is JSON-encoded with abbreviated keys (`"mktCap"` not `"market_cap"`, `"gm"` not `"gross_margin"`), dollar values are formatted strings not raw floats, and redundant fields that Claude can compute from others are omitted. The 14-section output structure is enforced by the prompt, not post-processing.

**SEC EDGAR without a library** — The EDGAR API is a free government service with no key requirement, but it requires a specific `User-Agent` header and has a 10 req/s rate limit. Rather than using a third-party wrapper (which may break or add dependencies), this tool calls the raw REST endpoints directly: CIK lookup → submissions JSON → filing index → HTML extraction. Rate pacing at 150ms between requests keeps usage well under limits.

**Model-specific data fetchers** — The LBO and M&A models import from `lbo/lbo_fetcher.py` rather than duplicating fetch logic. The M&A fetcher wraps the LBO fetcher and adds M&A-specific fields (EPS, P/E, book equity, analyst target). This prevents drift between what the models see and what the main pipeline sees. The rule is strict: never rewrite data fetching, always import it.

**Goodwill as balance sheet plug** — In the LBO model, goodwill is not calculated from purchase price minus book value (which ignores transaction fees and creates BS imbalance). Instead it is computed as: `equity + debt + AP − cash − AR/inventory − PP&E`. This guarantees the opening balance sheet balances to zero on Day 1, regardless of the assumed capital structure.

**Graceful degradation, always** — Every module returns a result dict with an `"error"` key rather than raising exceptions. Excel sheets render an error message card when a module fails; the PDF and pitch deck omit the affected section with a note. This means a broken FMP API key or a company not in EDGAR doesn't kill the entire run — it produces partial output with clear labels on what failed and why.

**Three Sonnet calls for the education layer** — The education content (30 Excel cell comments, 12 slide notes, 12-section PDF guide, 40-term glossary) is generated in exactly 3 API calls, not one per feature. Each call returns structured JSON or text covering an entire category. This limits cost to ~$0.05 per education run while still producing contextually specific content (each comment references the company's actual metrics, not generic definitions).

---

## Getting Started

### Prerequisites

- Python 3.9 or newer
- Git

### API Keys Required

| Key | Where to get it | Free tier |
|-----|-----------------|-----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | $5 credit on signup |
| `FMP_API_KEY` | [financialmodelingprep.com](https://financialmodelingprep.com) | 250 calls/day free |
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) | 100 calls/day free |

SEC EDGAR and yfinance require no API key.

### Installation

```bash
# Clone the repository
git clone https://github.com/maddinsd/portfolio-analyzer.git
cd portfolio-analyzer

# Install dependencies
pip install -r requirements.txt

# Create your environment file
cp .env.example .env   # then fill in your keys
```

### Environment Setup

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
FMP_API_KEY=your_fmp_key_here
NEWS_API_KEY=your_newsapi_key_here
```

This file is in `.gitignore` and will never be committed.

### First Run

```bash
# Free dry run — fetches all data, skips Claude API call
python3 main.py AAPL --dry-run

# Full analysis (uses ~$0.02 in Claude API credits)
python3 main.py AAPL

# Complete package: Excel + PDF + pitch deck
python3 main.py AAPL --full

# Standalone LBO model (no Claude required)
python3 lbo/lbo_model.py AAPL --entry-multiple 8 --hold-years 5

# Merger consequences model (no Claude required)
python3 ma/ma_model.py MSFT AAPL --premium 30 --cash-pct 60
```

Outputs are saved to `reports/AAPL/` with timestamped filenames. `AAPL_latest.xlsx` always points to the most recent run.

### Running the Automation Layer

```bash
# Morning briefing (run manually to test; normally scheduled 7am ET)
python3 automation/morning_briefing.py

# On-demand IC memo
python3 automation/ic_memo.py AAPL --recommendation BUY --conviction HIGH
```

See [docs/AUTOMATION.md](docs/AUTOMATION.md) for scheduling and phone notification setup.

---

## About

Built by **Samuel Madding**, University of Cincinnati — Carl H. Lindner College of Business.

Developed as a demonstration of applied AI and financial modeling skills targeting equity research roles. Every financial model follows institutional methodology — the DCF uses CFA-standard WACC construction, the LBO model uses a two-pass debt schedule with excess cash sweep, and the M&A model follows standard Purchase Price Allocation accounting.

Built entirely from scratch using Claude Code.

---

*For detailed documentation: [docs/OUTPUTS.md](docs/OUTPUTS.md) · [docs/METHODOLOGY.md](docs/METHODOLOGY.md) · [docs/AUTOMATION.md](docs/AUTOMATION.md) · [CHANGELOG.md](CHANGELOG.md)*
