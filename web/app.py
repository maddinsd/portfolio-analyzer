from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import (Flask, Response, jsonify,
                   render_template, request, send_file, send_from_directory,
                   stream_with_context)
from flask_cors import CORS

# ── Paths & environment ───────────────────────────────────────────────────────
_this_dir    = Path(__file__).parent          # web/  (also the Vercel deploy root)
PROJECT_ROOT = _this_dir.parent               # portfolio-analyzer/ (local only)
IS_VERCEL    = os.environ.get("VERCEL") == "1"

if not IS_VERCEL:
    load_dotenv(PROJECT_ROOT / ".env")

# On Vercel all pipeline .py files are copied into web/ (same dir as app.py).
# Locally they live in PROJECT_ROOT. Insert both so imports work in either env.
for _p in (str(_this_dir), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if IS_VERCEL:
    REPORTS_DIR = Path("/tmp/reports")
    LBO_OUTPUTS = Path("/tmp/lbo/outputs")
    MA_OUTPUTS  = Path("/tmp/ma/outputs")
    WATCHLIST   = Path("/tmp/watchlist.json")
else:
    REPORTS_DIR = Path.home() / "Desktop" / "reports"
    LBO_OUTPUTS = PROJECT_ROOT / "lbo" / "outputs"
    MA_OUTPUTS  = PROJECT_ROOT / "ma"  / "outputs"
    WATCHLIST   = PROJECT_ROOT / "automation" / "watchlist.json"

app = Flask(__name__)
CORS(app)

jobs: dict[str, dict] = {}

# ── JSON serialisation helper (handles numpy/pandas types) ───────────────────
def _make_json_safe(obj):
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj == float('inf') or obj == float('-inf'):
            return None
        return obj
    if isinstance(obj, int):
        return obj
    if hasattr(obj, 'item'):      # numpy scalar
        return _make_json_safe(obj.item())
    if hasattr(obj, 'tolist'):    # numpy array / pandas Series
        return _make_json_safe(obj.tolist())
    if hasattr(obj, 'to_dict'):   # pandas DataFrame
        return _make_json_safe(obj.to_dict())
    try:
        return str(obj)
    except Exception:
        return None

def _save_analysis_data(ticker_dir: Path, ticker: str, stats: dict, fin_data: dict,
                         dcf_result: dict, comp_result: dict, analyst_cov_result: dict,
                         transcript_result: dict, sec_result: dict) -> None:
    """Persist analysis results so the education endpoint can run independently."""
    payload = _make_json_safe({
        "ticker": ticker,
        "stats": stats,
        "fin_data": fin_data,
        "dcf_result": dcf_result,
        "comp_result": comp_result,
        "analyst_cov_result": analyst_cov_result,
        "transcript_result": transcript_result,
        "sec_result": sec_result,
    })
    try:
        (ticker_dir / "analysis_data.json").write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass  # non-fatal — education button will surface the error if file is missing

# ── Rate limiter (in-memory, per-IP, 10/hour) ─────────────────────────────────
_rate_store: dict[str, list] = {}
_rate_lock  = threading.Lock()

def _check_rate_limit(ip: str, limit: int = 10, window: int = 3600) -> bool:
    now = time.time()
    with _rate_lock:
        bucket = _rate_store.get(ip, [])
        bucket = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            _rate_store[ip] = bucket
            return False
        bucket.append(now)
        _rate_store[ip] = bucket
        return True

# ── Daily analysis counter ────────────────────────────────────────────────────
_counter_lock = threading.Lock()
_DAILY_LIMIT  = 20
_COUNTER_FILE = Path("/tmp/.daily_counter.json") if IS_VERCEL else (PROJECT_ROOT / ".daily_counter.json")

def _check_daily_limit() -> bool:
    """Increment today's analysis count. Returns False if limit exceeded."""
    today = date.today().isoformat()
    with _counter_lock:
        try:
            data = json.loads(_COUNTER_FILE.read_text()) if _COUNTER_FILE.exists() else {}
        except Exception:
            data = {}
        if data.get("date") != today:
            data = {"date": today, "count": 0}
        if data["count"] >= _DAILY_LIMIT:
            return False
        data["count"] += 1
        _COUNTER_FILE.write_text(json.dumps(data))
        return True

# ── Assets (project-root assets/ dir) ────────────────────────────────────────
@app.route("/assets/<path:filename>")
def serve_assets(filename):
    base = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base, "assets") if IS_VERCEL else os.path.join(base, "..", "assets")
    return send_from_directory(assets_dir, filename)

# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ── Config ────────────────────────────────────────────────────────────────────
@app.route("/api/config")
def api_config():
    return jsonify({"is_vercel": IS_VERCEL})


# ── Auth ──────────────────────────────────────────────────────────────────────
def is_admin() -> bool:
    return request.cookies.get("admin_token") == os.environ.get("ADMIN_TOKEN", "")


@app.route("/api/auth/status")
def api_auth_status():
    return jsonify({"is_admin": is_admin()})


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json() or {}
    password = data.get("password", "")
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if password == admin_token:
        resp = jsonify({"ok": True})
        resp.set_cookie(
            "admin_token",
            admin_token,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure,
        )
        return resp
    return jsonify({"error": "Incorrect password"}), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    resp = jsonify({"ok": True})
    resp.delete_cookie("admin_token")
    return resp

# ── Quote ─────────────────────────────────────────────────────────────────────
@app.route("/api/quote/<ticker>")
def api_quote(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker.upper()).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return jsonify({"valid": False, "error": "Ticker not found"}), 404
        return jsonify({
            "valid":      True,
            "ticker":     ticker.upper(),
            "name":       info.get("shortName") or info.get("longName") or ticker.upper(),
            "exchange":   info.get("exchange", ""),
            "price":      round(float(price), 2),
            "change_pct": round(float(info.get("regularMarketChangePercent", 0)), 2),
            "market_cap": info.get("marketCap"),
            "pe_fwd":     info.get("forwardPE"),
        })
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 400

# ── Analysis job ──────────────────────────────────────────────────────────────
def _analysis_thread(job_id: str, ticker: str, flags: list[str], audience: str):
    q = jobs[job_id]["queue"]

    def emit(msg: str, pct: int, detail: str = ""):
        q.put({"message": msg, "percent": pct, "detail": detail})

    try:
        from fetcher          import fetch_stock_data, fetch_news
        from analyzer         import compute_stats, compute_financials
        from dcf              import run_dcf
        from reporter         import build_report
        from excel            import build_excel
        from research         import run_research_pipeline
        from competitive      import run_competitive
        from analyst_coverage import run_analyst_coverage
        from transcript_parser import run_transcript_parser
        from sec_parser       import run_sec_parser
        from insider_tracker  import run_insider_tracker

        ticker_dir = Path(jobs[job_id]["output_dir"])
        ticker_dir.mkdir(parents=True, exist_ok=True)
        xl_path    = ticker_dir / f"01_{ticker}_Excel_Report.xlsx"
        pdf_path   = ticker_dir / f"02_{ticker}_Research_Report.pdf"
        pitch_path = ticker_dir / f"03_{ticker}_Pitch_Deck.pptx"
        edu_path   = ticker_dir / f"04_{ticker}_Education_Guide.pdf"
        md_path    = ticker_dir / f"05_{ticker}_Analysis.md"

        emit(f"Fetching {ticker} market data via FMP + yfinance…", 8, "Live quote, fundamentals, price history")
        data = fetch_stock_data(ticker)
        company_name = data["info"].get("shortName") or data["info"].get("longName") or ticker

        emit(f"Fetching news for {company_name}…", 14)
        news = fetch_news(ticker, company_name)

        emit("Computing financial statistics and ratios…", 20)
        stats    = compute_stats(data)
        fin_data = compute_financials(data)

        emit("Running DCF valuation model…", 27, "WACC · 5-year projection · terminal value")
        dcf_result = run_dcf(data, fin_data)
        dcf_str = ""
        if not dcf_result.get("error"):
            iv = dcf_result.get("valuation", {}).get("intrinsic", 0)
            dcf_str = f"Intrinsic value: ${iv:.2f}"

        emit("Spawning 3 parallel research agents (thesis · comps · earnings)…", 33, "Expected ~20s · Sonnet 4.6")
        research = run_research_pipeline(ticker, stats, fin_data)

        emit("Running 5 parallel analysis modules…", 48, "Competitive · Coverage · Earnings · SEC · Insider")
        with ThreadPoolExecutor(max_workers=5) as pool:
            fut_comp    = pool.submit(run_competitive,       ticker, stats, fin_data)
            fut_cov     = pool.submit(run_analyst_coverage,  ticker, stats, fin_data)
            fut_tr      = pool.submit(run_transcript_parser, ticker, stats, fin_data)
            fut_sec     = pool.submit(run_sec_parser,        ticker, stats, fin_data)
            fut_insider = pool.submit(run_insider_tracker,   ticker, stats, fin_data)
            comp_result        = fut_comp.result()
            analyst_cov_result = fut_cov.result()
            transcript_result  = fut_tr.result()
            sec_result         = fut_sec.result()
            insider_result     = fut_insider.result()

        # Persist analysis data so the education endpoint can run after main analysis
        _save_analysis_data(ticker_dir, ticker, stats, fin_data, dcf_result,
                            comp_result, analyst_cov_result, transcript_result, sec_result)

        emit("Generating Claude analysis (Sonnet 4.6)…", 62, "14-section structured research report")
        markdown, news_sentiment, comp_assessment, cov_assessment = build_report(
            ticker, stats, fin_data, news, dcf_result, research, comp_result,
            analyst_cov_result, transcript_result, sec_result,
            insider_result=insider_result, dry_run=False
        )
        if comp_assessment and not comp_result.get("error"):
            comp_result["claude"] = comp_assessment
        if cov_assessment and not analyst_cov_result.get("error"):
            analyst_cov_result["claude"] = cov_assessment
        md_path.write_text(markdown, encoding="utf-8")

        n_sheets = 7
        if dcf_result and not dcf_result.get("error"): n_sheets += 1
        if research:            n_sheets += 3
        if comp_result:         n_sheets += 1
        if analyst_cov_result:  n_sheets += 1
        if transcript_result:   n_sheets += 1
        if sec_result:          n_sheets += 1
        if insider_result:      n_sheets += 1

        emit(f"Building Excel workbook ({n_sheets} sheets)…", 74, "Goldman-style formatting")
        build_excel(ticker, stats, fin_data, data["price_history"], data["sp500_history"],
                    markdown, news_sentiment, dcf_result, research, comp_result,
                    analyst_cov_result, transcript_result, sec_result,
                    insider_result=insider_result, output_path=str(xl_path))

        do_pitch = "--pitch" in flags or "--full" in flags
        do_pdf   = "--pdf"   in flags or "--full" in flags
        do_edu   = ("--education" in flags or "--full" in flags) and not IS_VERCEL
        pitch_result = {"error": "not requested"}

        if do_pitch:
            from pitch import run_pitch
            emit("Building pitch deck (12 slides)…", 82)
            pitch_result = run_pitch(
                ticker, stats, fin_data,
                dcf_result=dcf_result, research=research,
                comp_result=comp_result, cov_result=analyst_cov_result,
                transcript_result=transcript_result, out_path=str(pitch_path)
            )

        if do_pdf:
            from report_pdf import run_pdf
            emit("Generating equity research PDF…", 88)
            run_pdf(ticker, stats, fin_data,
                    dcf_result=dcf_result, research=research,
                    comp_result=comp_result, cov_result=analyst_cov_result,
                    transcript_result=transcript_result, sec_result=sec_result,
                    out_path=str(pdf_path))

        if do_edu:
            from education.content_engine import run_content_engine
            from education.excel_educator import add_excel_comments
            from education.pptx_educator  import add_ppt_notes
            from education.pdf_educator   import build_companion_pdf
            emit(f"Creating education guide ({audience} audience)…", 94, "6 Sonnet calls in parallel")
            edu_content = run_content_engine(
                ticker, stats, fin_data, dcf_result, audience,
                comp_result=comp_result, cov_result=analyst_cov_result,
                transcript_result=transcript_result, sec_result=sec_result,
            )
            if not edu_content.get("error"):
                add_excel_comments(str(xl_path), edu_content["excel_comments"], audience)
                if do_pitch and not pitch_result.get("error"):
                    add_ppt_notes(str(pitch_path), edu_content["ppt_notes"])
                build_companion_pdf(ticker, edu_content, str(edu_path), audience)

        _HIDDEN = {"analysis_data.json"}
        files = sorted(f.name for f in ticker_dir.iterdir()
                       if not f.name.startswith(".") and f.name not in _HIDDEN)
        rating = analyst_cov_result.get("consensus_rating", "—") if not analyst_cov_result.get("error") else "—"
        tgt    = analyst_cov_result.get("mean_target")            if not analyst_cov_result.get("error") else None
        price  = stats.get("current_price")

        # Send push notification via ntfy.sh
        ntfy_ok = False
        try:
            import requests as _req
            info    = stats.get("info", {})
            mktcap  = info.get("marketCap")
            if mktcap and mktcap >= 1e12:
                mktcap_str = f"${mktcap/1e12:.1f}T"
            elif mktcap and mktcap >= 1e9:
                mktcap_str = f"${mktcap/1e9:.0f}B"
            elif mktcap:
                mktcap_str = f"${mktcap/1e6:.0f}M"
            else:
                mktcap_str = None

            line1 = f"{company_name} ({ticker})"
            row2  = [rating.upper() if rating not in ("—", "") else None,
                     f"Target ${tgt:,.0f}" if isinstance(tgt, (int, float)) else None,
                     f"Now ${price:,.2f}" if isinstance(price, (int, float)) else None,
                     f"MCap {mktcap_str}" if mktcap_str else None]
            line2 = " · ".join(p for p in row2 if p)

            _FILE_LABELS = [("01_", "Excel"), ("02_", "PDF"),
                            ("03_", "Pitch Deck"), ("04_", "Education Guide")]
            labels = [lbl for pfx, lbl in _FILE_LABELS
                      if any(f.startswith(pfx) for f in files)]
            line3 = ("Files: " + " · ".join(labels)) if labels else None
            line4 = f"Saved to Desktop/reports/{ticker}/" if not IS_VERCEL else None

            body_txt = "\n".join(l for l in [line1, line2, line3, line4] if l)
            ntfy_resp = _req.post(
                "https://ntfy.sh/sam-madding-finance-alerts",
                data=body_txt.encode(),
                headers={
                    "Title": f"{ticker} Analysis Complete",
                    "Priority": "default",
                    "Tags": "chart_with_upwards_trend",
                },
                timeout=10,
            )
            ntfy_ok = ntfy_resp.status_code == 200
            print(f"[ntfy] {ticker} push HTTP {ntfy_resp.status_code}: {ntfy_resp.text[:120]}", file=sys.stderr)
        except Exception as _e:
            print(f"[ntfy] {ticker} push FAILED: {_e}", file=sys.stderr)

        emit("Analysis complete!", 100)
        q.put({
            "done":    True,
            "job_id":  job_id,
            "ticker":  ticker,
            "company": company_name,
            "files":   files,
            "ntfy_ok": ntfy_ok,
            "stats": {
                "rating": rating,
                "target": f"${tgt:,.0f}" if isinstance(tgt, (int, float)) else "—",
                "price":  f"${price:,.2f}" if isinstance(price, (int, float)) else "—",
                "dcf":    dcf_str,
            }
        })

    except Exception as e:
        import traceback
        q.put({"error": str(e), "traceback": traceback.format_exc()})

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    body     = request.get_json() or {}
    ticker   = body.get("ticker", "").upper().strip()
    flags    = body.get("flags", ["--full"])
    audience = body.get("audience", "student")
    if not ticker or not ticker.replace(".", "").isalpha() or len(ticker) > 6:
        return jsonify({"error": "Invalid ticker"}), 400
    if not _check_rate_limit(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Max 10 analyses per hour."}), 429
    if not _check_daily_limit():
        return jsonify({"error": "Daily analysis limit reached. Try again tomorrow."}), 429
    job_id = str(uuid.uuid4())[:8]
    output_dir = Path(f"/tmp/jobs/{job_id}/{ticker}") if IS_VERCEL else (REPORTS_DIR / ticker)
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs[job_id] = {"queue": queue.Queue(), "output_dir": str(output_dir)}
    threading.Thread(target=_analysis_thread, args=(job_id, ticker, flags, audience), daemon=True).start()
    return jsonify({"job_id": job_id})

# ── LBO job ───────────────────────────────────────────────────────────────────
def _lbo_thread(job_id: str, ticker: str, entry_multiple, hold_years: int, debt_pct: float):
    q = jobs[job_id]["queue"]
    def emit(msg, pct, detail=""):
        q.put({"message": msg, "percent": pct, "detail": detail})
    try:
        from lbo.lbo_model import run as lbo_run
        emit(f"Fetching {ticker} market data for LBO…", 10)
        emit("Building assumptions and transaction structure…", 30)
        emit("Running 3-statement model and debt schedule…", 55)
        emit("Computing returns (IRR, MOIC) and sensitivity…", 75)
        emit("Building 9-tab Excel workbook…", 90)
        LBO_OUTPUTS.mkdir(parents=True, exist_ok=True)
        lbo_out = str(LBO_OUTPUTS / f"{ticker}_{date.today().strftime('%Y%m%d')}_lbo.xlsx") if IS_VERCEL else None
        out_path = lbo_run(
            ticker=ticker,
            entry_multiple=entry_multiple,
            hold_years=hold_years,
            debt_pct=debt_pct,
            output_path=lbo_out,
        )
        emit("LBO model complete!", 100)
        q.put({"done": True, "ticker": ticker, "file": Path(out_path).name, "output_dir": "lbo"})
    except Exception as e:
        import traceback
        q.put({"error": str(e), "traceback": traceback.format_exc()})

@app.route("/api/lbo", methods=["POST"])
def api_lbo():
    body          = request.get_json() or {}
    ticker        = body.get("ticker", "").upper().strip()
    entry_multiple = body.get("entry_multiple")
    hold_years    = int(body.get("hold_years", 5))
    debt_pct      = float(body.get("debt_pct", 0.60))
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"queue": queue.Queue()}
    threading.Thread(target=_lbo_thread, args=(job_id, ticker, entry_multiple, hold_years, debt_pct), daemon=True).start()
    return jsonify({"job_id": job_id})

# ── M&A job ───────────────────────────────────────────────────────────────────
def _ma_thread(job_id: str, acquirer: str, target: str, premium_pct: float, cash_pct: float, synergies_m):
    q = jobs[job_id]["queue"]
    def emit(msg, pct, detail=""):
        q.put({"message": msg, "percent": pct, "detail": detail})
    try:
        from ma.ma_model import run as ma_run
        emit(f"Fetching {acquirer} acquirer data…", 10)
        emit(f"Fetching {target} target data…", 22)
        emit("Building transaction structure…", 38)
        emit("Modelling synergies…", 52)
        emit("Computing EPS accretion / dilution…", 68)
        emit("Building sensitivity tables…", 82)
        emit("Writing 8-tab Excel workbook…", 92)
        MA_OUTPUTS.mkdir(parents=True, exist_ok=True)
        ma_out = str(MA_OUTPUTS / f"{acquirer}_acquires_{target}_{date.today().strftime('%Y%m%d')}.xlsx") if IS_VERCEL else None
        out_path = ma_run(
            acquirer=acquirer,
            target=target,
            premium_pct=premium_pct,
            cash_pct=cash_pct,
            synergies_m=synergies_m,
            output_path=ma_out,
        )
        emit("M&A model complete!", 100)
        q.put({"done": True, "acquirer": acquirer, "target": target,
               "file": Path(out_path).name, "output_dir": "ma"})
    except Exception as e:
        import traceback
        q.put({"error": str(e), "traceback": traceback.format_exc()})

@app.route("/api/ma", methods=["POST"])
def api_ma():
    body       = request.get_json() or {}
    acquirer   = body.get("acquirer", "").upper().strip()
    target     = body.get("target", "").upper().strip()
    premium    = float(body.get("premium_pct", 30.0))
    cash_pct   = float(body.get("cash_pct", 50.0))
    synergies  = body.get("synergies_m")
    if not acquirer or not target:
        return jsonify({"error": "acquirer and target required"}), 400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"queue": queue.Queue()}
    threading.Thread(target=_ma_thread, args=(job_id, acquirer, target, premium, cash_pct, synergies), daemon=True).start()
    return jsonify({"job_id": job_id})

# ── Education job ─────────────────────────────────────────────────────────────
def _education_thread(edu_job_id: str, analysis_job_id: str, ticker: str, audience: str):
    q = jobs[edu_job_id]["queue"]
    def emit(msg, pct, detail=""):
        q.put({"message": msg, "percent": pct, "detail": detail})
    try:
        from education.content_engine import run_content_engine
        from education.excel_educator import add_excel_comments
        from education.pptx_educator  import add_ppt_notes
        from education.pdf_educator   import build_companion_pdf

        ticker_dir = (
            Path(f"/tmp/jobs/{analysis_job_id}/{ticker.upper()}")
            if IS_VERCEL else
            REPORTS_DIR / ticker.upper()
        )
        data_file = ticker_dir / "analysis_data.json"
        if not data_file.exists():
            q.put({"error": "Analysis data not found — run analysis first."}); return

        d = json.loads(data_file.read_text(encoding="utf-8"))

        emit(f"Generating education content ({audience} audience)…", 10, "6 Sonnet calls in parallel")
        edu_content = run_content_engine(
            ticker, d["stats"], d["fin_data"], d.get("dcf_result"), audience,
            comp_result=d.get("comp_result"),
            cov_result=d.get("analyst_cov_result"),
            transcript_result=d.get("transcript_result"),
            sec_result=d.get("sec_result"),
        )
        if edu_content.get("error"):
            q.put({"error": edu_content["error"]}); return

        emit("Annotating Excel workbook…", 55)
        xl_path = ticker_dir / f"01_{ticker.upper()}_Excel_Report.xlsx"
        if xl_path.exists():
            add_excel_comments(str(xl_path), edu_content["excel_comments"], audience)

        emit("Adding speaker notes to pitch deck…", 70)
        pitch_path = ticker_dir / f"03_{ticker.upper()}_Pitch_Deck.pptx"
        if pitch_path.exists():
            add_ppt_notes(str(pitch_path), edu_content["ppt_notes"])

        emit("Building companion PDF…", 85)
        edu_filename = f"04_{ticker.upper()}_Education_Guide.pdf"
        build_companion_pdf(ticker, edu_content, str(ticker_dir / edu_filename), audience)

        emit("Education guide complete!", 100)
        q.put({"done": True, "file": edu_filename,
               "job_id": analysis_job_id, "ticker": ticker.upper()})

    except Exception as e:
        import traceback
        q.put({"error": str(e), "traceback": traceback.format_exc()})

@app.route("/api/education", methods=["POST"])
def api_education():
    """Streaming SSE endpoint for post-hoc education guide generation.

    Returns the progress stream directly from this request (no separate
    /api/progress call needed) so the thread and SSE reader share the
    same lambda instance — avoiding cross-instance state loss on Vercel.
    """
    body     = request.get_json() or {}
    ticker   = body.get("ticker", "").upper().strip()
    audience = body.get("audience", "student")
    analysis_job_id = body.get("job_id", "")
    if not ticker or not analysis_job_id:
        def _err():
            yield f"data: {json.dumps({'error': 'ticker and job_id required'})}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    edu_job_id = str(uuid.uuid4())[:8]
    edu_queue  = queue.Queue()
    jobs[edu_job_id] = {"queue": edu_queue}
    threading.Thread(
        target=_education_thread,
        args=(edu_job_id, analysis_job_id, ticker, audience),
        daemon=True,
    ).start()

    def generate():
        import time as _time
        last_hb = _time.time()
        while True:
            try:
                msg = edu_queue.get(timeout=5)
                yield f"data: {json.dumps(msg)}\n\n"
                last_hb = _time.time()
                if msg.get("done") or msg.get("error"):
                    break
            except queue.Empty:
                if _time.time() - last_hb >= 15:
                    yield 'data: {"heartbeat":true}\n\n'
                    last_hb = _time.time()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

# ── SSE progress stream ───────────────────────────────────────────────────────
@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    def generate():
        import time as _time
        job = jobs.get(job_id)
        q = job["queue"] if job else None
        if not q:
            yield f"data: {json.dumps({'error': 'job not found'})}\n\n"
            return
        last_hb = _time.time()
        while True:
            try:
                msg = q.get(timeout=5)
                yield f"data: {json.dumps(msg)}\n\n"
                last_hb = _time.time()
                if msg.get("done") or msg.get("error"):
                    break
            except queue.Empty:
                if _time.time() - last_hb >= 15:
                    yield 'data: {"heartbeat":true}\n\n'
                    last_hb = _time.time()
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

# ── Downloads ─────────────────────────────────────────────────────────────────
@app.route("/api/download/<ticker>/<filename>")
def api_download(ticker, filename):
    path = REPORTS_DIR / ticker / filename
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=filename)

@app.route("/api/download/lbo/<filename>")
def api_download_lbo(filename):
    path = LBO_OUTPUTS / filename
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=filename)

@app.route("/api/download/ma/<filename>")
def api_download_ma(filename):
    path = MA_OUTPUTS / filename
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=filename)

@app.route("/api/download/job/<job_id>/<ticker>/<filename>")
def api_download_job(job_id, ticker, filename):
    """Vercel-compatible download: reads from job-specific /tmp dir or local REPORTS_DIR."""
    if IS_VERCEL:
        path = Path(f"/tmp/jobs/{job_id}/{ticker.upper()}/{filename}")
    else:
        path = REPORTS_DIR / ticker.upper() / filename
    if not path.exists():
        return jsonify({"error": "File not found or expired"}), 404
    return send_file(str(path), as_attachment=True, download_name=filename)

# ── History ───────────────────────────────────────────────────────────────────
@app.route("/api/history")
def api_history():
    if IS_VERCEL:
        return jsonify({"vercel_mode": True, "items": []})
    results = []
    NUMBERED = ("01_", "02_", "03_", "04_", "05_")
    if REPORTS_DIR.exists():
        for ticker_dir in sorted(REPORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not ticker_dir.is_dir():
                continue
            numbered = sorted(
                f.name for f in ticker_dir.iterdir()
                if not f.name.startswith(".") and f.name[:3] in NUMBERED
            )
            if not numbered:
                continue
            mtimes = [ticker_dir.stat().st_mtime] + [
                (ticker_dir / f).stat().st_mtime for f in numbered
            ]
            rating, target = _extract_rating(ticker_dir)
            results.append({
                "ticker":    ticker_dir.name,
                "files":     numbered,
                "timestamp": max(mtimes),
                "rating":    rating,
                "target":    target,
            })
    return jsonify({"vercel_mode": False, "items": results})

# ── Watchlist ─────────────────────────────────────────────────────────────────
@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    if WATCHLIST.exists():
        return jsonify(json.loads(WATCHLIST.read_text()))
    return jsonify({"tickers": [], "thresholds": {}, "alert_types": {}})

@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_post():
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    WATCHLIST.write_text(json.dumps(data, indent=2))
    return jsonify({"ok": True})

# ── Watchlist live quotes ─────────────────────────────────────────────────────
@app.route("/api/watchlist/quotes")
def api_watchlist_quotes():
    if WATCHLIST.exists():
        wl = json.loads(WATCHLIST.read_text())
    else:
        wl = {}
    tickers = wl.get("tickers", [])

    def fetch_one(ticker):
        try:
            import yfinance as yf
            t    = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="7d")
            sparkline = [round(float(p), 2) for p in hist["Close"].tolist()] if not hist.empty else []
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            ticker_dir = REPORTS_DIR / ticker
            has_analysis = ticker_dir.exists() and any(
                f.startswith("01_") for f in os.listdir(str(ticker_dir))
                if os.path.isfile(str(ticker_dir / f))
            )
            return {
                "ticker":        ticker,
                "name":          info.get("shortName") or info.get("longName") or ticker,
                "price":         round(float(price), 2) if price else None,
                "change_pct":    round(float(info.get("regularMarketChangePercent", 0)), 2),
                "change":        round(float(info.get("regularMarketChange", 0)), 2),
                "market_cap":    info.get("marketCap"),
                "sparkline":     sparkline,
                "last_analysis": {"has_analysis": has_analysis},
            }
        except Exception as e:
            return {"ticker": ticker, "error": str(e), "sparkline": []}

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch_one, tickers))
    return jsonify({"quotes": results, "timestamp": time.time()})


# ── Recent alerts ─────────────────────────────────────────────────────────────
@app.route("/api/alerts/recent")
def api_alerts_recent():
    cache_file = PROJECT_ROOT / "automation" / ".alert_cache.json"
    if not cache_file.exists():
        return jsonify({"alerts": [], "message": "No alerts yet — your watchlist is being monitored"})
    try:
        data = json.loads(cache_file.read_text())
        alerts = (data if isinstance(data, list) else list(data.values()))[-10:]
        return jsonify({"alerts": alerts})
    except Exception as e:
        return jsonify({"alerts": [], "error": str(e)})


def _extract_rating(ticker_dir: Path):
    """Pull rating and price target from the analysis markdown if present."""
    md_files = sorted(ticker_dir.glob("05_*.md"))
    if not md_files:
        return None, None
    try:
        content = md_files[0].read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"(?:consensus|rating|recommendation)[^:\n]*:\s*\**(buy|sell|hold)\**", content, re.IGNORECASE)
        if not m:
            m = re.search(r"\*\*(BUY|SELL|HOLD)\*\*", content)
        rating = m.group(1).capitalize() if m else None
        t = re.search(r"(?:price target|target)[^:$\n]*\$\s*([\d,]+(?:\.\d+)?)", content, re.IGNORECASE)
        target = f"${t.group(1)}" if t else None
        return rating, target
    except Exception:
        return None, None


# ── Market Bar ───────────────────────────────────────────────────────────────
_TICKER_CACHE: dict = {"data": None, "ts": 0.0}
_TICKER_LOCK = threading.Lock()


def _is_market_open_py() -> bool:
    from datetime import datetime, timezone, timedelta
    et = timezone(timedelta(hours=-4))  # EDT approximation
    now = datetime.now(et)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= mins < 16 * 60

def _load_watchlist_tickers() -> list:
    try:
        wl_path = PROJECT_ROOT / "automation" / "watchlist.json"
        with open(wl_path) as f:
            return json.load(f).get("tickers", [])
    except Exception:
        return []


@app.route("/api/market-bar")
def api_market_bar():
    """Fetch indices + watchlist tickers for the scrolling ticker tape (55s server cache)."""
    with _TICKER_LOCK:
        if _TICKER_CACHE["data"] and (time.time() - _TICKER_CACHE["ts"]) < 55:
            return jsonify(_TICKER_CACHE["data"])

    def _fetch_one(ticker, label=None, is_yield=False):
        lbl = label or ticker
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
            change_pct = info.get("regularMarketChangePercent") or 0
            change = info.get("regularMarketChange") or 0
            if price is None:
                return {"ticker": ticker, "label": lbl, "error": "no data"}
            return {
                "ticker": ticker,
                "label": lbl,
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "change_pct": round(float(change_pct), 2),
                "is_yield": is_yield,
            }
        except Exception as ex:
            return {"ticker": ticker, "label": lbl, "error": str(ex)[:80]}

    watchlist = _load_watchlist_tickers()

    pool = ThreadPoolExecutor(max_workers=10)
    f_spx = pool.submit(_fetch_one, "^GSPC", "S&P 500")
    f_vix = pool.submit(_fetch_one, "^VIX", "VIX")
    f_tsy = pool.submit(_fetch_one, "^TNX", "10yr", True)
    wl_futures = {t: pool.submit(_fetch_one, t) for t in watchlist}

    all_futures = [f_spx, f_vix, f_tsy] + list(wl_futures.values())
    futures_wait(all_futures, timeout=4)
    pool.shutdown(wait=False)

    def _safe(f):
        try:
            return f.result(timeout=0)
        except Exception:
            return {"error": "timeout"}

    wl_results = []
    for t in watchlist:
        r = _safe(wl_futures[t])
        if "ticker" not in r:
            r["ticker"] = t
        wl_results.append(r)

    result = {
        "spx": _safe(f_spx),
        "vix": _safe(f_vix),
        "tsy": _safe(f_tsy),
        "watchlist": wl_results,
        "market_open": _is_market_open_py(),
        "timestamp": time.time(),
    }

    with _TICKER_LOCK:
        _TICKER_CACHE["data"] = result
        _TICKER_CACHE["ts"] = result["timestamp"]

    return jsonify(result)


# ── Test notification ─────────────────────────────────────────────────────────
@app.route("/api/notify/test", methods=["POST"])
def api_notify_test():
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        import requests as req
        resp = req.post(
            "https://ntfy.sh/sam-madding-finance-alerts",
            data="Test notification from Lindner Research Platform".encode(),
            headers={"Title": "Platform Test", "Priority": "default", "Tags": "white_check_mark"},
            timeout=10,
        )
        ok = resp.status_code == 200
        print(f"[ntfy] test push HTTP {resp.status_code}: {resp.text[:120]}", file=sys.stderr)
        return jsonify({"ok": ok, "status_code": resp.status_code, "body": resp.text[:200]})
    except Exception as e:
        print(f"[ntfy] test push FAILED: {e}", file=sys.stderr)
        return jsonify({"ok": False, "error": str(e)}), 500

# ── OG image ──────────────────────────────────────────────────────────────────
@app.route("/og-image.png")
def og_image():
    return send_from_directory("static", "og-image.png")


# ── Example outputs ───────────────────────────────────────────────────────────
@app.route("/api/examples")
def api_examples():
    examples_dir = os.path.join(app.static_folder, "examples")
    file_config = [
        {
            "filename": "LLY_Research_Model.xlsx",
            "label": "Excel Research Model",
            "description": "17 sheets — DCF, comps, earnings history, insider tracking, debt schedule",
            "icon": "📊",
            "type": "excel",
        },
        {
            "filename": "LLY_Research_Report.pdf",
            "label": "Research Report",
            "description": "10-page institutional report with analyst note and price target",
            "icon": "📄",
            "type": "pdf",
        },
        {
            "filename": "LLY_Pitch_Deck.pptx",
            "label": "Pitch Deck",
            "description": "12-slide deck with football field valuation and investment thesis",
            "icon": "📑",
            "type": "pptx",
        },
        {
            "filename": "LLY_Education_Guide.pdf",
            "label": "Education Guide",
            "description": "Plain-English companion explaining every metric and model assumption",
            "icon": "🎓",
            "type": "pdf",
        },
    ]
    files = []
    for f in file_config:
        path = os.path.join(examples_dir, f["filename"])
        if os.path.exists(path):
            size_bytes = os.path.getsize(path)
            if size_bytes >= 1024 * 1024:
                size_str = f"{size_bytes / 1024 / 1024:.1f} MB"
            else:
                size_str = f"{size_bytes / 1024:.0f} KB"
            files.append({
                **f,
                "url": f"/static/examples/{f['filename']}",
                "size_mb": round(size_bytes / 1024 / 1024, 2),
                "size_str": size_str,
            })
    return jsonify({"ticker": "LLY", "company": "Eli Lilly & Co.", "files": files})


# ── Feedback ───────────────────────────────────────────────────────────────────
_FEEDBACK_FILE = _this_dir / "feedback.json"

@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message required"}), 400

    name      = (data.get("name") or "Anonymous").strip() or "Anonymous"
    page      = request.headers.get("Referer", "unknown")
    timestamp = datetime.now().isoformat()

    entry = {"timestamp": timestamp, "name": name, "message": message, "page": page}

    # Log to feedback.json (always, never crash)
    try:
        with open(_FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Send email via iCloud SMTP (best-effort — failure never surfaces to user)
    _send_feedback_email(name, message, page, timestamp)

    return jsonify({"ok": True})


def _send_feedback_email(name: str, message: str, page: str, timestamp: str) -> None:
    import smtplib
    from email.message import EmailMessage

    icloud_email    = os.environ.get("ICLOUD_EMAIL", "").strip()
    icloud_password = os.environ.get("ICLOUD_APP_PASSWORD", "").strip()
    if not icloud_email or not icloud_password:
        return  # Env vars not configured — skip silently

    try:
        msg = EmailMessage()
        msg["Subject"] = f"Lindner Platform Feedback — {name}"
        msg["From"]    = icloud_email
        msg["To"]      = icloud_email
        msg.set_content(
            f"Name: {name}\n"
            f"Message: {message}\n"
            f"Page: {page}\n"
            f"Time: {timestamp}\n"
        )
        with smtplib.SMTP("smtp.mail.me.com", 587, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(icloud_email, icloud_password)
            smtp.send_message(msg)
        print(f"[feedback] email sent for '{name}'", file=sys.stderr)
    except Exception as ex:
        print(f"[feedback] email failed (non-fatal): {ex}", file=sys.stderr)


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
