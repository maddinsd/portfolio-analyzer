# Lindner Research Platform

An AI-powered equity research platform that turns a single ticker symbol into a complete institutional-quality research package — 17-sheet financial model, 12-slide pitch deck, 10-page research PDF, and standalone LBO/M&A models — in under 30 seconds.

---

## Live Demo

**[https://web-chi-ten-48.vercel.app](https://web-chi-ten-48.vercel.app)**

Run any public company ticker and get a complete institutional research package directly in the browser. No installation required.

---

## Features

- **Equity Research Report** — 14-section Claude-generated analysis (investment thesis, valuation, risks, comps, and more) exported as a 10-page Goldman-style PDF
- **17-Sheet Excel Workbook** — Snapshot, income statement, balance sheet, cash flow, DCF model, comparable companies, competitive analysis, analyst coverage, earnings history, SEC filings, and insider transactions
- **12-Slide Pitch Deck** — PowerPoint with rating card, DCF bridge, football field valuation, and comps table
- **DCF Model** — Two-stage discounted cash flow with CAPM-based WACC, 5-year explicit forecast, terminal value, and 5×5 sensitivity table
- **LBO Model** — 9-tab leveraged buyout model with two-pass debt schedule, integrated 3-statement model, Newton-Raphson IRR, and 5×5 sensitivity tables
- **M&A Merger Model** — 8-tab accretion/dilution model with GAAP and Cash EPS, synergy ramp, purchase price allocation, break-even analysis, and sensitivity tables
- **SEC EDGAR Parser** — Algorithmic extraction of 10-K risk factors, MD&A tone, and business overview with no API key required
- **Insider Transaction Tracker** — Form 4 buy/sell signals scored by executive role, cluster activity, and conviction level
- **Earnings History** — 8-quarter beat/miss streak, revenue surprise tracking, and algorithmic tone scoring
- **Education Layer** — Excel cell comments, PowerPoint speaker notes, and a 12-page companion PDF with 40-term glossary generated in 3 parallel Sonnet calls
- **Real-Time Web Streaming** — Server-Sent Events stream pipeline progress to the browser as each stage completes
- **Automation Layer** — Scheduled morning briefings, price alert monitor, earnings calendar, and on-demand IC memo generator with push notifications

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI | Anthropic Claude API (Sonnet 4.6 for analysis, Haiku 4.5 for classification) |
| Data | yfinance, Financial Modeling Prep (FMP), SEC EDGAR, NewsAPI |
| Backend | Python 3.9, Flask, Server-Sent Events |
| Frontend | React 18, Tailwind CSS |
| Excel | openpyxl |
| PDF | ReportLab 4.x + matplotlib |
| PowerPoint | python-pptx 1.0.x |
| Deployment | Vercel |
| Notifications | ntfy.sh |

---

## Screenshots

> _Screenshots coming soon_

| Page | Description |
|---|---|
| Dashboard | Live watchlist with prices and prior analysis status |
| Analysis | Real-time streaming progress with download links |
| LBO Calculator | Entry multiple, hold period, and debt ratio inputs with live MOIC/IRR preview |
| M&A Deal Builder | Acquirer/target pair, offer premium, cash/stock mix, and synergy override |
| History | Browse and download all prior analysis runs |

---

## Getting Started

### Prerequisites

- Python 3.9+
- Git

### API Keys

| Key | Source | Free tier |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | $5 credit on signup |
| `FMP_API_KEY` | [financialmodelingprep.com](https://financialmodelingprep.com) | 250 calls/day |
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) | 100 calls/day |

SEC EDGAR and yfinance require no API key.

### Installation

```bash
git clone https://github.com/maddinsd/portfolio-analyzer.git
cd portfolio-analyzer
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

### Usage

```bash
# Dry run — no API cost, verifies data fetch
python3 main.py AAPL --dry-run

# Full analysis (~$0.02 in Claude credits)
python3 main.py AAPL

# Complete package: Excel + PDF + pitch deck
python3 main.py AAPL --full

# With education guide (~$0.05 additional)
python3 main.py AAPL --full --education --audience student

# Standalone LBO model
python3 lbo/lbo_model.py AAPL --entry-multiple 8 --hold-years 5

# M&A merger model
python3 ma/ma_model.py MSFT AAPL --premium 30 --cash-pct 60

# Run the web interface locally
cd web && flask run --port 5001
```

---

## Built By

**Sam Madding**  
University of Cincinnati — Carl H. Lindner College of Business

---

> **Disclaimer:** This project is an independent academic and personal portfolio project. It is not affiliated with, endorsed by, or produced in partnership with the University of Cincinnati or the Carl H. Lindner College of Business.
