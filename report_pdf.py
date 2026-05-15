from __future__ import annotations

import io
import math
from datetime import date as _date
from functools import partial

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether,
    NextPageTemplate,
)

# ── Design constants ──────────────────────────────────────────────────────────
_NAVY  = colors.HexColor('#003366')
_BLUE  = colors.HexColor('#1F4E79')
_STEEL = colors.HexColor('#2D5F8A')
_GREEN = colors.HexColor('#1D6F42')
_RED   = colors.HexColor('#C00000')
_GOLD  = colors.HexColor('#D4A017')
_LGREY = colors.HexColor('#F2F2F2')
_MGREY = colors.HexColor('#808080')
_DGREY = colors.HexColor('#333333')
_WHITE = colors.white
_BLACK = colors.black

_PW, _PH = letter          # 8.5" × 11"
_LM = _RM = _TM = _BM = inch

_SANS   = 'Helvetica'       # ≈ Arial
_SANS_B = 'Helvetica-Bold'
_SERIF  = 'Times-Roman'     # ≈ Times New Roman
_SERIF_B = 'Times-Bold'

_UC_RED  = colors.HexColor('#E00122')
_UC_HDR  = "University of Cincinnati  |  Carl H. Lindner College of Business"
_ANALYST = "Samuel Madding"
_CONF    = "University of Cincinnati | Lindner College of Business — For Educational Purposes Only"


# ── Format helpers ────────────────────────────────────────────────────────────

def _sf(val, digits: int = 2):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, digits)
    except (TypeError, ValueError):
        return None


def _sa(d, *keys, default="—"):
    if not d:
        return default
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


def _fp(v) -> str:
    f = _sf(v)
    return f"${f:,.2f}" if f is not None else "—"


def _fpct(v, plus: bool = False) -> str:
    f = _sf(v, 1)
    if f is None:
        return "—"
    prefix = "+" if plus and f > 0 else ""
    return f"{prefix}{f:.1f}%"


def _flarge(v) -> str:
    f = _sf(v)
    if f is None:
        return "—"
    for sfx, thr in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(f) >= thr:
            return f"${f/thr:.2f}{sfx}"
    return f"${f:,.0f}"


def _fm(v_m) -> str:
    f = _sf(v_m)
    if f is None:
        return "—"
    if abs(f) >= 1000:
        return f"${f/1000:.1f}B"
    return f"${f:.0f}M"


def _pct_str(v) -> str:
    return f"{v:.1f}%" if v is not None else "—"


# ── Fallback helpers (mirror pitch.py — no cross-module import) ───────────────

def _fallback_rating(research, cov_result) -> str:
    thesis = (research or {}).get("thesis") or {}
    if not thesis.get("_placeholder") and thesis.get("rating"):
        return thesis["rating"]
    if cov_result and not cov_result.get("error"):
        return cov_result.get("consensus_rating") or "—"
    return "—"


def _fallback_target(research, cov_result) -> str:
    thesis = (research or {}).get("thesis") or {}
    if not thesis.get("_placeholder"):
        raw = (thesis.get("target") or "").split("—")[0].strip()
        if raw:
            return raw
    if cov_result and not cov_result.get("error"):
        mt = cov_result.get("mean_target")
        if mt:
            return _fp(mt)
    return "—"


def _fallback_bulls(research, stats, fin_data, comp_result) -> list[str]:
    thesis = (research or {}).get("thesis") or {}
    ok = not thesis.get("_placeholder")
    bulls = thesis.get("bull", []) if ok else []
    if len(bulls) >= 2:
        return bulls
    info = (stats or {}).get("info", {})
    a_inc = ((fin_data or {}).get("income_statement") or {}).get("annual") or {}
    out = []
    rev_gr = (stats or {}).get("revenue_growth_yoy")
    if rev_gr is not None:
        out.append(f"Revenue {_fpct(rev_gr, plus=True)} YoY — growth at scale demonstrates pricing power")
    gm_list = a_inc.get("gross_margin") or []
    gm, gm_p = (gm_list[0] if gm_list else None), (gm_list[1] if len(gm_list) > 1 else None)
    if gm and gm_p:
        delta = round(gm - gm_p, 1)
        out.append(f"Gross margin {gm:.1f}% ({'+' if delta>=0 else ''}{delta:.1f}pp YoY) — services mix shift accelerating re-rating")
    fpe = _sf(info.get("forwardPE"), 1)
    peer_fpe = _sf(_sa(comp_result, "peer_medians", "fpe")) if comp_result and not comp_result.get("error") else None
    if fpe and peer_fpe and peer_fpe > 0:
        prem = round((fpe / peer_fpe - 1) * 100, 0)
        out.append(f"{fpe:.1f}x fwd P/E ({prem:+.0f}% to {peer_fpe:.1f}x peer median) — ecosystem lock-in justifies duration premium")
    beta = _sf(info.get("beta"), 2)
    if beta:
        out.append(f"Beta {beta:.2f} — defensive quality with deep institutional ownership")
    return out or ["Full thesis available in non-dry-run mode"]


def _fallback_bears(research, stats, fin_data, dcf_result, comp_result) -> list[str]:
    thesis = (research or {}).get("thesis") or {}
    ok = not thesis.get("_placeholder")
    bears = thesis.get("bear", []) if ok else []
    if len(bears) >= 2:
        return bears
    info = (stats or {}).get("info", {})
    out = []
    fpe = _sf(info.get("forwardPE"), 1)
    peer_fpe = _sf(_sa(comp_result, "peer_medians", "fpe")) if comp_result and not comp_result.get("error") else None
    if fpe and peer_fpe and peer_fpe > 0:
        prem = round((fpe / peer_fpe - 1) * 100, 0)
        out.append(f"Valuation compression — {fpe:.1f}x fwd P/E ({prem:.0f}% premium to {peer_fpe:.1f}x peer median); guidance miss triggers immediate de-rating")
    if dcf_result and not dcf_result.get("error"):
        iv = _sf(_sa(dcf_result, "valuation", "intrinsic"))
        px = _sf((stats or {}).get("current_price"))
        wacc = _sa(dcf_result, "inputs", "wacc")
        if iv and px and iv < px:
            disc = round((1 - iv/px) * 100, 0)
            out.append(f"DCF fair value {_fp(iv)} is {disc:.0f}% below current price at WACC {wacc}% — priced for perfect execution")
    rev_gr = (stats or {}).get("revenue_growth_yoy")
    if rev_gr is not None:
        out.append(f"Growth deceleration risk — LTM revenue {_fpct(rev_gr, plus=True)}; any slowdown destroys terminal value at current multiples")
    return out or ["Full risk analysis available in non-dry-run mode"]


def _fallback_catalysts(research, stats, fin_data, comp_result, cov_result) -> list[str]:
    thesis = (research or {}).get("thesis") or {}
    ok = not thesis.get("_placeholder")
    cats = thesis.get("catalysts", []) if ok else []
    if len(cats) >= 2:
        return cats
    out = []
    rev_gr = (stats or {}).get("revenue_growth_yoy")
    peer_rev_gr = _sf(_sa(comp_result, "peer_medians", "rev_growth")) if comp_result and not comp_result.get("error") else None
    if rev_gr is not None:
        vs = f" vs. peer median {peer_rev_gr:.1f}%" if peer_rev_gr else ""
        out.append(f"Revenue {_fpct(rev_gr, plus=True)} YoY{vs} — sustained top-line growth at scale")
    a_inc = ((fin_data or {}).get("income_statement") or {}).get("annual") or {}
    gm_list = a_inc.get("gross_margin") or []
    gm, gm_p = (gm_list[0] if gm_list else None), (gm_list[1] if len(gm_list) > 1 else None)
    if gm and gm_p:
        delta = round(gm - gm_p, 1)
        out.append(f"Gross margin {gm:.1f}% ({'+' if delta>=0 else ''}{delta:.1f}pp YoY) — operating leverage from mix shift")
    if cov_result and not cov_result.get("error"):
        n_an = cov_result.get("total_analysts")
        mean_t = cov_result.get("mean_target")
        up = cov_result.get("upside_pct")
        rat = cov_result.get("consensus_rating")
        if mean_t and n_an:
            out.append(f"{n_an} analysts covering; {rat or 'consensus'} with mean target {_fp(mean_t)} ({_fpct(up, plus=True)} upside)")
    return out or ["Full catalysts available in non-dry-run mode"]


# ── Paragraph styles ──────────────────────────────────────────────────────────

def _build_styles() -> dict:
    def _ps(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "h1": _ps("h1", fontName=_SANS_B, fontSize=14, textColor=_NAVY,
                  spaceAfter=6, spaceBefore=14, leading=17),
        "h2": _ps("h2", fontName=_SANS_B, fontSize=11, textColor=_NAVY,
                  spaceAfter=4, spaceBefore=10, leading=14),
        "h3": _ps("h3", fontName=_SANS_B, fontSize=10, textColor=_STEEL,
                  spaceAfter=3, spaceBefore=8, leading=13),
        "body": _ps("body", fontName=_SERIF, fontSize=9.5, textColor=_DGREY,
                    spaceAfter=5, leading=13),
        "body_sm": _ps("body_sm", fontName=_SERIF, fontSize=8.5, textColor=_DGREY,
                       spaceAfter=3, leading=11),
        "bullet": _ps("bullet", fontName=_SERIF, fontSize=9, textColor=_DGREY,
                      leftIndent=12, spaceAfter=4, leading=12,
                      bulletText="▸"),
        "caption": _ps("caption", fontName=_SANS, fontSize=7.5, textColor=_MGREY,
                       spaceAfter=4, leading=10),
        "rating_buy": _ps("rating_buy", fontName=_SANS_B, fontSize=20,
                          textColor=_GREEN, alignment=1, leading=24),
        "rating_hold": _ps("rating_hold", fontName=_SANS_B, fontSize=20,
                           textColor=_MGREY, alignment=1, leading=24),
        "rating_sell": _ps("rating_sell", fontName=_SANS_B, fontSize=20,
                           textColor=_RED, alignment=1, leading=24),
        "center": _ps("center", fontName=_SERIF, fontSize=9.5, textColor=_DGREY,
                      alignment=1, spaceAfter=4, leading=13),
        "disclaimer": _ps("disclaimer", fontName=_SANS, fontSize=7, textColor=_MGREY,
                          alignment=1, leading=9),
    }


# ── Table helper ──────────────────────────────────────────────────────────────

_BASE_TS = [
    ('BACKGROUND',    (0, 0), (-1, 0),  _NAVY),
    ('TEXTCOLOR',     (0, 0), (-1, 0),  _WHITE),
    ('FONTNAME',      (0, 0), (-1, 0),  _SANS_B),
    ('FONTSIZE',      (0, 0), (-1, 0),  8.5),
    ('ROWBACKGROUNDS',(0, 1), (-1, -1), [_WHITE, _LGREY]),
    ('FONTNAME',      (0, 1), (-1, -1), _SERIF),
    ('FONTSIZE',      (0, 1), (-1, -1), 8.5),
    ('ALIGN',         (0, 0), (0,  -1), 'LEFT'),
    ('ALIGN',         (1, 0), (-1, -1), 'CENTER'),
    ('GRID',          (0, 0), (-1, -1), 0.25, _MGREY),
    ('LEFTPADDING',   (0, 0), (-1, -1), 4),
    ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ('TOPPADDING',    (0, 0), (-1, -1), 3),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
]


def _tbl(data: list[list], col_w: list[float],
         extra: list | None = None, target_row: int | None = None) -> Table:
    ts = list(_BASE_TS)
    if target_row is not None:
        ts += [
            ('BACKGROUND', (0, target_row), (-1, target_row), _STEEL),
            ('TEXTCOLOR',  (0, target_row), (-1, target_row), _WHITE),
            ('FONTNAME',   (0, target_row), (-1, target_row), _SANS_B),
        ]
    if extra:
        ts += extra
    return Table(data, colWidths=col_w, style=TableStyle(ts),
                 repeatRows=1, hAlign='LEFT')


# ── Matplotlib chart generators ───────────────────────────────────────────────

def _mpl_colors():
    return {
        'navy':  '#003366',
        'blue':  '#1F4E79',
        'steel': '#2D5F8A',
        'gold':  '#D4A017',
        'red':   '#C00000',
        'lgrey': '#F2F2F2',
        'mgrey': '#808080',
    }


def _chart_revenue_fcf(fin_data: dict, width: float = 5.5, height: float = 2.4) -> Image | None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
        a_cf  = (fin_data.get("cash_flow") or {}).get("annual") or {}
        dates = a_inc.get("dates", [])[:4]
        rev   = a_inc.get("revenue", [])[:4]
        fcf   = a_cf.get("free_cash_flow", [])[:4]

        if not dates or not rev:
            return None

        c = _mpl_colors()
        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')

        x = np.arange(len(dates))
        bw = 0.35
        r_vals = [v/1000 if v else 0 for v in rev]   # billions
        f_vals = [v/1000 if v else 0 for v in fcf]

        b1 = ax.bar(x - bw/2, r_vals, bw, color=c['navy'], label='Revenue ($B)', zorder=3)
        b2 = ax.bar(x + bw/2, f_vals, bw, color=c['steel'], label='FCF ($B)', zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels(dates, fontsize=7)
        ax.yaxis.set_tick_params(labelsize=7)
        ax.set_ylabel('$ Billions', fontsize=7, color=c['mgrey'])
        ax.tick_params(colors=c['mgrey'])
        ax.grid(axis='y', color=c['lgrey'], linewidth=0.5, zorder=0)
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(c['mgrey'])
        ax.legend(fontsize=7, framealpha=0, loc='upper left')
        ax.set_title('Revenue & Free Cash Flow ($B)', fontsize=8, color=c['navy'],
                     fontweight='bold', pad=4)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return Image(buf, width=width * inch, height=height * inch)
    except Exception:
        return None


def _chart_margins(fin_data: dict, width: float = 5.5, height: float = 2.4) -> Image | None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
        dates = a_inc.get("dates", [])[:4]
        gm    = a_inc.get("gross_margin", [])[:4]
        om    = a_inc.get("operating_margin", [])[:4]
        nm    = a_inc.get("net_margin", [])[:4]

        if not dates or not gm:
            return None

        c = _mpl_colors()
        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')

        xs = range(len(dates))
        if any(v is not None for v in gm):
            ax.plot(xs, gm, 'o-', color=c['navy'],  linewidth=1.5, markersize=4, label='Gross Margin', zorder=3)
        if any(v is not None for v in om):
            ax.plot(xs, om, 's-', color=c['blue'],  linewidth=1.5, markersize=4, label='Op. Margin', zorder=3)
        if any(v is not None for v in nm):
            ax.plot(xs, nm, '^-', color=c['steel'], linewidth=1.5, markersize=4, label='Net Margin', zorder=3)

        ax.set_xticks(list(xs))
        ax.set_xticklabels(dates, fontsize=7)
        ax.yaxis.set_tick_params(labelsize=7)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0f}%'))
        ax.set_ylabel('%', fontsize=7, color=c['mgrey'])
        ax.tick_params(colors=c['mgrey'])
        ax.grid(axis='y', color=c['lgrey'], linewidth=0.5, zorder=0)
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(c['mgrey'])
        ax.legend(fontsize=7, framealpha=0, loc='upper left')
        ax.set_title('Margin Trends', fontsize=8, color=c['navy'],
                     fontweight='bold', pad=4)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return Image(buf, width=width * inch, height=height * inch)
    except Exception:
        return None


def _chart_football(stats: dict, dcf_result, comp_result, cov_result,
                    width: float = 6.0, height: float = 2.6) -> Image | None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        info = (stats or {}).get("info", {})
        px   = _sf(stats.get("current_price"))
        c    = _mpl_colors()

        dcf_lo = dcf_hi = None
        if dcf_result and not dcf_result.get("error"):
            tbl = dcf_result.get("sensitivity", {}).get("table", [])
            if tbl and len(tbl) >= 5 and len(tbl[0]) >= 5:
                dcf_lo = _sf(tbl[4][0])
                dcf_hi = _sf(tbl[0][4])

        wk52_lo = _sf(info.get("fiftyTwoWeekLow"))
        wk52_hi = _sf(info.get("fiftyTwoWeekHigh"))

        anal_lo = anal_hi = None
        if cov_result and not cov_result.get("error"):
            anal_lo = _sf(cov_result.get("low_target"))
            anal_hi = _sf(cov_result.get("high_target"))
            if anal_lo is None or anal_hi is None:
                mean_t = _sf(cov_result.get("mean_target"))
                if mean_t:
                    spread = _sf(cov_result.get("target_spread_pct")) or 20.0
                    anal_lo = round(mean_t * (1 - spread / 200), 2)
                    anal_hi = round(mean_t * (1 + spread / 200), 2)

        comp_lo = comp_hi = None
        eps = _sf(info.get("forwardEps")) or _sf(info.get("trailingEps"))
        if eps and eps > 0 and comp_result and not comp_result.get("error"):
            fpes = [_sf(p.get("fpe")) for p in comp_result.get("peers", [])
                    if _sf(p.get("fpe")) and _sf(p.get("fpe")) > 0]
            if fpes:
                comp_lo = round(min(fpes) * eps, 2)
                comp_hi = round(max(fpes) * eps, 2)

        bars = [
            ("DCF",             dcf_lo,   dcf_hi,   c['navy']),
            ("Comps-Implied",   comp_lo,  comp_hi,  c['steel']),
            ("52-Week Range",   wk52_lo,  wk52_hi,  c['blue']),
            ("Analyst Targets", anal_lo,  anal_hi,  c['gold']),
        ]

        all_vals = [v for b in bars for v in (b[1], b[2]) if v] + ([px] if px else [])
        if not all_vals:
            return None
        chart_min = min(all_vals) * 0.88
        chart_max = max(all_vals) * 1.10

        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_facecolor('white')
        ax.set_facecolor(c['lgrey'])

        y_pos = [3, 2, 1, 0]
        labels = [b[0] for b in bars]
        for i, (lbl, lo, hi, col) in enumerate(bars):
            if lo is not None and hi is not None and lo < hi:
                ax.barh(y_pos[i], hi - lo, left=lo, height=0.45, color=col,
                        zorder=3, alpha=0.9)
                ax.text(lo - 2, y_pos[i], f'${lo:,.0f}', ha='right', va='center',
                        fontsize=6.5, color=c['mgrey'])
                ax.text(hi + 2, y_pos[i], f'${hi:,.0f}', ha='left', va='center',
                        fontsize=6.5, color=c['mgrey'])
            else:
                ax.text((chart_min + chart_max) / 2, y_pos[i], 'N/A',
                        ha='center', va='center', fontsize=7, color=c['mgrey'],
                        style='italic')

        if px and chart_min < px < chart_max:
            ax.axvline(px, color=c['red'], linewidth=1.5, zorder=4)
            ax.text(px, 3.6, f'${px:,.2f}', ha='center', va='bottom',
                    fontsize=7, color=c['red'], fontweight='bold')

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=7.5)
        ax.set_xlim(chart_min, chart_max)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
        ax.tick_params(axis='x', labelsize=6.5, colors=c['mgrey'])
        ax.tick_params(axis='y', colors=c['mgrey'])
        ax.spines[['top', 'right', 'left']].set_visible(False)
        ax.spines['bottom'].set_color(c['mgrey'])
        ax.set_title('Valuation Football Field', fontsize=8, color=c['navy'],
                     fontweight='bold', pad=4)
        ax.grid(axis='x', color='white', linewidth=0.5, zorder=0)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return Image(buf, width=width * inch, height=height * inch)
    except Exception:
        return None


# ── Canvas page template callbacks ────────────────────────────────────────────

def _draw_cover_page(canvas, doc, *, ticker, company, rating, target, px,
                     mktcap, lo52, hi52, date_str):
    canvas.saveState()
    W, H = _PW, _PH

    # Full navy header band
    canvas.setFillColor(_NAVY)
    canvas.rect(0, H - 1.0*inch, W, 1.0*inch, fill=1, stroke=0)

    canvas.setFont(_SANS, 8.5)
    canvas.setFillColor(_WHITE)
    canvas.drawString(0.75*inch, H - 0.38*inch, _UC_HDR + "  —  Initiating Coverage")
    canvas.drawRightString(W - 0.75*inch, H - 0.38*inch, date_str)

    # UC logo placed below header band, left-aligned on cover
    import os as _os
    _logo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "uc_logo.png")
    if _os.path.exists(_logo_path):
        canvas.drawImage(_logo_path, 0.75*inch, H - 1.6*inch,
                         width=2.2*inch, height=0.52*inch,
                         preserveAspectRatio=True, mask="auto")

    # Company name
    canvas.setFont(_SANS_B, 32)
    canvas.setFillColor(_NAVY)
    canvas.drawCentredString(W/2, H - 1.85*inch, company)

    # Ticker / Exchange / Sector
    info_line = ticker
    canvas.setFont(_SANS, 13)
    canvas.setFillColor(_MGREY)
    canvas.drawCentredString(W/2, H - 2.2*inch, info_line)

    # Thin navy rule
    canvas.setStrokeColor(_NAVY)
    canvas.setLineWidth(0.75)
    canvas.line(0.75*inch, H - 2.5*inch, W - 0.75*inch, H - 2.5*inch)

    # Rating
    rc = _GREEN if rating == "BUY" else (_RED if rating == "SELL" else _MGREY)
    canvas.setFont(_SANS_B, 22)
    canvas.setFillColor(rc)
    canvas.drawCentredString(W/2, H - 3.0*inch, rating)

    # Target price
    canvas.setFont(_SANS_B, 14)
    canvas.setFillColor(_NAVY)
    canvas.drawCentredString(W/2, H - 3.4*inch, f"12-Month Price Target: {target}")

    # Thin divider
    canvas.setStrokeColor(_LGREY)
    canvas.setLineWidth(0.5)
    canvas.line(0.75*inch, H - 3.65*inch, W - 0.75*inch, H - 3.65*inch)

    # Key metrics row
    metrics = [
        ("Current Price", px),
        ("Market Cap", mktcap),
        ("52-Wk Range", f"{lo52} – {hi52}"),
    ]
    col_w = (W - 1.5*inch) / len(metrics)
    for i, (lbl, val) in enumerate(metrics):
        cx = 0.75*inch + col_w * i + col_w / 2
        canvas.setFont(_SANS, 8.5)
        canvas.setFillColor(_MGREY)
        canvas.drawCentredString(cx, H - 3.9*inch, lbl)
        canvas.setFont(_SANS_B, 12)
        canvas.setFillColor(_NAVY)
        canvas.drawCentredString(cx, H - 4.2*inch, val)

    # Analyst line
    canvas.setFont(_SANS, 9)
    canvas.setFillColor(_MGREY)
    canvas.drawCentredString(W/2, H - 4.7*inch, f"Analyst: {_ANALYST}")

    # Thin rule before footer
    canvas.setStrokeColor(_NAVY)
    canvas.setLineWidth(0.5)
    canvas.line(0.75*inch, 0.75*inch, W - 0.75*inch, 0.75*inch)

    canvas.setFont(_SANS, 7.5)
    canvas.setFillColor(_MGREY)
    canvas.drawCentredString(W/2, 0.45*inch, _CONF)

    canvas.restoreState()


def _draw_body_page(canvas, doc, *, ticker, company, rating):
    canvas.saveState()
    W, H = _PW, _PH

    # Narrow navy header bar
    canvas.setFillColor(_NAVY)
    canvas.rect(0, H - 0.38*inch, W, 0.38*inch, fill=1, stroke=0)

    canvas.setFont(_SANS, 7.5)
    canvas.setFillColor(_WHITE)
    canvas.drawString(0.75*inch, H - 0.25*inch, f"{company}  ({ticker})")
    canvas.drawRightString(W - 0.75*inch, H - 0.25*inch, _UC_HDR)

    # Footer rule
    canvas.setStrokeColor(_NAVY)
    canvas.setLineWidth(0.4)
    canvas.line(0.75*inch, 0.6*inch, W - 0.75*inch, 0.6*inch)

    canvas.setFont(_SANS, 7)
    canvas.setFillColor(_MGREY)
    canvas.drawString(0.75*inch, 0.4*inch, _CONF)
    canvas.drawRightString(W - 0.75*inch, 0.4*inch, f"Page {doc.page}")

    canvas.restoreState()


# ── Section builders (return lists of Flowable) ───────────────────────────────

_CW = _PW - _LM - _RM    # usable content width = 6.5 inches


def _hr() -> HRFlowable:
    return HRFlowable(width=_CW, thickness=0.4, color=_LGREY, spaceAfter=6, spaceBefore=6)


def _section_header(text: str, styles: dict) -> list:
    return [
        Spacer(1, 0.05*inch),
        Paragraph(text, styles["h1"]),
        HRFlowable(width=_CW, thickness=1, color=_NAVY, spaceAfter=6),
    ]


def _metrics_table_2col(pairs: list[tuple[str, str]]) -> Table:
    """Two-column label/value table styled as key metrics grid."""
    rows = []
    for i in range(0, len(pairs), 2):
        row = [pairs[i][0], pairs[i][1]]
        if i + 1 < len(pairs):
            row += [pairs[i+1][0], pairs[i+1][1]]
        else:
            row += ["", ""]
        rows.append(row)
    cw = [1.7*inch, 1.55*inch, 1.7*inch, 1.55*inch]
    ts = TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [_WHITE, _LGREY]),
        ('FONTNAME',       (0, 0), (-1, -1), _SANS),
        ('FONTSIZE',       (0, 0), (-1, -1), 8.5),
        ('FONTNAME',       (0, 0), (0, -1),  _SANS_B),
        ('FONTNAME',       (2, 0), (2, -1),  _SANS_B),
        ('TEXTCOLOR',      (0, 0), (0, -1),  _NAVY),
        ('TEXTCOLOR',      (2, 0), (2, -1),  _NAVY),
        ('TEXTCOLOR',      (1, 0), (1, -1),  _DGREY),
        ('TEXTCOLOR',      (3, 0), (3, -1),  _DGREY),
        ('GRID',           (0, 0), (-1, -1), 0.25, _MGREY),
        ('LEFTPADDING',    (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 5),
        ('TOPPADDING',     (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 3),
        ('ALIGN',          (1, 0), (1, -1),  'RIGHT'),
        ('ALIGN',          (3, 0), (3, -1),  'RIGHT'),
    ])
    return Table(rows, colWidths=cw, style=ts, hAlign='LEFT')


# ── Page 2: Executive Summary ─────────────────────────────────────────────────

def _section_exec_summary(styles: dict, stats: dict, fin_data: dict,
                          research, comp_result, cov_result, dcf_result) -> list:
    info   = stats.get("info", {})
    rating = _fallback_rating(research, cov_result)
    target = _fallback_target(research, cov_result)
    bulls  = _fallback_bulls(research, stats, fin_data, comp_result)
    cats   = _fallback_catalysts(research, stats, fin_data, comp_result, cov_result)
    bears  = _fallback_bears(research, stats, fin_data, dcf_result, comp_result)

    thesis = (research or {}).get("thesis") or {}
    verdict = thesis.get("verdict", "") if not thesis.get("_placeholder") else ""

    company = info.get("shortName") or info.get("longName") or stats.get("ticker", "")
    ticker  = stats.get("ticker", "")
    px      = stats.get("current_price")
    up_pct  = cov_result.get("upside_pct") if cov_result and not cov_result.get("error") else None

    # Build thesis paragraph (≤150 words, dense/specific)
    rating_uc = rating.upper()
    target_str = target if target != "—" else "—"
    up_str = _fpct(up_pct, plus=True) if up_pct else "—"
    fpe = _sf(info.get("forwardPE"), 1)
    peer_fpe = _sf(_sa(comp_result, "peer_medians", "fpe")) if comp_result and not comp_result.get("error") else None

    if verdict:
        thesis_text = verdict
    else:
        thesis_text = (
            f"We initiate coverage of {company} ({ticker}) with a {rating_uc} rating and "
            f"12-month price target of {target_str}, implying {up_str} upside from current levels. "
        )
        if bulls:
            thesis_text += (
                f"Our thesis rests on: (1) {bulls[0].split('—')[0].strip()}; "
            )
            if len(bulls) > 1:
                thesis_text += f"(2) {bulls[1].split('—')[0].strip()}. "
        if bears:
            thesis_text += f"Primary risk: {bears[0].split('—')[0].strip()}. "
        thesis_text += f"Initiating {rating_uc}."

    fpe_str  = f"{fpe:.1f}x" if fpe else "—"
    pe_ttm   = _sf(info.get("trailingPE"), 1)
    pe_str   = f"{pe_ttm:.1f}x" if pe_ttm else "—"
    mktcap   = _flarge(info.get("marketCap"))
    n_an     = cov_result.get("total_analysts") if cov_result and not cov_result.get("error") else None
    bull_rat = cov_result.get("bull_ratio") if cov_result and not cov_result.get("error") else None
    iv       = _fp(_sa(dcf_result, "valuation", "intrinsic")) if dcf_result and not dcf_result.get("error") else "—"

    metric_pairs = [
        ("Current Price",    _fp(px)),
        ("Price Target",     target_str),
        ("Rating",           rating_uc),
        ("Market Cap",       mktcap),
        ("P/E (TTM)",        pe_str),
        ("P/E (Forward)",    fpe_str),
        ("DCF Intrinsic",    iv),
        ("Analyst Coverage", f"{n_an} analysts" if n_an else "—"),
    ]
    if bull_rat is not None:
        metric_pairs[-1] = ("Bull Ratio", f"{bull_rat:.1f}%")

    # Rating style
    r_style_key = ("rating_buy" if rating_uc == "BUY" else
                   "rating_sell" if rating_uc == "SELL" else "rating_hold")

    story = []
    story += _section_header("Executive Summary", styles)

    story.append(Paragraph(rating_uc, styles[r_style_key]))
    story.append(Spacer(1, 0.06*inch))
    story.append(Paragraph(thesis_text, styles["body"]))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Key Metrics", styles["h2"]))
    story.append(_metrics_table_2col(metric_pairs))
    story.append(Spacer(1, 0.12*inch))

    story.append(Paragraph("Key Catalysts", styles["h2"]))
    for i, cat in enumerate(cats[:3], 1):
        story.append(Paragraph(f"{i}.  {cat}", styles["bullet"]))
    story.append(Spacer(1, 0.08*inch))

    story.append(Paragraph("Top Risks", styles["h2"]))
    for bear in bears[:2]:
        story.append(Paragraph(f"▸  {bear}", styles["bullet"]))

    return story


# ── Pages 3-4: Financial Analysis ─────────────────────────────────────────────

def _section_financials(styles: dict, stats: dict, fin_data: dict) -> list:
    info  = stats.get("info", {})
    a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
    a_cf  = (fin_data.get("cash_flow") or {}).get("annual") or {}
    bs    = fin_data.get("balance_sheet") or {}

    dates   = a_inc.get("dates", [])[:4]
    rev     = a_inc.get("revenue", [None]*4)[:4]
    gm      = a_inc.get("gross_margin", [None]*4)[:4]
    om      = a_inc.get("operating_margin", [None]*4)[:4]
    nm      = a_inc.get("net_margin", [None]*4)[:4]
    fcf     = a_cf.get("free_cash_flow", [None]*4)[:4]
    yoy_rev = a_inc.get("yoy_revenue", [None]*4)[:4]
    yoy_fcf = a_cf.get("yoy_fcf", [None]*4)

    story = []
    story.append(PageBreak())
    story += _section_header("Financial Analysis", styles)

    # Income statement table
    story.append(Paragraph("Income Statement Summary", styles["h2"]))
    n = len(dates)
    hdr = ["Metric"] + list(dates) + ["YoY"]
    col_w = [1.9*inch] + [1.1*inch] * n + [0.8*inch]
    rows = [hdr,
            ["Revenue"]         + [_fm(v) for v in rev]    + [_fpct(yoy_rev[0] if yoy_rev else None, plus=True)],
            ["Gross Margin"]    + [_pct_str(v) for v in gm]  + ["—"],
            ["Op. Margin"]      + [_pct_str(v) for v in om]  + ["—"],
            ["Net Margin"]      + [_pct_str(v) for v in nm]  + ["—"],
            ["Free Cash Flow"]  + [_fm(v) for v in fcf]    + [_fpct(yoy_fcf[0] if yoy_fcf else None, plus=True)],
            ]
    if sum(col_w) > _CW + 0.01:
        scale = _CW / sum(col_w)
        col_w = [c * scale for c in col_w]
    story.append(_tbl(rows, col_w))
    story.append(Spacer(1, 0.12*inch))

    # Charts — side by side
    ch_rev = _chart_revenue_fcf(fin_data, width=3.0, height=2.2)
    ch_mgn = _chart_margins(fin_data, width=3.0, height=2.2)
    if ch_rev or ch_mgn:
        chart_rows = [[ch_rev or "", ch_mgn or ""]]
        chart_tbl = Table(chart_rows, colWidths=[3.2*inch, 3.2*inch],
                          style=TableStyle([
                              ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                              ('VALIGN', (0,0), (-1,-1), 'TOP'),
                              ('LEFTPADDING', (0,0), (-1,-1), 2),
                              ('RIGHTPADDING', (0,0), (-1,-1), 2),
                          ]))
        story.append(chart_tbl)
        story.append(Paragraph("Left: Annual Revenue & FCF ($B). Right: Margin Trends (%).",
                                styles["caption"]))
    story.append(Spacer(1, 0.1*inch))

    # Key ratios table
    story.append(Paragraph("Balance Sheet & Valuation Highlights", styles["h2"]))
    fcf_v = a_cf.get("free_cash_flow", [None])
    fcf_latest = _sf(fcf_v[0]) if fcf_v else None
    mktcap_v = _sf(info.get("marketCap"))
    fcf_yield = round(fcf_latest / (mktcap_v / 1_000) * 100, 1) if fcf_latest and mktcap_v else None

    bs_pairs = [
        ("Cash & Equivalents",  _fm(bs.get("cash"))),
        ("Total Debt",          _fm(bs.get("total_debt"))),
        ("Net Debt",            _fm(bs.get("net_debt"))),
        ("Current Ratio",       str(_sf(bs.get("current_ratio"), 2)) if bs.get("current_ratio") else "—"),
        ("Debt / Equity",       str(_sf(bs.get("debt_to_equity"), 2)) if bs.get("debt_to_equity") else "—"),
        ("FCF Yield",           _fpct(fcf_yield) if fcf_yield else "—"),
        ("Total Assets",        _fm(bs.get("total_assets"))),
        ("Shareholders' Equity",_fm(bs.get("shareholders_equity"))),
    ]
    story.append(_metrics_table_2col(bs_pairs))

    return story


# ── Pages 5-6: Valuation ──────────────────────────────────────────────────────

def _section_valuation(styles: dict, stats: dict, fin_data: dict,
                       dcf_result, comp_result, cov_result, research) -> list:
    info = stats.get("info", {})
    story = []
    story.append(PageBreak())
    story += _section_header("Valuation", styles)

    # ── DCF summary ───────────────────────────────────────────────────────────
    story.append(Paragraph("DCF Model Summary", styles["h2"]))

    if not dcf_result or dcf_result.get("error"):
        story.append(Paragraph(
            f"DCF analysis unavailable: {(dcf_result or {}).get('error', 'No DCF data')}",
            styles["body_sm"]))
    else:
        inp = dcf_result.get("inputs", {})
        val = dcf_result.get("valuation", {})
        iv  = _fp(val.get("intrinsic"))
        px  = stats.get("current_price")
        up  = _fpct(val.get("upside_pct"), plus=True)
        ev  = _fm(val.get("ev_m"))
        tv  = f"{val.get('tv_pct', 0):.1f}%" if val.get("tv_pct") else "—"
        wacc = inp.get("wacc")
        tg   = inp.get("tg")
        beta = inp.get("beta")
        cagr = inp.get("rev_cagr")
        ebit_m = inp.get("ebit_margin")

        dcf_pairs = [
            ("WACC",              f"{wacc:.2f}%" if wacc else "—"),
            ("Terminal Growth",   f"{tg:.1f}%" if tg else "—"),
            ("Beta",              f"{beta:.2f}" if beta else "—"),
            ("Revenue CAGR",      f"{cagr:.1f}%" if cagr else "—"),
            ("EBIT Margin",       f"{ebit_m:.1f}%" if ebit_m else "—"),
            ("Forecast Horizon",  "5 Years"),
            ("Intrinsic Value",   iv),
            ("Implied Upside",    up),
            ("Enterprise Value",  ev),
            ("Terminal Val. %EV", tv),
        ]
        story.append(_metrics_table_2col(dcf_pairs))
        story.append(Spacer(1, 0.1*inch))

        # DCF sensitivity 3×3
        story.append(Paragraph("DCF Sensitivity — WACC × Terminal Growth Rate", styles["h2"]))
        tbl_data = dcf_result.get("sensitivity", {}).get("table", [])
        wacc_rng = dcf_result.get("sensitivity", {}).get("wacc_range", [])
        tg_rng   = dcf_result.get("sensitivity", {}).get("tg_range", [])

        if tbl_data and len(tbl_data) >= 5:
            ridx = [0, 2, 4]
            cidx = [0, 2, 4]
            hdr = ["WACC \\ g"] + [f"{tg_rng[c]:.1f}%" if c < len(tg_rng) else "—" for c in cidx]
            sens_rows = [hdr]
            for ri in ridx:
                w_lbl = f"{wacc_rng[ri]:.2f}%" if ri < len(wacc_rng) else "—"
                row = [w_lbl] + [_fp(tbl_data[ri][ci]) if ci < len(tbl_data[ri]) else "—"
                                  for ci in cidx]
                sens_rows.append(row)

            cw_s = [1.4*inch, 1.7*inch, 1.7*inch, 1.7*inch]
            center_extras = [
                ('BACKGROUND', (2, 2), (2, 2), _STEEL),
                ('TEXTCOLOR',  (2, 2), (2, 2), _WHITE),
                ('FONTNAME',   (2, 2), (2, 2), _SANS_B),
            ]
            story.append(_tbl(sens_rows, cw_s, extra=center_extras))
            story.append(Paragraph("Center cell = base case (WACC, terminal growth at current inputs).",
                                    styles["caption"]))
        story.append(Spacer(1, 0.12*inch))

    # ── Comps table ───────────────────────────────────────────────────────────
    story.append(Paragraph("Comparable Companies Analysis", styles["h2"]))

    ticker  = stats.get("ticker", "")
    tgt_fpe = _sf(info.get("forwardPE"), 1)
    tgt_pe  = _sf(info.get("trailingPE"), 1)

    comp_rows_r = (research or {}).get("comps", {}).get("comps", []) \
        if not ((research or {}).get("comps") or {}).get("_placeholder") else []

    if not comp_rows_r and comp_result and not comp_result.get("error"):
        for p in comp_result.get("peers", [])[:5]:
            comp_rows_r.append({
                "company": p.get("name", p.get("ticker", "—")),
                "ticker":  p.get("ticker", "—"),
                "ev_ebitda": None,
                "pe_fwd":  p.get("fpe"),
                "ev_rev":  None,
            })

    comp_hdr  = ["Company", "Ticker", "EV/EBITDA", "P/E (Fwd)", "EV/Revenue"]
    comp_rows = [comp_hdr,
                 [f"{info.get('shortName', ticker)} ◀", ticker, "—",
                  f"{tgt_fpe:.1f}x" if tgt_fpe else "—", "—"]]
    for r in comp_rows_r[:5]:
        def _mx(v): return f"{_sf(v,1):.1f}x" if _sf(v) else "—"
        comp_rows.append([
            r.get("company", "—"), r.get("ticker", "—"),
            _mx(r.get("ev_ebitda")), _mx(r.get("pe_fwd")), _mx(r.get("ev_rev")),
        ])
    cw_c = [2.3*inch, 0.85*inch, 1.1*inch, 1.1*inch, 1.15*inch]
    story.append(_tbl(comp_rows, cw_c, target_row=1))

    if comp_result and not comp_result.get("error"):
        med = comp_result.get("peer_medians", {})
        rks = comp_result.get("rankings", {})
        prem = rks.get("fpe_premium_pct")
        med_fpe = _sf(med.get("fpe"), 1)
        if prem is not None and med_fpe:
            direction = "premium" if prem > 0 else "discount"
            story.append(Paragraph(
                f"{ticker} trades at {tgt_fpe:.1f}x fwd P/E — "
                f"{abs(prem):.1f}% {direction} to peer median of {med_fpe:.1f}x.",
                styles["body_sm"]))

    story.append(Spacer(1, 0.12*inch))

    # ── Football field chart ──────────────────────────────────────────────────
    story.append(Paragraph("Valuation Football Field", styles["h2"]))
    ff_chart = _chart_football(stats, dcf_result, comp_result, cov_result,
                               width=6.0, height=2.6)
    if ff_chart:
        story.append(ff_chart)
        story.append(Paragraph(
            "Red line = current price. Bars show valuation range implied by each methodology.",
            styles["caption"]))
    else:
        story.append(Paragraph("Insufficient valuation data to render football field.", styles["body_sm"]))

    return story


# ── Pages 7-8: Research Analysis ─────────────────────────────────────────────

def _section_research(styles: dict, stats: dict, fin_data: dict,
                      research, comp_result, cov_result) -> list:
    info    = stats.get("info", {})
    ticker  = stats.get("ticker", "")
    company = info.get("shortName") or ticker
    story   = []
    story.append(PageBreak())
    story += _section_header("Research Analysis", styles)

    # ── Competitive position ──────────────────────────────────────────────────
    story.append(Paragraph("Competitive Position & Moat Assessment", styles["h2"]))
    ok_comp = comp_result and not comp_result.get("error")

    moat_text = ""
    if ok_comp:
        moat_text = comp_result.get("claude") or ""

    if not moat_text and ok_comp:
        rks  = comp_result.get("rankings", {})
        med  = comp_result.get("peer_medians", {})
        prem = rks.get("fpe_premium_pct")
        prem_str = (f"Trading at {abs(prem):.1f}% {'premium' if prem and prem>0 else 'discount'} "
                    f"to peer median fwd P/E. ") if prem is not None else ""
        rank_map = {"top": "above peer median", "mid": "in-line with peers", "bot": "below peer median"}
        rev_rank = rank_map.get(rks.get("rev_growth", "mid"), "—")
        gm_rank  = rank_map.get(rks.get("gross_margin", "mid"), "—")
        om_rank  = rank_map.get(rks.get("op_margin", "mid"), "—")
        moat_text = (f"{prem_str}Revenue growth is {rev_rank}; gross margin is "
                     f"{gm_rank}; operating margin is {om_rank}.")

    if not moat_text:
        moat_text = "Competitive analysis data unavailable."

    story.append(Paragraph(moat_text[:800], styles["body"]))
    story.append(Spacer(1, 0.1*inch))

    # Peer metrics table
    if ok_comp:
        peers = comp_result.get("peers", [])[:4]
        tgt   = comp_result.get("target", {})
        if peers and tgt:
            story.append(Paragraph("Peer Comparison — Key Metrics", styles["h3"]))
            p_hdr  = ["Company", "Rev Growth", "Gross Margin", "Op. Margin", "ROE", "Fwd P/E"]
            def _pv(d, k): v = d.get(k); return f"{v:.1f}%" if v is not None else "—"
            def _fx(d, k): v = d.get(k); return f"{v:.1f}x" if v is not None else "—"
            p_rows = [p_hdr,
                      [f"{tgt.get('name', ticker)} ◀",
                       _pv(tgt,'rev_growth'), _pv(tgt,'gross_margin'),
                       _pv(tgt,'op_margin'),  _pv(tgt,'roe'), _fx(tgt,'fpe')]]
            for p in peers:
                p_rows.append([p.get("name", p.get("ticker","—")),
                                _pv(p,'rev_growth'), _pv(p,'gross_margin'),
                                _pv(p,'op_margin'),  _pv(p,'roe'), _fx(p,'fpe')])
            cw_p = [1.8*inch, 0.95*inch, 1.05*inch, 0.95*inch, 0.85*inch, 0.9*inch]
            story.append(_tbl(p_rows, cw_p, target_row=1))
    story.append(Spacer(1, 0.12*inch))

    # ── Analyst coverage ──────────────────────────────────────────────────────
    story.append(Paragraph("Analyst Coverage", styles["h2"]))
    ok_cov = cov_result and not cov_result.get("error")
    if ok_cov:
        rat      = cov_result.get("consensus_rating", "—")
        n_an     = cov_result.get("total_analysts", 0)
        mean_t   = _fp(cov_result.get("mean_target"))
        hi_t     = _fp(cov_result.get("high_target"))
        lo_t     = _fp(cov_result.get("low_target"))
        up       = _fpct(cov_result.get("upside_pct"), plus=True)
        bull_rat = cov_result.get("bull_ratio")
        buys     = cov_result.get("buy_count", 0)
        holds    = cov_result.get("hold_count", 0)
        sells    = cov_result.get("sell_count", 0)

        cov_pairs = [
            ("Consensus Rating",  rat),
            ("Analysts Covering", str(n_an)),
            ("Mean Price Target", mean_t),
            ("Implied Upside",    up),
            ("Target High",       hi_t),
            ("Target Low",        lo_t),
            ("Buy Ratings",       str(buys)),
            ("Hold Ratings",      str(holds)),
        ]
        if bull_rat is not None:
            cov_pairs.append(("Bull Ratio", f"{bull_rat:.1f}%"))
            cov_pairs.append(("Sell Ratings", str(sells)))
        else:
            cov_pairs.append(("Sell Ratings", str(sells)))
            cov_pairs.append(("Distribution", "Breakdown unavailable"))

        story.append(_metrics_table_2col(cov_pairs))

        # Recent targets table
        recents = cov_result.get("recent_targets", [])[:5]
        if recents:
            story.append(Spacer(1, 0.08*inch))
            story.append(Paragraph("Recent Price Target Actions", styles["h3"]))
            rt_hdr  = ["Firm", "Analyst", "Target", "Date"]
            rt_rows = [rt_hdr]
            for r in recents:
                rt_rows.append([
                    r.get("firm", "—")[:22],
                    r.get("analyst", "—")[:18],
                    _fp(r.get("price_target")),
                    r.get("date", "—")[:10],
                ])
            cw_rt = [2.4*inch, 1.8*inch, 1.15*inch, 1.15*inch]
            story.append(_tbl(rt_rows, cw_rt))
    else:
        story.append(Paragraph("Analyst coverage data unavailable.", styles["body_sm"]))
    story.append(Spacer(1, 0.12*inch))

    # ── Investment thesis — full bull and bear ────────────────────────────────
    story.append(Paragraph("Investment Thesis — Bull Case", styles["h2"]))
    bulls = _fallback_bulls(research, stats, fin_data, comp_result)
    for b in bulls:
        story.append(Paragraph(f"▸  {b}", styles["bullet"]))

    story.append(Spacer(1, 0.08*inch))
    story.append(Paragraph("Investment Thesis — Bear Case", styles["h2"]))
    bears_full = _fallback_bears(research, stats, fin_data, None, comp_result)
    for b in bears_full:
        story.append(Paragraph(f"▸  {b}", styles["bullet"]))

    # Research earnings preview if available
    earnings = (research or {}).get("earnings") or {}
    if earnings and not earnings.get("_placeholder"):
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph("Earnings Preview", styles["h2"]))
        summary = earnings.get("summary", "")
        if summary:
            story.append(Paragraph(summary[:800], styles["body"]))
        ests = cov_result.get("estimates", []) if ok_cov else []
        if ests:
            story.append(Spacer(1, 0.06*inch))
            story.append(Paragraph("Analyst Estimates", styles["h3"]))
            est_hdr  = ["Quarter", "EPS Est.", "EPS High", "EPS Low", "Rev Est.", "N Analysts"]
            est_rows = [est_hdr]
            for e in ests[:4]:
                est_rows.append([
                    e.get("date", "—"),
                    _fp(e.get("eps_est")),
                    _fp(e.get("eps_high")),
                    _fp(e.get("eps_low")),
                    _fm(e.get("rev_est")),
                    str(e.get("n_analysts") or "—"),
                ])
            cw_e = [1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.35*inch, 1.15*inch]
            story.append(_tbl(est_rows, cw_e))

    return story


# ── Page 9: Risks ─────────────────────────────────────────────────────────────

def _section_risks(styles: dict, stats: dict, fin_data: dict,
                   research, dcf_result, comp_result, cov_result) -> list:
    story = []
    story.append(PageBreak())
    story += _section_header("Risk Analysis", styles)

    bears = _fallback_bears(research, stats, fin_data, dcf_result, comp_result)

    # Build risk entries: probability and mitigant heuristics
    risk_entries = []
    for i, risk in enumerate(bears):
        # Infer probability from language
        rtext_lo = risk.lower()
        if any(w in rtext_lo for w in ("compression", "dcf", "intrinsic", "priced")):
            prob, mag = "High", "High"
        elif any(w in rtext_lo for w in ("deceleration", "slowdown", "disruption")):
            prob, mag = "Medium", "High"
        else:
            prob, mag = "Medium", "Medium"
        # Mitigant
        if "valuation" in rtext_lo or "p/e" in rtext_lo.lower():
            mitigant = "Services revenue mix (~25% of revenue) justifies premium to hardware-only peers; ecosystem switching costs support duration."
        elif "dcf" in rtext_lo or "intrinsic" in rtext_lo:
            mitigant = "Bull-case scenario assumptions (higher FCF growth, lower discount rate) close the gap; strong buyback program supports floor."
        else:
            mitigant = "Diversified revenue streams and balance sheet flexibility provide operational buffer."
        risk_entries.append((risk, prob, mag, mitigant))

    # Add generic 4th risk if fewer than 4
    if len(risk_entries) < 4:
        risk_entries.append((
            "Macro / Rate Sensitivity — multiple compression risk if rates remain elevated above 4.5%; historical 5-year average P/E of 28x vs. current 36x implies 22% downside on reversion alone",
            "Medium", "High",
            "Services mix shift diversifies revenue away from hardware cycles; sticky ecosystem provides defensive characteristics vs. pure-play hardware peers."
        ))

    risk_hdr  = ["Risk", "Probability", "Magnitude", "Mitigant"]
    risk_rows = [risk_hdr]
    for risk, prob, mag, mitigant in risk_entries[:4]:
        risk_rows.append([risk[:200], prob, mag, mitigant[:200]])

    cw_r = [2.4*inch, 0.85*inch, 0.85*inch, 2.4*inch]
    story.append(_tbl(risk_rows, cw_r))
    story.append(Spacer(1, 0.14*inch))

    # Scenario analysis
    story.append(Paragraph("Scenario Analysis — 12-Month Price Target", styles["h2"]))
    px = _sf(stats.get("current_price"))
    mt = _sf(cov_result.get("mean_target") if cov_result and not cov_result.get("error") else None)
    iv = _sf(_sa(dcf_result, "valuation", "intrinsic")) if dcf_result and not dcf_result.get("error") else None

    if mt and px:
        bull_tgt  = round(mt * 1.15, 2)
        base_tgt  = mt
        bear_tgt  = max(round(px * 0.75, 2), iv or round(px * 0.65, 2))
    elif iv and px:
        base_tgt  = mt or round((px + iv)/2, 2)
        bull_tgt  = round(px * 1.10, 2)
        bear_tgt  = iv
    else:
        bull_tgt = base_tgt = bear_tgt = None

    def _up(t): return _fpct(((t - px) / px * 100) if (t and px) else None, plus=True)

    scen_hdr  = ["Scenario", "Price Target", "Upside / Downside", "Key Assumption"]
    scen_rows = [
        scen_hdr,
        ["Bull", _fp(bull_tgt), _up(bull_tgt),
         "Services ASP expansion + margin re-rating to 35x P/E; FCF CAGR accelerates to 15%"],
        ["Base", _fp(base_tgt), _up(base_tgt),
         "Consensus revenue growth; margins stable; multiple holds at current levels"],
        ["Bear", _fp(bear_tgt), _up(bear_tgt),
         "Multiple compression to 28x (5-yr avg); revenue growth decelerates to 4%; DCF floor"],
    ]
    cw_sc = [0.9*inch, 1.1*inch, 1.25*inch, 3.25*inch]
    extra_sc = [
        ('TEXTCOLOR', (0,1), (-1,1), _GREEN),
        ('TEXTCOLOR', (0,3), (-1,3), _RED),
        ('FONTNAME',  (0,1), (-1,1), _SANS_B),
        ('FONTNAME',  (0,3), (-1,3), _SANS_B),
    ]
    story.append(_tbl(scen_rows, cw_sc, extra=extra_sc))

    return story


# ── Page 10: Appendix ─────────────────────────────────────────────────────────

def _section_appendix(styles: dict, stats: dict, fin_data: dict,
                       dcf_result) -> list:
    a_inc = (fin_data.get("income_statement") or {}).get("annual") or {}
    a_cf  = (fin_data.get("cash_flow") or {}).get("annual") or {}
    bs    = fin_data.get("balance_sheet") or {}

    dates  = a_inc.get("dates", [])[:4]
    story  = []
    story.append(PageBreak())
    story += _section_header("Appendix — Full Financial Statements", styles)

    # Full income statement
    story.append(Paragraph("A1. Income Statement (Annual)", styles["h2"]))
    rev = a_inc.get("revenue", [None]*4)[:4]
    gp  = a_inc.get("gross_profit", [None]*4)[:4]
    oi  = a_inc.get("operating_income", [None]*4)[:4]
    ni  = a_inc.get("net_income", [None]*4)[:4]
    gm  = a_inc.get("gross_margin", [None]*4)[:4]
    om  = a_inc.get("operating_margin", [None]*4)[:4]
    nm  = a_inc.get("net_margin", [None]*4)[:4]
    yoy_r = a_inc.get("yoy_revenue", [None]*4)[:4]
    yoy_n = a_inc.get("yoy_ni", [None]*4)[:4]

    n    = len(dates)
    hdr  = [""] + list(dates)
    cw_a = [2.1*inch] + [(_CW - 2.1*inch) / n] * n

    inc_rows = [hdr,
                ["Revenue ($M)"]     + [_fm(v) for v in rev],
                ["Gross Profit ($M)"]+ [_fm(v) for v in gp],
                ["Gross Margin"]     + [_pct_str(v) for v in gm],
                ["Op. Income ($M)"]  + [_fm(v) for v in oi],
                ["Op. Margin"]       + [_pct_str(v) for v in om],
                ["Net Income ($M)"]  + [_fm(v) for v in ni],
                ["Net Margin"]       + [_pct_str(v) for v in nm],
                ["YoY Revenue"]      + [_fpct(v, plus=True) for v in yoy_r],
                ["YoY Net Income"]   + [_fpct(v, plus=True) for v in yoy_n],
                ]
    story.append(_tbl(inc_rows, cw_a))
    story.append(Spacer(1, 0.1*inch))

    # Balance sheet
    story.append(Paragraph("A2. Balance Sheet Highlights", styles["h2"]))
    bs_rows = [
        [""],
        ["Total Assets ($M)",         _fm(bs.get("total_assets"))],
        ["Total Liabilities ($M)",     _fm(bs.get("total_liabilities"))],
        ["Shareholders' Equity ($M)",  _fm(bs.get("shareholders_equity"))],
        ["Cash ($M)",                  _fm(bs.get("cash"))],
        ["Total Debt ($M)",            _fm(bs.get("total_debt"))],
        ["Net Debt ($M)",              _fm(bs.get("net_debt"))],
        ["Current Ratio",              str(_sf(bs.get("current_ratio"), 2)) or "—"],
        ["Debt / Equity",              str(_sf(bs.get("debt_to_equity"), 2)) or "—"],
    ]
    bs_hdr = [["Metric", "Latest"]]
    cw_bs  = [3.5*inch, 3.0*inch]
    story.append(_tbl(bs_hdr + bs_rows[1:], cw_bs))
    story.append(Spacer(1, 0.1*inch))

    # Cash flow
    story.append(Paragraph("A3. Cash Flow Statement (Annual)", styles["h2"]))
    ocf = a_cf.get("operating_cash_flow", [None]*4)[:4]
    cap = a_cf.get("capital_expenditure", [None]*4)[:4]
    fcf = a_cf.get("free_cash_flow", [None]*4)[:4]
    fcfm = a_cf.get("fcf_margin", [None]*4)[:4]

    cf_rows = [hdr,
               ["Op. Cash Flow ($M)"] + [_fm(v) for v in ocf],
               ["CapEx ($M)"]         + [_fm(v) for v in cap],
               ["Free Cash Flow ($M)"]+ [_fm(v) for v in fcf],
               ["FCF Margin"]         + [_pct_str(v) for v in fcfm],
               ]
    story.append(_tbl(cf_rows, cw_a))
    story.append(Spacer(1, 0.1*inch))

    # Full 5×5 DCF sensitivity
    if dcf_result and not dcf_result.get("error"):
        sens     = dcf_result.get("sensitivity", {})
        full_tbl = sens.get("table", [])
        wacc_rng = sens.get("wacc_range", [])
        tg_rng   = sens.get("tg_range", [])

        if full_tbl and len(full_tbl) >= 3:
            story.append(Paragraph("A4. DCF Sensitivity — Full 5×5 Table", styles["h2"]))
            n_cols = len(full_tbl[0]) if full_tbl else 0
            f_hdr  = ["WACC \\ g"] + [f"{g:.1f}%" if g else "—" for g in tg_rng[:n_cols]]
            f_rows = [f_hdr]
            for ri, row in enumerate(full_tbl):
                w = f"{wacc_rng[ri]:.2f}%" if ri < len(wacc_rng) else "—"
                f_rows.append([w] + [_fp(v) for v in row])
            n_s_cols = len(f_hdr)
            cw_s5 = [1.2*inch] + [(_CW - 1.2*inch) / (n_s_cols - 1)] * (n_s_cols - 1)
            center_ri = len(full_tbl) // 2 + 1
            center_ci = n_cols // 2 + 1
            s5_extra = [
                ('BACKGROUND', (center_ci, center_ri), (center_ci, center_ri), _STEEL),
                ('TEXTCOLOR',  (center_ci, center_ri), (center_ci, center_ri), _WHITE),
            ]
            story.append(_tbl(f_rows, cw_s5, extra=s5_extra))

    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Source: yfinance, Financial Modeling Prep (FMP). Analysis generated by automated pipeline. "
        "This report is for informational purposes only and does not constitute investment advice.",
        styles["disclaimer"]))

    return story


# ── Document assembly ─────────────────────────────────────────────────────────

class _UCDoc(BaseDocTemplate):
    def __init__(self, path: str, cover_kw: dict, body_kw: dict, **kw):
        super().__init__(path, **kw)
        self._cover_kw = cover_kw
        self._body_kw  = body_kw

        body_frame = Frame(
            _LM, _BM + 0.25*inch,
            _PW - _LM - _RM,
            _PH - _TM - _BM - 0.25*inch - 0.45*inch,  # clearance for header + footer
            id='body',
        )
        cover_frame = Frame(_LM, _BM, _PW - _LM - _RM, _PH - _TM - _BM, id='cover')

        self.addPageTemplates([
            PageTemplate(id='cover',  frames=[cover_frame],
                         onPage=self._on_cover),
            PageTemplate(id='body',   frames=[body_frame],
                         onPage=self._on_body),
        ])

    def _on_cover(self, canvas, doc):
        _draw_cover_page(canvas, doc, **self._cover_kw)

    def _on_body(self, canvas, doc):
        _draw_body_page(canvas, doc, **self._body_kw)


# ── Entry point ───────────────────────────────────────────────────────────────

def run_pdf(ticker: str, stats: dict, fin_data: dict,
            dcf_result: dict | None = None,
            research:   dict | None = None,
            comp_result: dict | None = None,
            cov_result:  dict | None = None,
            out_path: str = "") -> dict:
    """Build a UC Lindner equity research PDF. Never raises."""
    try:
        info    = stats.get("info", {})
        company = info.get("shortName") or info.get("longName") or ticker
        rating  = _fallback_rating(research, cov_result)
        target  = _fallback_target(research, cov_result)
        px      = _fp(stats.get("current_price"))
        mktcap  = _flarge(info.get("marketCap"))
        lo52    = _fp(info.get("fiftyTwoWeekLow"))
        hi52    = _fp(info.get("fiftyTwoWeekHigh"))
        date_str = _date.today().strftime("%B %d, %Y")

        cover_kw = dict(ticker=ticker, company=company, rating=rating,
                        target=target, px=px, mktcap=mktcap,
                        lo52=lo52, hi52=hi52, date_str=date_str)
        body_kw  = dict(ticker=ticker, company=company, rating=rating)

        doc = _UCDoc(
            out_path,
            cover_kw=cover_kw,
            body_kw=body_kw,
            pagesize=letter,
            leftMargin=_LM, rightMargin=_RM,
            topMargin=_TM,  bottomMargin=_BM,
            title=f"{company} ({ticker}) — University of Cincinnati Equity Research",
            author=_ANALYST,
            subject="Initiating Coverage",
        )

        styles = _build_styles()

        story = []
        # Page 1: cover drawn entirely by canvas callback
        story.append(Spacer(1, 0.01*inch))        # triggers first page
        story.append(NextPageTemplate('body'))
        story.append(PageBreak())

        # Pages 2–10: content
        story += _section_exec_summary(
            styles, stats, fin_data, research, comp_result, cov_result, dcf_result)
        story += _section_financials(styles, stats, fin_data)
        story += _section_valuation(
            styles, stats, fin_data, dcf_result, comp_result, cov_result, research)
        story += _section_research(
            styles, stats, fin_data, research, comp_result, cov_result)
        story += _section_risks(
            styles, stats, fin_data, research, dcf_result, comp_result, cov_result)
        story += _section_appendix(styles, stats, fin_data, dcf_result)

        doc.build(story)
        return {"error": None, "path": out_path}

    except Exception as exc:
        import traceback
        return {"error": str(exc), "traceback": traceback.format_exc()}
