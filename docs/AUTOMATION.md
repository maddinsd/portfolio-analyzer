# Automation Layer

Four scheduled tools that run automatically via Claude Code routines in Anthropic's cloud. Each can also be run manually for testing.

---

## Overview

| Tool | Schedule | Output | Manual Run |
|------|---------|--------|-----------|
| Morning Briefing | 7am ET weekdays | `automation/briefings/` | `python3 automation/morning_briefing.py` |
| Market Alert Monitor | Hourly 9am–4pm ET | Phone notification | `python3 automation/notification_tool.py` |
| Earnings Calendar | Daily weekdays | `automation/calendars/` | `python3 automation/earnings_calendar.py` |
| IC Memo Generator | On-demand | `automation/ic_memos/` | `python3 automation/ic_memo.py AAPL --recommendation BUY` |

All tools share `automation/common.py` for common utilities: quote fetching, notification sending, headline retrieval.

---

## Phone Notifications (ntfy.sh)

Notifications use [ntfy.sh](https://ntfy.sh) — a free, open-source push notification service. No account required beyond subscribing to a topic on your phone.

### Setup (one-time)

1. Install the ntfy app on your phone (iOS or Android)
2. Subscribe to topic: `sam-madding-finance-alerts`
3. That's it — notifications fire automatically when alerts trigger

The topic name is hardcoded in `automation/common.py`:
```python
_NTFY_TOPIC = "sam-madding-finance-alerts"
```

To use a different topic, update this constant and re-subscribe in the app.

### Testing Notifications

```bash
python3 -c "from automation.common import notify; notify('Test', 'Notification working')"
```

---

## Watchlist Configuration

**File:** `automation/watchlist.json`

The watchlist controls which tickers the morning briefing and alert monitor track.

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
  "alerts": {
    "AAPL": {"price_above": 220.00, "price_below": 180.00, "move_pct": 3.0},
    "NVDA": {"price_above": 150.00, "price_below": 100.00, "move_pct": 5.0}
  }
}
```

**Fields:**
- `tickers` — list of tickers to include in morning briefing and earnings calendar
- `alerts` — per-ticker price alerts (optional for each ticker)
  - `price_above` — notify when price crosses above this level
  - `price_below` — notify when price crosses below this level
  - `move_pct` — notify when intraday move exceeds this percentage

To add a ticker to the watchlist, add it to the `tickers` array. To add price alerts, add an entry to the `alerts` object.

---

## Morning Briefing

**File:** `automation/morning_briefing.py`

**Schedule:** `0 11 * * 1-5` (7am ET = 11am UTC, weekdays only)

### What It Does

1. Fetches overnight price moves for all watchlist tickers
2. Identifies tickers with significant moves (> 1% default threshold)
3. Generates a Claude-written briefing for each significant mover
4. Saves briefing to `automation/briefings/YYYYMMDD_morning_briefing.md`
5. Sends a push notification with the summary

### Briefing Format

Each briefing includes:
- Price change and % move
- Latest 3 headlines explaining the move
- 2–3 sentence Claude commentary on what it means for the position
- Market context (sector performance, index moves)

### Manual Run

```bash
python3 automation/morning_briefing.py
```

Briefings saved to `automation/briefings/`. View the latest:
```bash
cat automation/briefings/$(ls automation/briefings/ | tail -1)
```

---

## Market Alert Monitor

**File:** `automation/notification_tool.py`

**Schedule:** `0 13-20 * * 1-5` (9am–4pm ET = 1pm–8pm UTC, weekdays, hourly)

### What It Does

1. Fetches live prices for all tickers with configured alerts
2. Checks each price against `price_above`, `price_below`, and `move_pct` thresholds
3. Fires a push notification when any threshold is crossed
4. Tracks fired alerts in `.alert_cache.json` to prevent re-notifying for the same event during the same day

### Alert Format

```
AAPL crossed above $220.00
Current: $221.45 (+1.2% today)
```

### Alert Caching

The cache file `.alert_cache.json` resets daily. If you want to re-test an alert without waiting until tomorrow:
```bash
rm automation/.alert_cache.json
```

### Manual Run

```bash
python3 automation/notification_tool.py
```

---

## Earnings Calendar

**File:** `automation/earnings_calendar.py`

**Schedule:** `30 11 * * 1-5` (7:30am ET = 11:30am UTC, weekdays)

### What It Does

1. Checks earnings dates for all watchlist tickers using yfinance
2. Identifies companies reporting in the next 24 hours
3. Generates a pre-earnings preview for each upcoming report
4. Saves preview to `automation/calendars/YYYYMMDD_earnings_preview.md`
5. Sends push notification 24 hours before earnings

### Preview Content

Each preview includes:
- Earnings date and time (before/after market)
- Analyst consensus EPS estimate and revenue estimate
- Last 4 quarters beat/miss history
- Key items to watch (from analyst notes)
- EPS surprise trend (3-quarter rolling average)

### Manual Run

```bash
python3 automation/earnings_calendar.py
```

Previews saved to `automation/calendars/`.

---

## IC Memo Generator

**File:** `automation/ic_memo.py`

**Type:** On-demand only (no scheduled run)

### Usage

```bash
# Basic — BUY recommendation, MEDIUM conviction
python3 automation/ic_memo.py AAPL --recommendation BUY --conviction HIGH

# With thesis
python3 automation/ic_memo.py NVDA --thesis "AI infrastructure supercycle" --recommendation BUY --conviction HIGH

# SELL recommendation
python3 automation/ic_memo.py META --recommendation SELL --conviction LOW
```

**Arguments:**
- `ticker` — required, case-insensitive
- `--recommendation` — BUY, HOLD, or SELL (default: BUY)
- `--conviction` — HIGH, MEDIUM, or LOW (default: MEDIUM)
- `--thesis` — optional one-line thesis statement

### What It Does

1. Runs the full pipeline (`main.py --full`) for the ticker
2. Reads the generated markdown report
3. Calls Claude with a structured IC memo prompt
4. Saves memo to `automation/ic_memos/TICKER_YYYYMMDD_ic_memo.md`
5. Sends push notification

### IC Memo Format

```
INVESTMENT COMMITTEE MEMORANDUM
University of Cincinnati | Lindner College of Business | [Date] | CONFIDENTIAL

RECOMMENDATION: BUY AAPL — Apple Inc.
Target Price: $XXX | Current Price: $XXX | Implied Return: XX%
Conviction: HIGH | Time Horizon: 12 months
Position Size: 4-5% of portfolio

## EXECUTIVE SUMMARY
## INVESTMENT THESIS
## VALUATION
## FINANCIAL SNAPSHOT
## RISK ASSESSMENT
## COMPETITIVE POSITION
## ANALYST COVERAGE
## INSIDER ACTIVITY
## RECOMMENDATION & POSITION SIZING

Prepared by: Samuel Madding
```

Position sizing guidance embedded in the prompt:
- HIGH conviction: 4–5% of portfolio
- MEDIUM conviction: 2–3%
- LOW conviction: 1–2%

### Runtime

~60 seconds (includes full pipeline run + one Claude API call). Uses claude-sonnet-4-6, max_tokens=1500.

---

## Scheduling — Claude Code Routines

The three scheduled tools run as remote Claude Code routines in Anthropic's cloud. They have no dependency on your local machine being on.

### Current Routines

| Routine Name | Cron | UTC |
|-------------|------|-----|
| `morning-market-briefing` | `0 11 * * 1-5` | 11am UTC = 7am ET |
| `market-alert-monitor` | `0 13-20 * * 1-5` | 1–8pm UTC = 9am–4pm ET |
| `earnings-calendar-monitor` | `30 11 * * 1-5` | 11:30am UTC = 7:30am ET |

### Viewing Routines

```bash
# In Claude Code session:
/schedule
# Select "List routines"
```

Or view at: https://claude.ai/code/routines

### Modifying a Routine

Use `/schedule` in a Claude Code session, select "Update a routine", and pick the routine to modify.

### How Routines Work

Each routine spawns an isolated remote session with a fresh checkout of the GitHub repo. The remote agent:
1. Has access to the repo code but NOT your local `.env`
2. API keys must be configured as environment variables in the routine's environment
3. Outputs (briefings, calendars) are committed back to the repo or sent as notifications

**Important**: The remote environment does not have your local API keys. If keys are not configured in the routine environment, automation tools that require them (FMP, News API, Claude API) will fail gracefully and send a failure notification.

---

## Common Utilities

**File:** `automation/common.py`

Shared functions used by all automation tools:

```python
format_large_number(n)  # 1234567890 → "$1.2B"
fmt_pct(n)              # 0.0523 → "+5.2%"
notify(title, body)     # Send push notification via ntfy.sh
get_quote(ticker)       # Fetch current price, change, % change
get_headlines(ticker)   # Fetch latest 3 headlines from NewsAPI
```

These functions are designed to fail silently — if NewsAPI is unavailable, `get_headlines()` returns an empty list rather than raising.
