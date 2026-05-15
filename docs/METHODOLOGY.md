# Financial Methodology

How the models work — assumptions, formulas, and design decisions.

---

## DCF Model

**File:** `dcf.py`

### WACC Construction

Follows CFA Institute curriculum methodology.

```
Cost of Equity (CAPM) = Rf + β × ERP
WACC = (E/V) × Ke + (D/V) × Kd × (1 − tax rate)
```

| Input | Value | Source |
|-------|-------|--------|
| Risk-free rate (Rf) | 4.5% | Current 10-year Treasury yield |
| Equity risk premium (ERP) | 5.5% | Damodaran historical average |
| Beta (β) | Live | yfinance (5-year monthly regression vs S&P 500) |
| Cost of debt (Kd) | Estimated from interest expense / total debt | Balance sheet |
| Tax rate | Effective rate from income statement | FMP |
| Debt weight (D/V) | Total debt / (market cap + total debt) | Calculated at runtime |

Beta floor: 0.5 (applied to prevent nonsensical WACC for very low-beta companies). Beta ceiling: none — very high-beta companies will produce WACC > 20%, which triggers a halt.

**Halt conditions** (DCF returns `{"error": "..."}` rather than producing a result):
- WACC > 20% — indicates distressed company or data error
- Terminal growth ≥ WACC — produces mathematically negative enterprise value

### Two-Stage FCF Projection

**Stage 1** — Years 1–5: Explicit free cash flow forecast

Revenue growth decays from the historical 3-year CAGR toward a long-run rate over the forecast period. Operating margin held at trailing 3-year average. FCF = EBIT × (1 − tax rate) + D&A − capex − ΔNWC.

**Stage 2** — Terminal value (Gordon Growth Model):

```
TV = FCF_Year5 × (1 + g) / (WACC − g)
```

Terminal growth rate (g): 2.5% default (slightly above long-run nominal GDP growth of ~2%).

### Sensitivity Table

5×5 grid. Rows: WACC from (base − 2%) to (base + 2%) in 0.5% steps. Columns: terminal growth rate from 1.5% to 3.5% in 0.5% steps. Center cell = base case. Color-coded: green > 20% upside, yellow 0–20%, red = downside.

---

## Comparable Company Analysis

**File:** `competitive.py`

### Peer Identification

1. **Primary**: yfinance `Sector` and `Industry` fields for the subject company. Query all tickers in the same industry, filter to market cap within 0.1× to 10× of the subject.
2. **Fallback**: If yfinance returns 0 peers (common for non-US companies), FMP `/search-name` endpoint with the company name. FMP `/profile` fills in data when yfinance returns empty info for a peer.

Peer count target: 3–5 companies. Never includes the subject company itself.

### Benchmarking Metrics

| Metric | Formula |
|--------|---------|
| Revenue growth | YoY % change, trailing annual |
| Gross margin | Gross profit / Revenue |
| Operating margin | Operating income / Revenue |
| ROE | Net income / Book equity |
| Forward P/E | Current price / Next-year EPS estimate |

### Tercile Ranking

Each metric ranked relative to the full peer distribution (subject + peers). Top tercile = top 33%, mid tercile = middle 33%, bottom tercile = bottom 33%. Used to identify where the company stands relative to its competitive set, not relative to the market.

### P/E Premium/Discount

```
Premium = (Subject Forward P/E − Peer Median Forward P/E) / Peer Median Forward P/E
```

Expressed as a percentage. Positive = subject trades at a premium to peers.

---

## Analyst Coverage

**File:** `analyst_coverage.py`

### Consensus Rating

FMP `/analyst-stock-recommendations` returns monthly Buy/Hold/Sell counts from sell-side firms. Consensus label:

```
Bull ratio = Buy / (Buy + Hold + Sell)
> 0.60 → Strong Buy
0.45–0.60 → Buy
0.30–0.45 → Hold
< 0.30 → Sell / Underperform
```

### Price Targets

FMP `/price-target` returns individual analyst targets with dates. Mean, high, and low calculated from the 10 most recent targets. Upside = (mean target − current price) / current price. Fallback to yfinance `targetMeanPrice` if FMP returns nothing.

### EPS Estimates

FMP `/analyst-estimates` returns quarterly consensus EPS and revenue estimates for the next 2 quarters. Displayed alongside historical actuals for context.

---

## Earnings Beat/Miss History

**File:** `transcript_parser.py`

### Data Sources

- **EPS**: yfinance `earnings_dates` — provides reported vs estimated EPS for the last 8 quarters. Beat defined as reported > estimated (after adjusting for GAAP vs adjusted where possible).
- **Revenue**: FMP `income-statement` (limit=5, period=quarter) — quarterly revenue actuals for context.

### Tone Score

Algorithmic sentiment analysis of guidance language. Applied to FMP quarterly income statement description fields and any available press release text. Score range: −1.0 (strongly bearish language) to +1.0 (strongly bullish). Based on a keyword dictionary of bullish/bearish financial guidance phrases.

Label mapping: > 0.2 → Positive, −0.2 to 0.2 → Neutral, < −0.2 → Negative.

This is a heuristic, not a true NLP model. It flags strong language but cannot interpret nuance.

---

## SEC EDGAR Analysis

**File:** `sec_parser.py`

### API Approach

Direct REST API calls to EDGAR — no third-party library. Required header: `User-Agent: SamuelMadding/1.0 sdmadding@icloud.com` (per SEC terms of service). Rate pacing: 150ms between requests (EDGAR limit: 10 req/second).

### Filing Extraction Pipeline

1. CIK lookup: `https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK={ticker}&...` or bulk `company_tickers.json`
2. Submissions: `https://data.sec.gov/submissions/CIK{10-digit-zero-padded}.json`
3. Latest 10-K filing index URL from submissions JSON
4. HTML filing: full 10-K HTML fetched and parsed with BeautifulSoup

### Item Extraction

- **Item 1 (Business)**: First 200 words after "Item 1" header. Describes what the company does.
- **Item 1A (Risk Factors)**: Top 5 risks by paragraph length. Length correlates with management's perceived severity — they write more about risks they consider material.
- **Item 7 (MD&A)**: First 300 words after "Item 7" or "Management's Discussion" header. Tone signals extracted from this section.

### MD&A Tone Signals

Pattern matching for bearish signals (e.g., "uncertainty", "headwinds", "inflationary pressure", "challenging") and bullish signals (e.g., "momentum", "strong demand", "expanding margins", "record"). Returned as separate lists — not aggregated into a single score, to preserve nuance.

No Claude API calls in this module — all algorithmic.

---

## Insider Transaction Analysis

**File:** `insider_tracker.py`

### Data Sources

EDGAR Form 4 XML files. URL pattern: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&...`

### Transaction Code Filter

| Code | Description | Include? |
|------|-------------|---------|
| P | Open-market purchase | ✅ Yes |
| S | Open-market sale | ✅ Yes |
| A | Grant/award | ❌ No |
| M | Option exercise | ❌ No |
| F | Tax withholding | ❌ No |
| G | Gift | ❌ No |
| D | Disposition to issuer | ❌ No |

10b5-1 plan transactions (`aff10b5One` XML field = 1) are excluded from conviction scoring. Pre-planned sales are less informative signals than discretionary selling.

### Conviction Score

Base score: 5.0

| Signal | Adjustment |
|--------|-----------|
| CEO open-market buy | +2.0 |
| CFO open-market buy | +1.5 |
| Director buy | +0.5 per director |
| Cluster buy (3+ insiders same month) | +1.0 |
| CEO discretionary sell | −1.5 |
| Multiple directors selling same month | −1.0 |
| Large sell (> $1M, non-10b5-1) | −0.5 |

Score clipped to [1.0, 10.0].

Label mapping: ≥ 7.0 → Strong Buy Signal, 5.5–7.0 → Bullish, 4.0–5.5 → Neutral, ≤ 4.0 → Bearish.

---

## Claude Analysis

**File:** `reporter.py`

### Payload Construction

All financial data is JSON-encoded with abbreviated keys to minimize token consumption. Target: ≤ 900 tokens input. Key abbreviations:

| Field | Key |
|-------|-----|
| market_cap | mktCap |
| gross_margin | gm |
| enterprise_value | ev |
| price_to_earnings | pe |

Dollar values formatted as strings ("$148.3B") rather than raw floats. Fields computable from others are omitted (e.g., `rel` — relative performance, computable from price history).

### 14-Section Analysis Structure

Defined in `ANALYSIS_STRUCTURE` constant. Claude is instructed to return exactly these 14 sections in order:

1. Investment Thesis
2. Valuation Analysis
3. Financial Health
4. Competitive Position
5. Growth Drivers
6. Risk Factors
7. Analyst Consensus
8. Insider Activity
9. Earnings Quality
10. SEC Filings
11. News Sentiment
12. Technical Signals
13. Bull vs Bear
14. Recommendation

MAX_TOKENS: 4096. Never lower — truncation breaks the section structure.

### Three Parallel Research Agents

**File:** `research.py` — runs simultaneously with the main Claude call

Each agent is a separate API call (claude-sonnet-4-6, max_tokens=1000):

1. **Investment Thesis Agent** — deep-dive thesis with specific catalysts and time horizon
2. **Comps Analysis Agent** — qualitative peer comparison with sector dynamics
3. **Earnings Preview Agent** — forward-looking earnings setup with estimate revision analysis

All three fire in parallel via `ThreadPoolExecutor`. Each returns `_placeholder(kind, error)` on failure — never raises. Results populate Sheets 10, 11, 12.

---

## LBO Model

**File:** `lbo/lbo_engine.py`

### Transaction Structure

Default capital structure (adjustable via CLI):
- Sponsor equity: 40%
- Term Loan B: 35%
- Senior Notes: 15%
- Subordinated Debt: 10%

Entry multiple: user-specified (e.g., 8×) applied to trailing EBITDA. Transaction fees: 2% of enterprise value.

### Debt Schedule — Two-Pass Algorithm

**Pass 1**: Build scheduled amortization for each tranche. TLB: 1%/year. Senior Notes: bullet. Sub Debt: bullet.

**Pass 2**: Compute excess FCF after all scheduled payments. Apply excess cash sweep to debt in priority order (TLB first). Ensures no tranche balance goes negative.

### Goodwill as Balance Sheet Plug

Rather than calculating goodwill as (purchase price − book value), goodwill is computed as:

```
Goodwill = Equity + Debt + AP − Cash − (AR + Inventory) − PP&E
```

This guarantees the opening balance sheet balances to zero on Day 1, regardless of the assumed capital structure. Book value math ignores transaction fees and creates imbalance; the plug approach is conservative and common in practice.

### IRR Calculation

Newton-Raphson iteration on the IRR definition:

```
NPV(r) = Σ [CF_t / (1+r)^t] = 0
```

Solves iteratively from an initial guess of 20%. Maximum 1000 iterations. No numpy-financial dependency.

### Sensitivity Tables

Two 5×5 tables:
1. IRR vs entry multiple × exit multiple
2. MOIC vs entry multiple × debt ratio

Center cell = base case. Center cell IRR/MOIC must equal the model's actual IRR/MOIC — this is the proof the table is wired correctly.

---

## M&A Merger Consequences Model

**File:** `ma/ma_engine.py`

### Consideration Mix

Cash/stock split specified by user (`--cash-pct`). New shares issued = (stock consideration) / (acquirer current price). Exchange ratio = new shares / target shares outstanding.

### Purchase Price Allocation

Per GAAP ASC 805:
- 30% of acquisition premium allocated to intangible assets (customer relationships, technology, brand)
- 70% to goodwill
- Intangibles amortized straight-line over 10 years (creates D&A step-up reducing GAAP EPS)

### EPS Analysis — Two Metrics

**GAAP EPS** = Pro forma net income (after PPA amortization) / pro forma shares outstanding

**Cash EPS** = (Pro forma net income + intangible amortization) / pro forma shares outstanding

Cash EPS is the metric acquirers typically cite in deal rationale. GAAP EPS is what GAAP earnings reports will show.

### Synergy Model

Three categories with independent ramp:
- Revenue synergies (cross-sell, pricing): 50%/75%/100% of target in Years 1/2/3
- COGS synergies (procurement, manufacturing): same ramp
- SG&A synergies (headcount, facilities): same ramp

NPV of synergies discounted at 8%.

### Break-Even Premium

Binary search finds the acquisition premium at which Year 1 GAAP EPS accretion/dilution = 0. Convergence tolerance: 0.01%.

### Sensitivity Table

5×5: accretion/dilution (Year 1, GAAP EPS) vs offer premium (base ± 10pp in 5pp steps) × synergy realization (50% to 150% of base in 25pp steps). Center cell = base assumptions. Green = accretive, red = dilutive.
