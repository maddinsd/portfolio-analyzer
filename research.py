from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import anthropic

_MODEL   = "claude-sonnet-4-6"
_MAX_TOK = 800
_TIMEOUT = 60
_SYSTEM  = "You are a senior equity analyst. Be precise and data-specific. Output only valid JSON."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_large(val) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "N/A"
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= threshold:
            return f"${v / threshold:.1f}{suffix}"
    return f"${v:.0f}"


def _fmt_m(val_m) -> str:
    if val_m is None:
        return "N/A"
    try:
        v = float(val_m)
    except (TypeError, ValueError):
        return "N/A"
    return f"${v / 1000:.1f}B" if abs(v) >= 1000 else f"${v:.0f}M"


def _build_context(ticker: str, stats: dict, fin_data: dict) -> str:
    info  = stats["info"]
    a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
    a_cf  = (fin_data.get("cash_flow") or {}).get("annual") or {}
    bs    = fin_data.get("balance_sheet") or {}
    return json.dumps({
        "ticker":  ticker,
        "company": info.get("shortName") or info.get("longName") or ticker,
        "sector":  info.get("sector"),
        "ind":     info.get("industry"),
        "px":      stats["current_price"],
        "mktCap":  _fmt_large(info.get("marketCap")),
        "pe":      info.get("trailingPE"),
        "fpe":     info.get("forwardPE"),
        "eps":     info.get("trailingEps"),
        "feps":    info.get("forwardEps"),
        "revGr":   stats.get("revenue_growth_yoy"),
        "ret6m":   stats["stock_return_6mo"],
        "vsSpx":   stats["relative_return"],
        "tgt":     info.get("targetMeanPrice"),
        "rat":     info.get("recommendationMean"),
        "nAn":     info.get("numberOfAnalystOpinions"),
        "gm":      (a_inc.get("gross_margin") or [None])[0],
        "om":      (a_inc.get("operating_margin") or [None])[0],
        "nm":      (a_inc.get("net_margin") or [None])[0],
        "rev":     _fmt_m((a_inc.get("revenue") or [None])[0]),
        "fcf":     _fmt_m((a_cf.get("free_cash_flow") or [None])[0]),
        "netDebt": _fmt_m(bs.get("net_debt")),
    }, separators=(",", ":"))


def _parse_json(text: str) -> dict | None:
    # Try ```json ... ``` block first
    m = re.search(r'```(?:json)?\s*(\{[\s\S]+?\})\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Walk from first '{' counting braces — handles any nesting
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _call(client: anthropic.Anthropic, prompt: str) -> str:
    return client.messages.create(
        model=_MODEL, max_tokens=_MAX_TOK, system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text.strip()


def _placeholder(kind: str, error: str) -> dict:
    return {"_placeholder": True, "_error": error, "_kind": kind}


# ── Research tasks ────────────────────────────────────────────────────────────

def _run_thesis(client: anthropic.Anthropic, ctx: str) -> dict:
    d = json.loads(ctx)
    prompt = (
        f"Investment thesis for {d['ticker']} ({d.get('company')}, {d.get('sector')}).\n"
        f"Data: {ctx}\n"
        f"Output ONLY this JSON:\n"
        f'{{"bull":["pt1","pt2","pt3","pt4"],"bear":["pt1","pt2","pt3","pt4"],'
        f'"catalysts":["c1","c2","c3"],"rating":"Buy","target":"$XXX — rationale",'
        f'"verdict":"one sentence with clear stance"}}\n'
        f"4 bull, 4 bear, 3 catalysts. Quote specific numbers. rating must be Buy/Hold/Sell."
    )
    return _parse_json(_call(client, prompt)) or _placeholder("thesis", "parse failed")


def _run_comps(client: anthropic.Anthropic, ctx: str) -> dict:
    d = json.loads(ctx)
    prompt = (
        f"Comparable companies for {d['ticker']} ({d.get('sector')}).\n"
        f"Target: {ctx}\n"
        f"Output ONLY this JSON:\n"
        f'{{"comps":[{{"company":"Name","ticker":"XXX","ev_ebitda":25.3,"pe_fwd":32.1,'
        f'"ev_rev":8.5,"note":"brief positioning"}}],'
        f'"summary":"2-3 sentence relative valuation","premium":"±X% to peer median EV/EBITDA"}}\n'
        f"5 closest peers. Multiples from training data (approximate)."
    )
    return _parse_json(_call(client, prompt)) or _placeholder("comps", "parse failed")


def _run_earnings(client: anthropic.Anthropic, ctx: str) -> dict:
    d = json.loads(ctx)
    prompt = (
        f"Earnings preview for {d['ticker']} ({d.get('company')}).\n"
        f"Data: {ctx}\n"
        f"Output ONLY this JSON:\n"
        f'{{"next_earnings":"Q3 FY26 (est.)","consensus_rev":"$XXB","consensus_eps":"$X.XX",'
        f'"implied_move":"~X%","watch":["item1","item2","item3"],'
        f'"scenarios":['
        f'{{"name":"Bull","rev":"$XXB","eps":"$X.XX","move":"+X%","prob":"25%","trigger":"..."}},'
        f'{{"name":"Base","rev":"$XXB","eps":"$X.XX","move":"+X%","prob":"50%","trigger":"..."}},'
        f'{{"name":"Bear","rev":"$XXB","eps":"$X.XX","move":"-X%","prob":"25%","trigger":"..."}}]}}\n'
        f"Base estimates on analyst consensus and recent trend. Be specific."
    )
    return _parse_json(_call(client, prompt)) or _placeholder("earnings", "parse failed")


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_research_pipeline(ticker: str, stats: dict, fin_data: dict) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        err = "ANTHROPIC_API_KEY not set"
        return {k: _placeholder(k, err) for k in ("thesis", "comps", "earnings")}

    client = anthropic.Anthropic(api_key=api_key)
    ctx    = _build_context(ticker, stats, fin_data)

    tasks = [
        ("thesis",   "Investment thesis", _run_thesis),
        ("comps",    "Comps analysis",    _run_comps),
        ("earnings", "Earnings preview",  _run_earnings),
    ]

    def _timed(name, fn):
        t0 = time.time()
        return fn(client, ctx), round(time.time() - t0, 1)

    results: dict = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {name: ex.submit(_timed, name, fn) for name, _, fn in tasks}
        for name, label, _ in tasks:
            try:
                result, elapsed = futures[name].result(timeout=_TIMEOUT)
                results[name] = result
                tag = "✗ placeholder" if result.get("_placeholder") else "✓"
                print(f"    {tag} {label} ({elapsed}s)")
            except FuturesTimeout:
                results[name] = _placeholder(name, "timeout")
                print(f"    ✗ {label} (timeout after {_TIMEOUT}s)")
            except Exception as e:
                results[name] = _placeholder(name, str(e)[:80])
                print(f"    ✗ {label} (error)")

    return results
