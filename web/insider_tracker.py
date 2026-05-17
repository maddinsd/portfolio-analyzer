from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta

import requests

_HEADERS     = {"User-Agent": "SamuelMadding/1.0 sdmadding@icloud.com"}
_DELAY       = 0.15        # 150ms between EDGAR requests — stays under 10 req/sec
_MAX_FILINGS = 40          # cap Form 4 fetches to bound latency

# Only open-market transactions carry informational content
_KEEP = {"P", "S"}

_CEO_TITLES = {"chief executive", "ceo", "president", "co-ceo", "co-president"}
_CFO_TITLES = {"chief financial", "cfo", "chief accounting"}


# ── EDGAR helpers ─────────────────────────────────────────────────────────────

def _edgar_get(url: str, timeout: int = 20) -> requests.Response | None:
    time.sleep(_DELAY)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception:
        return None


def _get_cik(ticker: str) -> str | None:
    """CIK lookup — mirrors sec_parser.py logic (no cross-import)."""
    r = _edgar_get("https://www.sec.gov/files/company_tickers.json")
    if not r:
        return None
    try:
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        pass
    return None


def _get_form4_listing(cik10: str, days: int = 365) -> list[dict]:
    """Return Form 4 filings within `days`, newest-first, capped at _MAX_FILINGS."""
    r = _edgar_get(f"https://data.sec.gov/submissions/CIK{cik10}.json")
    if not r:
        return []
    try:
        subs    = r.json()
        recent  = subs["filings"]["recent"]
        forms   = recent.get("form", [])
        dates   = recent.get("filingDate", [])
        accs    = recent.get("accessionNumber", [])
        cik_int = int(subs.get("cik", 0))
    except Exception:
        return []

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result: list[dict] = []
    for i, f in enumerate(forms):
        if f != "4":
            continue
        if dates[i] < cutoff:
            break  # newest-first — safe to stop
        if len(result) >= _MAX_FILINGS:
            break
        acc_clean = accs[i].replace("-", "")
        url = (f"https://www.sec.gov/Archives/edgar/data/"
               f"{cik_int}/{acc_clean}/form4.xml")
        result.append({"filed": dates[i], "url": url})
    return result


# ── Form 4 XML parsing ────────────────────────────────────────────────────────

def _role(title: str) -> str:
    t = title.lower()
    if any(k in t for k in _CEO_TITLES):
        return "ceo"
    if any(k in t for k in _CFO_TITLES):
        return "cfo"
    return "other"


def _parse_form4(url: str, filed_date: str) -> list[dict]:
    """Parse one Form 4 XML → list of filtered transaction dicts."""
    r = _edgar_get(url)
    if not r:
        return []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return []

    is_10b5 = (root.findtext("aff10b5One") or "").lower() == "true"

    owner = root.find("reportingOwner")
    if owner is None:
        return []
    name  = (owner.findtext("reportingOwnerId/rptOwnerName") or "Unknown").strip()
    title = (owner.findtext("reportingOwnerRelationship/officerTitle") or "").strip()
    is_director = (owner.findtext("reportingOwnerRelationship/isDirector") or "0") == "1"
    is_ten_pct  = (owner.findtext("reportingOwnerRelationship/isTenPercentOwner") or "0") == "1"
    if not title:
        title = "Director" if is_director else ("10% Owner" if is_ten_pct else "Other")

    txns: list[dict] = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = (tx.findtext("transactionCoding/transactionCode") or "").upper()
        if code not in _KEEP:
            continue
        date_val = tx.findtext("transactionDate/value") or filed_date
        try:
            shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
            price  = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except (ValueError, TypeError):
            continue
        value = shares * price
        if value < 50_000:
            continue  # immaterial
        post_shares = 0.0
        try:
            post_shares = float(
                tx.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value") or 0
            )
        except (ValueError, TypeError):
            pass
        txns.append({
            "date":        date_val,
            "name":        name,
            "title":       title,
            "code":        code,
            "is_10b5":     is_10b5,
            "is_director": is_director,
            "shares":      shares,
            "price":       price,
            "value":       value,
            "post_shares": post_shares,
        })
    return txns


# ── Signal scoring ────────────────────────────────────────────────────────────

def _cluster_check(bought_txns: list[dict]) -> bool:
    """True if 3+ unique insiders bought within any 30-day window."""
    # Only non-10b5-1 purchases
    dates = sorted([
        (t["date"], t["name"]) for t in bought_txns if not t["is_10b5"]
    ])
    for i, (d, _) in enumerate(dates):
        end = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        names = {nm for bd, nm in dates[i:] if bd <= end}
        if len(names) >= 3:
            return True
    return False


def _score_conviction(txns_90d: list[dict]) -> tuple[float, str]:
    """
    Algorithmic conviction score 1.0–10.0.
    Only non-10b5-1 transactions drive the score.
    """
    # Exclude ALL 10b5-1 transactions from scoring — pre-scheduled, no signal
    signal = [t for t in txns_90d if not t["is_10b5"]]
    if not signal:
        return 5.0, "No Signal"

    bought = [t for t in signal if t["code"] == "P"]
    sold   = [t for t in signal if t["code"] == "S"]

    score = 5.0

    # Role-based buy bonuses (apply once per role)
    roles_bought = {_role(t["title"]) for t in bought}
    if "ceo" in roles_bought:
        score += 2.0
    if "cfo" in roles_bought:
        score += 1.5
    if any(t["is_director"] and _role(t["title"]) == "other" for t in bought):
        score += 1.0

    # Cluster buy
    if _cluster_check(bought):
        score += 1.5

    # Total open-market buy volume
    total_bought = sum(t["value"] for t in bought)
    if total_bought > 5_000_000:
        score += 1.0
    elif total_bought > 1_000_000:
        score += 0.5

    # CEO open-market sell penalty
    for t in sold:
        if _role(t["title"]) == "ceo" and t["value"] > 10_000_000:
            score -= 2.0
            break

    # Multiple directors selling simultaneously
    dir_sellers = {t["name"] for t in sold if t["is_director"]}
    if len(dir_sellers) >= 2:
        score -= 1.0

    score = max(1.0, min(10.0, score))

    if score >= 8.0:
        label = "Very High"
    elif score >= 6.5:
        label = "High"
    elif score >= 4.5:
        label = "Moderate"
    elif score >= 3.0:
        label = "Low"
    else:
        label = "Very Low"

    return round(score, 1), label


def _net_signal(total_bought: float, total_sold: float,
                score: float, has_txns: bool) -> str:
    if not has_txns:
        return "Neutral"
    if score >= 8.0 and total_bought > total_sold:
        return "Strong Buy"
    if score >= 6.5 and total_bought > total_sold * 0.5:
        return "Buy"
    if score <= 2.5 and total_sold > total_bought * 2:
        return "Strong Sell"
    if score < 4.0 and total_sold > total_bought:
        return "Sell"
    return "Neutral"


# ── Main entry ────────────────────────────────────────────────────────────────

def run_insider_tracker(ticker: str, stats: dict, fin_data: dict) -> dict:
    """Fetch and parse SEC Form 4 filings — algorithmic only, no Claude calls.
    Returns {"error": "reason"} on failure, never raises.
    """
    try:
        return _run(ticker, stats, fin_data)
    except Exception as exc:
        return {"error": str(exc)}


def _run(ticker: str, stats: dict, fin_data: dict) -> dict:
    cik10 = _get_cik(ticker)
    if not cik10:
        return {"error": f"CIK not found for {ticker}"}

    listings = _get_form4_listing(cik10, days=365)
    if not listings:
        return {"error": "No Form 4 filings found in last 12 months"}

    # Parse all filings (EDGAR requests are already rate-limited in _edgar_get)
    cutoff_90d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    all_txns: list[dict] = []
    for item in listings:
        all_txns.extend(_parse_form4(item["url"], item["filed"]))

    all_txns.sort(key=lambda t: t["date"], reverse=True)
    txns_90d = [t for t in all_txns if t["date"] >= cutoff_90d]

    # 90-day aggregates
    bought_90d      = [t for t in txns_90d if t["code"] == "P"]
    sold_90d        = [t for t in txns_90d if t["code"] == "S"]
    total_bought_90d = sum(t["value"] for t in bought_90d)
    total_sold_90d   = sum(t["value"] for t in sold_90d)
    unique_buyers    = len({t["name"] for t in bought_90d})
    unique_sellers   = len({t["name"] for t in sold_90d})
    cluster          = _cluster_check(bought_90d)

    score, conv_label = _score_conviction(txns_90d)
    signal = _net_signal(total_bought_90d, total_sold_90d, score, bool(txns_90d))

    largest = max(all_txns, key=lambda t: t["value"]) if all_txns else None

    # Monthly net activity for chart (12 months)
    monthly: dict[str, float] = defaultdict(float)
    for t in all_txns:
        m = t["date"][:7]
        monthly[m] += t["value"] if t["code"] == "P" else -t["value"]

    # Top 5 insiders by volume (12 months)
    agg: dict = defaultdict(lambda: {"bought": 0.0, "sold": 0.0, "title": "", "last_date": ""})
    for t in all_txns:
        k = t["name"]
        agg[k]["title"] = t["title"]
        if t["code"] == "P":
            agg[k]["bought"] += t["value"]
        else:
            agg[k]["sold"] += t["value"]
        if t["date"] > agg[k]["last_date"]:
            agg[k]["last_date"] = t["date"]
    top_insiders = sorted(
        [{"name": k, **v, "net": v["bought"] - v["sold"]} for k, v in agg.items()],
        key=lambda x: x["bought"] + x["sold"],
        reverse=True,
    )[:5]

    return {
        "error":              None,
        "cik":                cik10,
        "ticker":             ticker.upper(),
        "transactions_90d":   txns_90d[:20],
        "transactions_12m":   all_txns,
        "net_signal_90d":     signal,
        "total_bought_90d":   total_bought_90d,
        "total_sold_90d":     total_sold_90d,
        "unique_buyers_90d":  unique_buyers,
        "unique_sellers_90d": unique_sellers,
        "largest_transaction": largest,
        "cluster_signal":     cluster,
        "conviction_score":   score,
        "conviction_label":   conv_label,
        "monthly_net_12m":    dict(monthly),
        "top_insiders":       top_insiders,
    }
