from __future__ import annotations

import os
from datetime import date, datetime

import requests
import yfinance as yf

_FMP_BASE = "https://financialmodelingprep.com/stable"


def _fmp_get(endpoint: str, params: dict) -> list | dict | None:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            f"{_FMP_BASE}/{endpoint}",
            params={**params, "apikey": key},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _tone_label(score: float) -> str:
    if score >= 0.6:
        return "Very Positive"
    if score >= 0.2:
        return "Positive"
    if score >= -0.2:
        return "Neutral"
    if score >= -0.6:
        return "Negative"
    return "Very Negative"


def _compute_tone(history: list, beat_streak: int) -> float:
    """Algorithmic tone -1.0 to +1.0. No API calls.
    Weighted average of EPS surprise magnitude, beat streak, and revenue growth trend.
    """
    if not history:
        return 0.0

    recent = history[:4]
    surprises = [q["eps_surprise"] for q in recent if q.get("eps_surprise") is not None]
    if not surprises:
        return 0.0

    avg_surp = sum(surprises) / len(surprises)
    # +20% avg surprise → +1.0; -20% → -1.0
    surprise_score = max(-1.0, min(1.0, avg_surp / 20.0))

    # Beat streak: each consecutive beat adds 0.1, capped at 0.4
    streak_bonus = min(0.4, beat_streak * 0.1) if beat_streak > 0 else 0.0

    # Revenue growth component: ±20% avg growth → ±0.3
    rev_growths = [q["rev_growth"] for q in recent if q.get("rev_growth") is not None]
    rev_score = 0.0
    if rev_growths:
        avg_rev = sum(rev_growths) / len(rev_growths)
        rev_score = max(-0.3, min(0.3, avg_rev / 20.0))

    raw = surprise_score + streak_bonus + rev_score
    return round(max(-1.0, min(1.0, raw)), 3)


def _guidance_signals(history: list, tone_score: float, beat_streak: int) -> list[str]:
    signals: list[str] = []

    if beat_streak >= 6:
        signals.append(f"Exceptional execution: {beat_streak} consecutive EPS beats")
    elif beat_streak >= 4:
        signals.append(f"Consistent execution: {beat_streak} consecutive EPS beats")
    elif beat_streak >= 2:
        signals.append(f"Recent momentum: {beat_streak} consecutive EPS beats")

    if history:
        recent_surps = [q["eps_surprise"] for q in history[:4]
                        if q.get("eps_surprise") is not None]
        if recent_surps:
            avg = sum(recent_surps) / len(recent_surps)
            if avg > 5:
                signals.append(
                    f"Street systematically underestimates: avg +{avg:.1f}% EPS surprise "
                    f"over last {len(recent_surps)} quarters"
                )
            elif avg < -3:
                signals.append(
                    f"Earnings misses: avg {avg:.1f}% EPS surprise "
                    f"over last {len(recent_surps)} quarters"
                )

        rev_growths = [q["rev_growth"] for q in history[:4]
                       if q.get("rev_growth") is not None]
        if rev_growths:
            avg_rev = sum(rev_growths) / len(rev_growths)
            if avg_rev > 10:
                signals.append(f"Strong revenue acceleration: avg +{avg_rev:.1f}% YoY")
            elif avg_rev > 0:
                signals.append(f"Modest revenue growth: avg +{avg_rev:.1f}% YoY")
            else:
                signals.append(f"Revenue under pressure: avg {avg_rev:.1f}% YoY")

    if tone_score >= 0.6:
        signals.append("Earnings quality: strongly positive trend across recent quarters")
    elif tone_score <= -0.4:
        signals.append("Earnings quality: deteriorating trend warrants monitoring")

    return signals[:4]


def run_transcript_parser(ticker: str, stats: dict, fin_data: dict) -> dict:
    """Fetch earnings beat/miss history and compute algorithmic tone score.

    Data sources:
    - yfinance earnings_dates: EPS estimate, actual, surprise% (8 quarters)
    - FMP income-statement quarterly (limit=5): revenue actuals for YoY growth

    No Claude API calls — all signals derived algorithmically.
    Returns {"error": "reason"} on failure, never raises.
    """
    try:
        return _run(ticker, stats, fin_data)
    except Exception as exc:
        return {"error": str(exc)}


def _run(ticker: str, stats: dict, fin_data: dict) -> dict:
    # ── 1. EPS beat/miss from yfinance earnings_dates ─────────────────────────
    tk = yf.Ticker(ticker)
    ed = getattr(tk, "earnings_dates", None)

    beat_miss: list[dict] = []
    next_earnings_date: str | None = None
    today = date.today()

    if ed is not None and not ed.empty:
        for idx, row in ed.iterrows():
            try:
                dt = idx.date() if hasattr(idx, "date") else idx
            except Exception:
                continue

            if dt > today:
                dt_str = dt.strftime("%Y-%m-%d")
                if next_earnings_date is None or dt_str < next_earnings_date:
                    next_earnings_date = dt_str
                continue

            eps_est = row.get("EPS Estimate")
            eps_act = row.get("Reported EPS")
            surp    = row.get("Surprise(%)")

            if eps_est is None and eps_act is None:
                continue

            try:
                eps_est_f = float(eps_est) if eps_est is not None else None
                eps_act_f = float(eps_act) if eps_act is not None else None
                surp_f    = float(surp)    if surp    is not None else None
            except (TypeError, ValueError):
                continue

            if (surp_f is None and eps_est_f is not None
                    and eps_act_f is not None and eps_est_f != 0):
                surp_f = (eps_act_f - eps_est_f) / abs(eps_est_f) * 100

            if surp_f is not None:
                beat = surp_f >= 0
            elif eps_est_f is not None and eps_act_f is not None:
                beat = eps_act_f >= eps_est_f
            else:
                beat = None

            beat_miss.append({
                "date":         dt.strftime("%Y-%m-%d"),
                "eps_est":      eps_est_f,
                "eps_actual":   eps_act_f,
                "eps_surprise": round(surp_f, 2) if surp_f is not None else None,
                "beat":         beat,
                "rev_actual":   None,
                "rev_growth":   None,
            })

            if len(beat_miss) >= 8:
                break

    # ── 2. Revenue actuals from FMP income-statement (quarterly, limit≤5) ─────
    fmp_records = _fmp_get("income-statement",
                           {"symbol": ticker, "period": "quarter", "limit": 8})

    rev_by_date: dict[str, tuple] = {}
    if fmp_records and isinstance(fmp_records, list):
        fmp_sorted = sorted(fmp_records, key=lambda r: r.get("date", ""), reverse=True)
        for i, rec in enumerate(fmp_sorted):
            rec_date = (rec.get("date") or "")[:10]
            if not rec_date:
                continue
            rev_raw = rec.get("revenue")
            rev_m   = float(rev_raw) / 1e6 if rev_raw is not None else None
            rev_yoy = None
            if i + 4 < len(fmp_sorted):
                prev = fmp_sorted[i + 4].get("revenue")
                if prev and float(prev) != 0 and rev_raw is not None:
                    rev_yoy = (float(rev_raw) - float(prev)) / abs(float(prev)) * 100
            rev_by_date[rec_date] = (rev_m, rev_yoy)

    # yfinance fallback when FMP returns no quarterly revenue records
    if not rev_by_date:
        try:
            qf = getattr(tk, "quarterly_income_stmt", None)
            if qf is None or (hasattr(qf, "empty") and qf.empty):
                qf = getattr(tk, "quarterly_financials", None)
            if qf is not None and not (hasattr(qf, "empty") and qf.empty):
                rev_row = None
                for label in ("Total Revenue", "Revenue", "TotalRevenue"):
                    if label in qf.index:
                        rev_row = qf.loc[label]
                        break
                if rev_row is not None:
                    cols = sorted(rev_row.index, reverse=True)
                    for i, col in enumerate(cols):
                        try:
                            val = float(rev_row[col])
                        except (TypeError, ValueError):
                            continue
                        rev_m = val / 1e6
                        rev_yoy = None
                        if i + 4 < len(cols):
                            try:
                                prev_val = float(rev_row[cols[i + 4]])
                                if prev_val != 0:
                                    rev_yoy = (val - prev_val) / abs(prev_val) * 100
                            except (TypeError, ValueError):
                                pass
                        rec_date = (col.strftime("%Y-%m-%d")
                                    if hasattr(col, "strftime") else str(col)[:10])
                        rev_by_date[rec_date] = (rev_m, rev_yoy)
        except Exception:
            pass

    # Match revenue to beat/miss rows by nearest date (±60 days)
    for bm in beat_miss:
        bm_dt = datetime.strptime(bm["date"], "%Y-%m-%d").date()
        best_key, best_delta = None, 999
        for rec_date in rev_by_date:
            try:
                delta = abs((bm_dt - datetime.strptime(rec_date, "%Y-%m-%d").date()).days)
                if delta < best_delta:
                    best_delta, best_key = delta, rec_date
            except ValueError:
                continue
        if best_key and best_delta <= 60:
            bm["rev_actual"], bm["rev_growth"] = rev_by_date[best_key]

    # ── 3. Streaks and tone ────────────────────────────────────────────────────
    beat_streak = 0
    miss_streak = 0
    beat_count  = sum(1 for bm in beat_miss if bm.get("beat") is True)

    for bm in beat_miss:
        if bm.get("beat") is True:
            beat_streak += 1
        else:
            break

    for bm in beat_miss:
        if bm.get("beat") is False:
            miss_streak += 1
        else:
            break

    tone_score   = _compute_tone(beat_miss, beat_streak)
    tone_lbl     = _tone_label(tone_score)
    guidance     = _guidance_signals(beat_miss, tone_score, beat_streak)
    last_surprise = beat_miss[0]["eps_surprise"] if beat_miss else None
    last_rev      = beat_miss[0]["rev_actual"]   if beat_miss else None

    return {
        "error":             None,
        "beat_miss_history": beat_miss,
        "beat_streak":       beat_streak,
        "miss_streak":       miss_streak,
        "beat_count":        beat_count,
        "total_quarters":    len(beat_miss),
        "tone_score":        tone_score,
        "tone_label":        tone_lbl,
        "guidance_signals":  guidance,
        "next_earnings_date": next_earnings_date,
        "last_eps_surprise": last_surprise,
        "last_rev_actual":   last_rev,
    }
