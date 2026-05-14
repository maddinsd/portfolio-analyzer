from __future__ import annotations

import math
import re
from datetime import date as _date_type

import openpyxl
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.legend import Legend
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ── Design system ─────────────────────────────────────────────────────────────
_F        = "Calibri"

_NAVY     = "003366"   # deep navy  – primary headers
_BLUE     = "1F4E79"   # mid blue   – section sub-headers
_STEEL    = "2D5F8A"   # steel blue – column headers
_WHITE    = "FFFFFF"
_ROW_ALT  = "EFF3F9"   # very light blue-grey – alternating row
_LBL_BG   = "E4EDF7"   # light blue – label cell background
_LBL_ALT  = "D6E4F0"   # slightly darker label bg for alt rows
_BORD_CLR = "C2CBD5"   # border colour
_GRN_BG   = "E2F0D9";  _GRN_FG = "375623"
_RED_BG   = "FFE0E0";  _RED_FG = "9C0006"
_SUBTITLE = "EAF0F7"   # subtitle bar

_THIN   = Side(style="thin", color=_BORD_CLR)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _fill(c: str) -> PatternFill:
    return PatternFill("solid", start_color=c, end_color=c)


def _f(size=10, bold=False, color=None) -> Font:
    return Font(name=_F, size=size, bold=bold, color=color or "000000")


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*",     r"\1", text)
    return text.strip()


# ── Column auto-fit ───────────────────────────────────────────────────────────

def _auto_fit(ws, min_w: int = 9, max_w: int = 55) -> None:
    """Fit column widths to content, skipping merged-cell spans."""
    skip: set[tuple[int, int]] = set()
    for mr in ws.merged_cells.ranges:
        for r, c in mr.cells:
            if (r, c) != (mr.min_row, mr.min_col):
                skip.add((r, c))
        if mr.max_col > mr.min_col:               # anchor of multi-col merge
            skip.add((mr.min_row, mr.min_col))

    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if (cell.row, cell.column) in skip or cell.value is None:
                continue
            L = len(str(cell.value))
            if cell.font and cell.font.bold:
                L = int(L * 1.12)
            widths[cell.column] = max(widths.get(cell.column, min_w), L + 3)

    for col_idx, w in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = max(min_w, min(max_w, w))


# ── Snapshot sheet ────────────────────────────────────────────────────────────

def _safe_fmt(val, decimals: int = 2, pct: bool = False, mult=None) -> str:
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "N/A"
    if mult:
        val = val * mult
    return f"{val:.{decimals}f}%" if pct else f"{val:.{decimals}f}"


def _large_fmt(val) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "N/A"
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= threshold:
            return f"${v / threshold:.2f}{suffix}"
    return f"${v:.2f}"


def _snap_lbl(cell, text: str, alt: bool = False) -> None:
    cell.value = text
    cell.font  = _f(10, bold=True)
    cell.fill  = _fill(_LBL_ALT if alt else _LBL_BG)
    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    cell.border = _BORDER


def _snap_val(cell, text: str, positive_green: bool = False, alt: bool = False) -> None:
    cell.value = text
    cell.alignment = Alignment(horizontal="right", vertical="center")
    cell.border = _BORDER
    if positive_green and isinstance(text, str) and text not in ("N/A", "—"):
        try:
            n = float(text.replace("%", "").replace("$", "").replace(",", "")
                      .replace("T", "").replace("B", "").replace("M", ""))
            if n > 0:
                cell.font = _f(10, color=_GRN_FG); cell.fill = _fill(_GRN_BG); return
            if n < 0:
                cell.font = _f(10, color=_RED_FG); cell.fill = _fill(_RED_BG); return
        except ValueError:
            pass
    cell.font = _f(10)
    cell.fill = _fill(_ROW_ALT if alt else _WHITE)


def _snap_section(ws, row: int, text: str, ncols: int = 4) -> None:
    ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
    c = ws.cell(row=row, column=1)
    c.value = text
    c.font  = _f(10, bold=True, color=_WHITE)
    c.fill  = _fill(_BLUE)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 22


def _build_snapshot_sheet(wb, ticker: str, stats: dict) -> None:
    ws   = wb.create_sheet("Snapshot")
    info = stats["info"]
    f, fl = _safe_fmt, _large_fmt

    # Title
    ws.merge_cells("A1:D1")
    t = ws["A1"]
    t.value = f"{ticker}   ·   Stock Snapshot"
    t.font  = _f(14, bold=True, color=_WHITE)
    t.fill  = _fill(_NAVY)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Date bar
    ws.merge_cells("A2:D2")
    s = ws["A2"]
    s.value = f"As of {_date_type.today().strftime('%B %d, %Y')}"
    s.font  = _f(9, color="5A6B7B")
    s.fill  = _fill(_SUBTITLE)
    s.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16

    sections = [
        ("PRICE & PERFORMANCE", True, [
            ("Current Price",   f"${stats['current_price']:.2f}",           "Prev Close",         f"${f(info.get('previousClose'))}"),
            ("6mo Return",      f(stats["stock_return_6mo"],  pct=True),    "S&P 500 6mo Return", f(stats["sp500_return_6mo"], pct=True)),
            ("Relative Return", f(stats["relative_return"],   pct=True),    "Annualized Vol",     f(stats["volatility_annualized"], pct=True)),
            ("52W High",        f"${f(info.get('fiftyTwoWeekHigh'))}",       "52W Low",            f"${f(info.get('fiftyTwoWeekLow'))}"),
            ("From 52W High",   f(stats["pct_from_52w_high"], pct=True),    "From 52W Low",       f(stats["pct_from_52w_low"], pct=True)),
            ("50-Day MA",       f"${f(info.get('fiftyDayAverage'))}",        "200-Day MA",         f"${f(info.get('twoHundredDayAverage'))}"),
        ]),
        ("VALUATION", False, [
            ("Trailing P/E",  f(info.get("trailingPE")),   "Forward P/E", f(info.get("forwardPE"))),
            ("Price / Book",  f(info.get("priceToBook")),  "Market Cap",  fl(info.get("marketCap"))),
            ("EPS (TTM)",     f(info.get("trailingEps")),  "EPS (Fwd)",   f(info.get("forwardEps"))),
        ]),
        ("FUNDAMENTALS", True, [
            ("Total Revenue",  fl(info.get("totalRevenue")),                             "Revenue Growth YoY", f(stats["revenue_growth_yoy"], pct=True)),
            ("Gross Margin",   f(info.get("grossMargins"),  mult=100, pct=True),         "Operating Margin",   f(info.get("operatingMargins"), mult=100, pct=True)),
            ("Net Margin",     f(info.get("profitMargins"), mult=100, pct=True),         "Free Cash Flow",     fl(info.get("freeCashflow"))),
            ("Total Debt",     fl(info.get("totalDebt")),                                "Dividend Yield",     f(info.get("dividendYield"), pct=True)),
        ]),
        ("ANALYST CONSENSUS", False, [
            ("Rating  (1 = Strong Buy)", f(info.get("recommendationMean")), "Price Target", f"${f(info.get('targetMeanPrice'))}"),
            ("# of Analysts",           str(info.get("numberOfAnalystOpinions") or "N/A"), "Sector",  info.get("sector") or "N/A"),
            ("Industry",                info.get("industry") or "N/A",                     "",        ""),
        ]),
    ]

    row = 3
    for section_name, use_color, rows_data in sections:
        ws.row_dimensions[row].height = 5          # thin spacer
        row += 1
        _snap_section(ws, row, section_name)
        row += 1
        alt = False
        for ll, lv, rl, rv in rows_data:
            _snap_lbl(ws.cell(row=row, column=1), ll, alt=alt)
            _snap_val(ws.cell(row=row, column=2), lv, positive_green=use_color, alt=alt)
            if rl:
                _snap_lbl(ws.cell(row=row, column=3), rl, alt=alt)
                _snap_val(ws.cell(row=row, column=4), rv, positive_green=use_color, alt=alt)
            ws.row_dimensions[row].height = 18
            row += 1
            alt = not alt

    _auto_fit(ws, min_w=14)


# ── Price Chart sheet ─────────────────────────────────────────────────────────

def _build_chart_sheet(wb, ticker: str, price_history, sp500_history) -> None:
    ws = wb.create_sheet("Price Chart")

    stock_close = price_history["Close"].reset_index()
    sp_close    = sp500_history["Close"].reset_index()
    stock_close.columns = ["Date", "Close"]
    sp_close.columns    = ["Date", "Close"]

    stock_idx = (stock_close["Close"] / stock_close["Close"].iloc[0] * 100).round(2)
    sp_idx    = (sp_close["Close"]    / sp_close["Close"].iloc[0]    * 100).round(2)

    # Column headers
    for ci, label in enumerate(["Date", ticker, "S&P 500"], start=1):
        c = ws.cell(row=1, column=ci)
        c.value = label
        c.font  = _f(10, bold=True, color=_WHITE)
        c.fill  = _fill(_NAVY)
        c.alignment = Alignment(horizontal="left" if ci == 1 else "center", vertical="center")
        c.border = _BORDER
    ws.row_dimensions[1].height = 22

    n = len(stock_idx)
    for i in range(n):
        d = stock_close["Date"].iloc[i]
        try:
            lbl = d.strftime("%b '%y") if hasattr(d, "strftime") else str(d)[:10]
        except Exception:
            lbl = str(d)[:10]

        ws.cell(row=i + 2, column=1).value = lbl
        ws.cell(row=i + 2, column=2).value = float(stock_idx.iloc[i])
        if i < len(sp_idx):
            ws.cell(row=i + 2, column=3).value = float(sp_idx.iloc[i])

    all_v = list(stock_idx) + list(sp_idx)
    pad   = (max(all_v) - min(all_v)) * 0.08
    y_min = round(max(0.0, min(all_v) - pad), 1)
    y_max = round(max(all_v) + pad, 1)

    chart = LineChart()
    chart.title         = f"{ticker} vs. S&P 500  —  6-Month Relative Performance (Indexed to 100)"
    chart.style         = 10
    chart.y_axis.title  = "Indexed Value  (Base = 100)"
    chart.x_axis.title  = "Date"
    chart.width         = 32
    chart.height        = 18
    chart.y_axis.numFmt = "0.0"
    chart.y_axis.scaling.min = y_min
    chart.y_axis.scaling.max = y_max
    chart.x_axis.tickLblSkip = 21          # ~one label per month

    # Explicit y-axis gridlines
    try:
        from openpyxl.chart.axis import ChartLines
        chart.y_axis.majorGridlines = ChartLines()
    except Exception:
        pass

    # Legend below the plot
    legend          = Legend()
    legend.position = "b"
    legend.overlay  = False
    chart.legend    = legend

    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=n + 1), titles_from_data=True)
    chart.add_data(Reference(ws, min_col=3, min_row=1, max_row=n + 1), titles_from_data=True)

    for s in chart.series:
        s.smooth = True

    chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n + 1))
    ws.add_chart(chart, "E2")

    _auto_fit(ws, min_w=8, max_w=16)


# ── Analysis sheet ────────────────────────────────────────────────────────────

def _build_analysis_sheet(wb, markdown: str) -> None:
    ws    = wb.create_sheet("Analysis")
    lines = markdown.split("\n")

    # Pre-scan table column widths
    tbl_max = [0, 0, 0]
    for line in lines:
        if not line.startswith("|") or re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        cols = [_clean(c) for c in line.strip("|").split("|")]
        for idx, val in enumerate(cols[:3]):
            tbl_max[idx] = max(tbl_max[idx], len(val))

    col_b = max(min(max(tbl_max[0], 30) + 4, 58), 42)
    col_c = min(tbl_max[1] + 4, 32) if tbl_max[1] else 26
    col_d = min(tbl_max[2] + 4, 28) if tbl_max[2] else 20
    text_w = col_b + col_c + col_d

    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = col_b
    ws.column_dimensions["C"].width = col_c
    ws.column_dimensions["D"].width = col_d

    row   = 1
    i     = 0
    first = True

    while i < len(lines):
        line = lines[i]

        # H1 — report title
        if line.startswith("# "):
            ws.merge_cells(f"A{row}:D{row}")
            c = ws.cell(row=row, column=1)
            c.value = _clean(line[2:])
            c.font  = _f(14, bold=True, color=_WHITE)
            c.fill  = _fill(_NAVY)
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[row].height = 40
            row += 1
            ws.row_dimensions[row].height = 14   # spacer
            row += 1
            i += 1

        # H2 — section header
        elif line.startswith("## "):
            if not first:
                ws.row_dimensions[row].height = 10
                row += 1
            first = False
            ws.cell(row=row, column=1).fill = _fill(_BLUE)   # left accent sliver
            ws.merge_cells(f"B{row}:D{row}")
            c = ws.cell(row=row, column=2)
            c.value = _clean(line[3:]).upper()
            c.font  = _f(11, bold=True, color=_WHITE)
            c.fill  = _fill(_BLUE)
            c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            ws.row_dimensions[row].height = 26
            row += 1
            i += 1

        # Table block
        elif line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1

            is_hdr, alt = True, False
            for tl in table_lines:
                if re.match(r"^\|[\s\-:|]+\|$", tl):
                    continue
                cols  = [_clean(c) for c in tl.strip("|").split("|")]
                widths = [col_b, col_c, col_d]
                row_h  = 18
                for ci, val in enumerate(cols[:3]):
                    row_h = max(row_h, math.ceil(len(val) / max(1, widths[ci])) * 14 + 4)

                for ci, val in enumerate(cols[:3]):
                    c = ws.cell(row=row, column=ci + 2)
                    c.value  = val
                    c.border = _BORDER
                    if is_hdr:
                        c.font  = _f(9, bold=True, color=_WHITE)
                        c.fill  = _fill(_STEEL)
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        c.font  = _f(9)
                        c.fill  = _fill(_ROW_ALT if alt else _WHITE)
                        c.alignment = Alignment(horizontal="left", vertical="center",
                                                wrap_text=True, indent=1)
                ws.row_dimensions[row].height = row_h
                row    += 1
                alt     = not alt
                is_hdr  = False

            ws.row_dimensions[row].height = 5
            row += 1

        # Bullet
        elif line.startswith("- ") or line.startswith("* "):
            ws.merge_cells(f"B{row}:D{row}")
            c     = ws.cell(row=row, column=2)
            text  = "  •  " + _clean(line[2:])
            c.value = text
            c.font  = _f(11)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            n_lines = max(1, math.ceil(len(text) / text_w))
            ws.row_dimensions[row].height = max(18, n_lines * 16)
            row += 1
            i   += 1

        # Blank / HR
        elif line.strip() in ("---", "***", ""):
            ws.row_dimensions[row].height = 6
            row += 1
            i   += 1

        # Paragraph
        else:
            ws.merge_cells(f"B{row}:D{row}")
            c    = ws.cell(row=row, column=2)
            text = _clean(line)
            c.value = text
            c.font  = _f(11)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            n_lines = max(1, math.ceil(len(text) / text_w))
            ws.row_dimensions[row].height = max(16, n_lines * 16)
            row += 1
            i   += 1


# ── Financial statement sheet helpers ────────────────────────────────────────

def _fmt_m(val_m) -> str:
    if val_m is None:
        return "N/A"
    try:
        v = float(val_m)
    except (TypeError, ValueError):
        return "N/A"
    return f"${v / 1000:.1f}B" if abs(v) >= 1000 else f"${v:.0f}M"


def _fmt_pct_fin(val, signed: bool = False) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        return f"{v:+.1f}%" if signed else f"{v:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fin_title(ws, row: int, text: str, ncols: int) -> None:
    ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
    c = ws.cell(row=row, column=1)
    c.value = text
    c.font  = _f(13, bold=True, color=_WHITE)
    c.fill  = _fill(_NAVY)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 32


def _fin_subhdr(ws, row: int, text: str, ncols: int) -> None:
    ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
    c = ws.cell(row=row, column=1)
    c.value = text
    c.font  = _f(10, bold=True, color=_WHITE)
    c.fill  = _fill(_BLUE)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 22


def _fin_col_hdr(ws, row: int, headers: list[str]) -> None:
    for ci, h in enumerate(headers):
        c = ws.cell(row=row, column=ci + 1)
        c.value = h
        c.font  = _f(9, bold=True, color=_WHITE)
        c.fill  = _fill(_STEEL)
        c.alignment = Alignment(horizontal="left" if ci == 0 else "right", vertical="center")
        c.border = _BORDER
    ws.row_dimensions[row].height = 18


def _fin_data_row(ws, row: int, label: str, values: list[str],
                  alt: bool = False, is_growth: bool = False) -> None:
    lbl_bg  = _LBL_ALT if alt else _LBL_BG
    data_bg = _ROW_ALT if alt else _WHITE

    lbl = ws.cell(row=row, column=1)
    lbl.value = label
    lbl.font  = _f(9, bold=True)
    lbl.fill  = _fill(lbl_bg)
    lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    lbl.border = _BORDER

    for ci, val in enumerate(values):
        c = ws.cell(row=row, column=ci + 2)
        c.value  = val
        c.font   = _f(9)
        c.fill   = _fill(data_bg)
        c.border = _BORDER
        c.alignment = Alignment(horizontal="right", vertical="center")
        if is_growth and val not in ("N/A", "", None):
            try:
                n = float(str(val).replace("%", "").replace("+", ""))
                if n > 0:
                    c.fill = _fill(_GRN_BG); c.font = _f(9, color=_GRN_FG)
                elif n < 0:
                    c.fill = _fill(_RED_BG); c.font = _f(9, color=_RED_FG)
            except ValueError:
                pass
    ws.row_dimensions[row].height = 17


def _draw_table(ws, start_row: int, subtitle: str, periods: list[str],
                data_rows: list[tuple], ncols: int) -> int:
    _fin_subhdr(ws, start_row, subtitle, ncols)
    start_row += 1
    _fin_col_hdr(ws, start_row, [""] + periods)
    start_row += 1
    alt = False
    for label, values, is_growth in data_rows:
        _fin_data_row(ws, start_row, label, values, alt=alt, is_growth=is_growth)
        start_row += 1
        alt = not alt
    return start_row + 2   # blank gap


# ── Sheet 4: Income Statement ─────────────────────────────────────────────────

def _build_income_sheet(wb, fin_data: dict) -> None:
    ws  = wb.create_sheet("Income Statement")
    inc = fin_data.get("income_statement", {})
    q   = inc.get("quarterly")
    a   = inc.get("annual")
    N   = 5   # label col + 4 period cols

    _fin_title(ws, 1, "INCOME STATEMENT", N)
    row = 3

    def _rows(data, annual=False):
        if not data:
            return []
        r = [
            ("Revenue",           [_fmt_m(v) for v in data["revenue"]],           False),
            ("Gross Profit",      [_fmt_m(v) for v in data["gross_profit"]],      False),
            ("Operating Income",  [_fmt_m(v) for v in data["operating_income"]],  False),
            ("Net Income",        [_fmt_m(v) for v in data["net_income"]],        False),
            ("Gross Margin",      [_fmt_pct_fin(v) for v in data["gross_margin"]],     False),
            ("Operating Margin",  [_fmt_pct_fin(v) for v in data["operating_margin"]], False),
            ("Net Margin",        [_fmt_pct_fin(v) for v in data["net_margin"]],       False),
        ]
        if annual:
            if data.get("yoy_revenue"):
                r.append(("YoY Revenue Growth",
                           [_fmt_pct_fin(v, signed=True) for v in data["yoy_revenue"]], True))
            if data.get("yoy_ni"):
                r.append(("YoY Net Income Growth",
                           [_fmt_pct_fin(v, signed=True) for v in data["yoy_ni"]], True))
        return r

    if q:
        row = _draw_table(ws, row, "Quarterly  —  Last 4 Quarters", q["dates"], _rows(q), N)
    if a:
        row = _draw_table(ws, row, "Annual  —  Last 4 Years", a["dates"], _rows(a, annual=True), N)

    _auto_fit(ws, min_w=10)


# ── Sheet 5: Balance Sheet ────────────────────────────────────────────────────

def _build_balance_sheet_sheet(wb, fin_data: dict) -> None:
    ws = wb.create_sheet("Balance Sheet")
    bs = fin_data.get("balance_sheet") or {}
    dt = bs.get("date", "")

    _fin_title(ws, 1, f"BALANCE SHEET  —  {dt}" if dt else "BALANCE SHEET", 2)
    row = 3

    def _section(title, items, start):
        _fin_subhdr(ws, start, title, 2)
        start += 1
        _fin_col_hdr(ws, start, ["Metric", "Value"])
        start += 1
        alt = False
        for label, val in items:
            _fin_data_row(ws, start, label, [val], alt=alt)
            start += 1
            alt = not alt
        return start + 2

    row = _section("Assets, Liabilities & Equity", [
        ("Total Assets",         _fmt_m(bs.get("total_assets"))),
        ("Total Liabilities",    _fmt_m(bs.get("total_liabilities"))),
        ("Shareholders' Equity", _fmt_m(bs.get("shareholders_equity"))),
        ("Cash & Equivalents",   _fmt_m(bs.get("cash"))),
        ("Total Debt",           _fmt_m(bs.get("total_debt"))),
        ("Net Debt",             _fmt_m(bs.get("net_debt"))),
    ], row)

    row = _section("Key Ratios", [
        ("Current Ratio",  f"{bs['current_ratio']:.2f}"  if bs.get("current_ratio")  else "N/A"),
        ("Debt / Equity",  f"{bs['debt_to_equity']:.2f}" if bs.get("debt_to_equity") else "N/A"),
    ], row)

    _auto_fit(ws, min_w=10)


# ── Sheet 6: Cash Flow ────────────────────────────────────────────────────────

def _build_cashflow_sheet(wb, fin_data: dict) -> None:
    ws = wb.create_sheet("Cash Flow")
    cf = fin_data.get("cash_flow", {})
    q  = cf.get("quarterly")
    a  = cf.get("annual")
    N  = 5

    _fin_title(ws, 1, "CASH FLOW STATEMENT", N)
    row = 3

    def _rows(data, annual=False):
        if not data:
            return []
        r = [
            ("Operating Cash Flow", [_fmt_m(v) for v in data["operating_cash_flow"]], False),
            ("Capital Expenditure",  [_fmt_m(v) for v in data["capital_expenditure"]], False),
            ("Free Cash Flow",       [_fmt_m(v) for v in data["free_cash_flow"]],      False),
            ("FCF Margin",           [_fmt_pct_fin(v) for v in data["fcf_margin"]],    False),
        ]
        if annual and data.get("yoy_fcf"):
            r.append(("YoY FCF Growth",
                       [_fmt_pct_fin(v, signed=True) for v in data["yoy_fcf"]], True))
        return r

    if q:
        row = _draw_table(ws, row, "Quarterly  —  Last 4 Quarters", q["dates"], _rows(q), N)
    if a:
        row = _draw_table(ws, row, "Annual  —  Last 4 Years", a["dates"], _rows(a, annual=True), N)

    _auto_fit(ws, min_w=10)


# ── Sheet 4: Bull vs Bear ────────────────────────────────────────────────────

_BULL_DARK   = "1E6630"   # dark forest green – bull header / text
_BEAR_DARK   = "C00000"   # dark crimson      – bear header / text
_BULL_BG_ALT = "D4EBC4"   # slightly deeper green for alt rows
_BEAR_BG_ALT = "FFCECE"   # slightly deeper red   for alt rows


def _parse_section(markdown: str, header: str) -> list[str]:
    """Return non-empty lines from a ## header block, stripped of markdown markers."""
    m = re.search(
        rf"^## {re.escape(header)}\s*\n([\s\S]*?)(?=\n## |\Z)",
        markdown, re.MULTILINE,
    )
    if not m:
        return []
    lines = []
    for line in m.group(1).split("\n"):
        text = re.sub(r"^[-*•\d]+[.)]\s*", "", line.strip())
        text = _clean(text)
        if text:
            lines.append(text)
    return lines


def _build_bull_bear_sheet(wb, markdown: str) -> None:
    ws   = wb.create_sheet("Bull vs Bear")
    bull = _parse_section(markdown, "Bull Case")
    bear = _parse_section(markdown, "Bear Case")

    if not bull and not bear:
        return

    # Title
    ws.merge_cells("A1:B1")
    t           = ws["A1"]
    t.value     = "BULL CASE  ·  BEAR CASE"
    t.font      = _f(14, bold=True, color=_WHITE)
    t.fill      = _fill(_NAVY)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Column headers
    for col, label, bg in ((1, "BULL CASE", _BULL_DARK), (2, "BEAR CASE", _BEAR_DARK)):
        c           = ws.cell(row=2, column=col)
        c.value     = label
        c.font      = _f(12, bold=True, color=_WHITE)
        c.fill      = _fill(bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border    = _BORDER
    ws.row_dimensions[2].height = 28

    # Content rows
    COL_W = 58
    for i in range(max(len(bull), len(bear))):
        row    = i + 3
        alt    = i % 2 == 1
        b_text = ("•  " + bull[i]) if i < len(bull) else ""
        r_text = ("•  " + bear[i]) if i < len(bear) else ""

        b           = ws.cell(row=row, column=1)
        b.value     = b_text
        b.font      = _f(10, color=_BULL_DARK if b_text else "000000")
        b.fill      = _fill(_BULL_BG_ALT if alt else _GRN_BG)
        b.alignment = Alignment(horizontal="left", vertical="top",
                                wrap_text=True, indent=1)
        b.border    = _BORDER

        r           = ws.cell(row=row, column=2)
        r.value     = r_text
        r.font      = _f(10, color=_BEAR_DARK if r_text else "000000")
        r.fill      = _fill(_BEAR_BG_ALT if alt else _RED_BG)
        r.alignment = Alignment(horizontal="left", vertical="top",
                                wrap_text=True, indent=1)
        r.border    = _BORDER

        n_lines = max(1, math.ceil(max(len(b_text), len(r_text)) / COL_W))
        ws.row_dimensions[row].height = max(26, n_lines * 16 + 6)

    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 60


# ── Sheet 7 (now 8): News & Sentiment ────────────────────────────────────────

_SENT_ROW: dict[str, tuple[str, str]] = {
    "Positive": (_GRN_BG, _GRN_FG),
    "Negative": (_RED_BG, _RED_FG),
    "Neutral":  ("F2F2F2", "595959"),
}
_OVERALL_ROW: dict[str, tuple[str, str]] = {
    "Bullish": (_GRN_BG, _GRN_FG),
    "Bearish": (_RED_BG, _RED_FG),
    "Neutral": ("F2F2F2", "595959"),
}


def _build_news_sheet(wb, sent_data: dict | None) -> None:
    if not sent_data:
        return

    ws       = wb.create_sheet("News & Sentiment")
    overall  = sent_data.get("overall", "Neutral")
    score    = sent_data.get("score")
    momentum = sent_data.get("momentum", "Stable")
    themes   = sent_data.get("themes", [])
    catalyst = sent_data.get("catalyst", "")
    summary  = sent_data.get("summary", "")
    articles = sent_data.get("articles", [])

    NCOLS    = 7
    last_col = get_column_letter(NCOLS)

    # ── Title ──────────────────────────────────────────────────────────────
    ws.merge_cells(f"A1:{last_col}1")
    t           = ws["A1"]
    t.value     = "NEWS & SENTIMENT ANALYSIS"
    t.font      = _f(14, bold=True, color=_WHITE)
    t.fill      = _fill(_NAVY)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # ── Overall sentiment banner ────────────────────────────────────────────
    ov_bg, ov_fg = _OVERALL_ROW.get(overall, _OVERALL_ROW["Neutral"])
    ws.merge_cells(f"A2:{last_col}2")
    ov           = ws["A2"]
    score_part   = f"   ·   Score: {score:.1f}/10" if score is not None else ""
    moment_part  = f"   ·   Momentum: {momentum}" if momentum else ""
    ov.value     = f"Overall Sentiment: {overall}{score_part}{moment_part}"
    ov.font      = _f(13, bold=True, color=ov_fg)
    ov.fill      = _fill(ov_bg)
    ov.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 30

    row = 3

    # ── Analyst summary ─────────────────────────────────────────────────────
    if summary:
        ws.merge_cells(f"A{row}:{last_col}{row}")
        c           = ws.cell(row=row, column=1)
        c.value     = summary
        c.font      = _f(10, color="2C3E50")
        c.fill      = _fill(_SUBTITLE)
        c.alignment = Alignment(horizontal="left", vertical="center",
                                wrap_text=True, indent=2)
        n_lines = max(2, math.ceil(len(summary) / 130))
        ws.row_dimensions[row].height = max(40, n_lines * 16 + 8)
        row += 1

    # ── Key Themes ──────────────────────────────────────────────────────────
    if themes:
        ws.merge_cells(f"A{row}:{last_col}{row}")
        c           = ws.cell(row=row, column=1)
        c.value     = "KEY THEMES   ·   " + "     ·     ".join(themes)
        c.font      = _f(10, bold=True, color=_NAVY)
        c.fill      = _fill("DCE9F7")
        c.alignment = Alignment(horizontal="left", vertical="center", indent=2)
        c.border    = Border(bottom=_THIN)
        ws.row_dimensions[row].height = 22
        row += 1

    # ── Catalyst Watch ──────────────────────────────────────────────────────
    if catalyst:
        ws.merge_cells(f"A{row}:{last_col}{row}")
        c           = ws.cell(row=row, column=1)
        c.value     = "CATALYST WATCH   ·   " + catalyst
        c.font      = _f(10, color="595959")
        c.fill      = _fill("F2F6FC")
        c.alignment = Alignment(horizontal="left", vertical="center", indent=2)
        c.border    = Border(bottom=_THIN)
        ws.row_dimensions[row].height = 22
        row += 1

    # Spacer
    ws.row_dimensions[row].height = 8
    row += 1

    # ── Column headers ──────────────────────────────────────────────────────
    headers = ["Impact", "Type", "Sentiment", "Source", "Date",
               "Headline", "Investment Implication"]
    for ci, h in enumerate(headers, start=1):
        c           = ws.cell(row=row, column=ci)
        c.value     = h
        c.font      = _f(9, bold=True, color=_WHITE)
        c.fill      = _fill(_STEEL)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border    = _BORDER
    ws.row_dimensions[row].height = 20
    row += 1

    # ── Article rows ────────────────────────────────────────────────────────
    _IMP_FG = {"Major": "7B0000", "Minor": "4A4A4A"}

    for article in articles:
        sentiment        = article.get("sentiment", "Neutral")
        impact           = article.get("impact", "Moderate")
        row_bg, row_fg   = _SENT_ROW.get(sentiment, _SENT_ROW["Neutral"])

        values = [
            impact,
            article.get("type", ""),
            sentiment,
            article.get("source", ""),
            article.get("date", ""),
            article.get("headline", ""),
            article.get("note", ""),
        ]
        for ci, val in enumerate(values, start=1):
            c        = ws.cell(row=row, column=ci)
            c.value  = val
            c.fill   = _fill(row_bg)
            c.border = _BORDER

            if ci == 1:   # Impact
                c.font      = _f(9, bold=True, color=_IMP_FG.get(impact, row_fg))
                c.alignment = Alignment(horizontal="center", vertical="top")
            elif ci == 3: # Sentiment
                c.font      = _f(9, bold=True, color=row_fg)
                c.alignment = Alignment(horizontal="center", vertical="top")
            elif ci == 6: # Headline — hyperlinked
                url = article.get("url", "")
                if url:
                    c.hyperlink = url
                    c.font      = _f(9, color="0563C1")
                else:
                    c.font      = _f(9)
                c.alignment = Alignment(horizontal="left", vertical="top",
                                        wrap_text=True, indent=1)
            elif ci == 7: # Investment Implication
                c.font      = _f(9, color="1A1A2E")
                c.alignment = Alignment(horizontal="left", vertical="top",
                                        wrap_text=True, indent=1)
            else:
                c.font      = _f(9)
                c.alignment = Alignment(horizontal="center", vertical="top")

        ws.row_dimensions[row].height = 52
        row += 1

    # ── Column widths ────────────────────────────────────────────────────────
    for col, w in zip("ABCDEFG", [11, 13, 12, 18, 12, 44, 52]):
        ws.column_dimensions[col].width = w


# ── DCF Model sheet ───────────────────────────────────────────────────────────

def _build_dcf_sheet(wb, dcf_result: dict | None, ticker: str) -> None:
    if not dcf_result or dcf_result.get("error"):
        return

    ws  = wb.create_sheet("DCF Model")
    inp = dcf_result["inputs"]
    fc  = dcf_result["forecast"]
    val = dcf_result["valuation"]
    sen = dcf_result["sensitivity"]
    px  = val["current_price"] or 0

    NCOLS = 6   # A–F used throughout

    # Title
    _fin_title(ws, 1, f"DCF MODEL  —  {ticker}", NCOLS)

    # Subtitle
    ws.merge_cells(f"A2:{get_column_letter(NCOLS)}2")
    sub           = ws["A2"]
    sub.value     = "Two-Stage Discounted Cash Flow  ·  FCFF-based  ·  Gordon Growth Terminal Value"
    sub.font      = _f(9, color="5A6B7B")
    sub.fill      = _fill(_SUBTITLE)
    sub.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16

    row = 4   # row 3 is a blank spacer (default height)

    # ── Section 1: Model Assumptions ─────────────────────────────────────────
    _fin_subhdr(ws, row, "MODEL ASSUMPTIONS", NCOLS)
    row += 1
    _fin_col_hdr(ws, row, ["Assumption", "Value"])
    row += 1

    assumptions = [
        ("Risk-Free Rate",           f"{inp['rf']:.2f}%",          False),
        ("Equity Risk Premium",      f"{inp['erp']:.2f}%",         False),
        ("Beta (5-yr Monthly)",      f"{inp['beta']:.3f}",         False),
        ("Cost of Equity (Ke)",      f"{inp['ke']:.2f}%",          False),
        ("Pre-Tax Cost of Debt",     f"{inp['kd_pretax']:.2f}%",   False),
        ("After-Tax Cost of Debt",   f"{inp['kd_aftertax']:.2f}%", False),
        ("Effective Tax Rate",       f"{inp['tax_rate']:.2f}%",    False),
        ("Equity Weight",            f"{inp['we']:.1f}%",          False),
        ("Debt Weight",              f"{inp['wd']:.1f}%",          False),
        ("WACC",                     f"{inp['wacc']:.2f}%",        False),  # idx 9 — highlighted
        ("Revenue CAGR (3-yr Hist)", f"{inp['rev_cagr']:.2f}%",   False),
        ("EBIT Margin (Hist. Avg)",  f"{inp['ebit_margin']:.2f}%", False),
        ("D&A as % of Revenue",      f"{inp['da_pct']:.2f}%",      False),
        ("CapEx as % of Revenue",    f"{inp['capex_pct']:.2f}%",   False),
        ("ΔWC as % of Revenue", f"{inp['nwc_pct']:.2f}%",     False),
        ("Terminal Growth Rate",     f"{inp['tg']:.2f}%",          False),
        ("Forecast Horizon",         "5 Years",                    False),
    ]

    for idx, (label, value, _) in enumerate(assumptions):
        alt      = idx % 2 == 1
        is_wacc  = (idx == 9)
        lbl_bg   = _BLUE if is_wacc else (_LBL_ALT if alt else _LBL_BG)
        val_bg   = _BLUE if is_wacc else (_ROW_ALT if alt else _WHITE)
        txt_clr  = _WHITE if is_wacc else "000000"

        lbl           = ws.cell(row=row, column=1)
        lbl.value     = label
        lbl.font      = _f(9, bold=True, color=txt_clr)
        lbl.fill      = _fill(lbl_bg)
        lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        lbl.border    = _BORDER

        vc           = ws.cell(row=row, column=2)
        vc.value     = value
        vc.font      = _f(9, bold=is_wacc, color=txt_clr)
        vc.fill      = _fill(val_bg)
        vc.alignment = Alignment(horizontal="right", vertical="center")
        vc.border    = _BORDER

        ws.row_dimensions[row].height = 17
        row += 1

    row += 1  # spacer

    # ── Section 2: 5-Year FCFF Forecast ──────────────────────────────────────
    years = ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
    _fin_subhdr(ws, row, "5-YEAR FCFF FORECAST  ($M)", NCOLS)
    row += 1
    _fin_col_hdr(ws, row, ["Metric"] + years)
    row += 1

    forecast_rows = [
        ("Revenue Growth",  [f"{g:.1f}%" for g in fc["growth_pct"]], True),
        ("Revenue ($M)",    [_fmt_m(v) for v in fc["revenue_m"]],    False),
        ("EBIT ($M)",       [_fmt_m(v) for v in fc["ebit_m"]],       False),
        ("NOPAT ($M)",      [_fmt_m(v) for v in fc["nopat_m"]],      False),
        ("D&A ($M)",        [_fmt_m(v) for v in fc["da_m"]],         False),
        ("CapEx ($M)",      [_fmt_m(v) for v in fc["capex_m"]],      False),
        ("ΔNWC ($M)",  [_fmt_m(v) for v in fc["dnwc_m"]],       False),
        ("FCFF ($M)",       [_fmt_m(v) for v in fc["fcff_m"]],       False),
    ]

    alt = False
    for label, values, is_growth in forecast_rows:
        _fin_data_row(ws, row, label, values, alt=alt, is_growth=is_growth)
        row += 1
        alt = not alt

    row += 1  # spacer

    # ── Section 3: Valuation Bridge ──────────────────────────────────────────
    _fin_subhdr(ws, row, "VALUATION BRIDGE", NCOLS)
    row += 1
    _fin_col_hdr(ws, row, ["Metric", "Value"])
    row += 1

    upside_str = (f"{val['upside_pct']:+.1f}%"
                  if val["upside_pct"] is not None else "N/A")
    iv_str = f"${val['intrinsic']:.2f}"
    px_str = f"${px:.2f}" if px else "N/A"

    valuation_rows = [
        ("PV of Explicit Forecast",      _fmt_m(val["pv_fcff_m"]),  False),
        ("Terminal Value (undiscounted)", _fmt_m(val["tv_m"]),       False),
        ("PV of Terminal Value",          _fmt_m(val["pv_tv_m"]),    False),
        ("Terminal Value % of EV",        f"{val['tv_pct']:.1f}%",  False),
        ("Enterprise Value",              _fmt_m(val["ev_m"]),       False),  # idx 4 — highlighted
        ("Less: Net Debt",                _fmt_m(val["net_debt_m"]), False),
        ("Equity Value",                  _fmt_m(val["eq_val_m"]),   False),
        ("Shares Outstanding",            f"{val['shares_m']:.2f}M", False),
        ("Intrinsic Value / Share",       iv_str,                    False),  # idx 8 — highlighted
        ("Current Price",                 px_str,                    False),
        ("Implied Upside / Downside",     upside_str,                True),   # green/red
    ]

    for idx, (label, value, is_growth) in enumerate(valuation_rows):
        alt     = idx % 2 == 1
        is_ev   = (idx == 4)
        is_iv   = (idx == 8)
        special = is_ev or is_iv

        lbl_bg  = _BLUE if special else (_LBL_ALT if alt else _LBL_BG)
        val_bg  = _BLUE if special else (_ROW_ALT if alt else _WHITE)
        txt_clr = _WHITE if special else "000000"

        lbl           = ws.cell(row=row, column=1)
        lbl.value     = label
        lbl.font      = _f(9, bold=True, color=txt_clr)
        lbl.fill      = _fill(lbl_bg)
        lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        lbl.border    = _BORDER

        vc = ws.cell(row=row, column=2)
        vc.value  = value
        vc.border = _BORDER
        vc.alignment = Alignment(horizontal="right", vertical="center")

        if special:
            vc.font = _f(9, bold=True, color=txt_clr)
            vc.fill = _fill(val_bg)
        elif is_growth and value not in ("N/A", ""):
            try:
                n = float(value.replace("%", "").replace("+", ""))
                if n > 0:
                    vc.font = _f(9, color=_GRN_FG); vc.fill = _fill(_GRN_BG)
                elif n < 0:
                    vc.font = _f(9, color=_RED_FG); vc.fill = _fill(_RED_BG)
                else:
                    vc.font = _f(9); vc.fill = _fill(val_bg)
            except ValueError:
                vc.font = _f(9); vc.fill = _fill(val_bg)
        else:
            vc.font = _f(9)
            vc.fill = _fill(val_bg)

        ws.row_dimensions[row].height = 17
        row += 1

    row += 1  # spacer

    # ── Section 4: Sensitivity Table ─────────────────────────────────────────
    _fin_subhdr(ws, row, "SENSITIVITY: INTRINSIC VALUE PER SHARE  ($/share)", NCOLS)
    row += 1

    ws.merge_cells(f"A{row}:{get_column_letter(NCOLS)}{row}")
    note           = ws.cell(row=row, column=1)
    note.value     = "Row = WACC  ·  Column = Terminal Growth Rate  ·  Base case highlighted in navy"
    note.font      = _f(9, color="595959")
    note.fill      = _fill("F2F6FC")
    note.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 16
    row += 1

    tg_hdrs = [f"{t:.1f}%" for t in sen["tg_range"]]
    _fin_col_hdr(ws, row, ["WACC \\ Term Growth"] + tg_hdrs)
    row += 1

    for ri, (w, row_vals) in enumerate(zip(sen["wacc_range"], sen["table"])):
        is_base_row = (ri == 2)

        lbl           = ws.cell(row=row, column=1)
        lbl.value     = f"{w:.2f}%"
        lbl.font      = _f(9, bold=True, color=_WHITE if is_base_row else "000000")
        lbl.fill      = _fill(_NAVY if is_base_row else (_LBL_ALT if ri % 2 else _LBL_BG))
        lbl.alignment = Alignment(horizontal="center", vertical="center")
        lbl.border    = _BORDER

        for ci, iv in enumerate(row_vals):
            is_base = is_base_row and ci == 2
            c        = ws.cell(row=row, column=ci + 2)
            c.border  = _BORDER
            c.alignment = Alignment(horizontal="center", vertical="center")
            if iv is None:
                c.value = "N/A"
                c.font  = _f(9, color="999999")
                c.fill  = _fill("F2F2F2")
            elif is_base:
                c.value = f"${iv:.2f}"
                c.font  = _f(9, bold=True, color=_WHITE)
                c.fill  = _fill(_NAVY)
            elif px and iv > px:
                c.value = f"${iv:.2f}"
                c.font  = _f(9, color=_GRN_FG)
                c.fill  = _fill(_GRN_BG)
            elif px and iv < px:
                c.value = f"${iv:.2f}"
                c.font  = _f(9, color=_RED_FG)
                c.fill  = _fill(_RED_BG)
            else:
                c.value = f"${iv:.2f}"
                c.font  = _f(9)
                c.fill  = _fill(_ROW_ALT if ri % 2 else _WHITE)

        ws.row_dimensions[row].height = 18
        row += 1

    # Warning banner if any
    if dcf_result.get("warnings"):
        row += 1
        ws.merge_cells(f"A{row}:{get_column_letter(NCOLS)}{row}")
        w           = ws.cell(row=row, column=1)
        w.value     = "  ".join(dcf_result["warnings"])
        w.font      = _f(9, bold=True, color=_RED_FG)
        w.fill      = _fill(_RED_BG)
        w.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[row].height = 20

    # Column widths
    ws.column_dimensions["A"].width = 30
    for col in "BCDEF":
        ws.column_dimensions[col].width = 14


# ── Entry point ───────────────────────────────────────────────────────────────

def build_excel(ticker: str, stats: dict, fin_data: dict,
                price_history, sp500_history, markdown: str,
                news_sentiment: dict | None,
                dcf_result: dict | None,
                output_path: str) -> None:
    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    _build_snapshot_sheet(wb, ticker, stats)
    _build_chart_sheet(wb, ticker, price_history, sp500_history)
    _build_analysis_sheet(wb, markdown)
    _build_bull_bear_sheet(wb, markdown)
    _build_income_sheet(wb, fin_data)
    _build_balance_sheet_sheet(wb, fin_data)
    _build_cashflow_sheet(wb, fin_data)
    _build_news_sheet(wb, news_sentiment)
    _build_dcf_sheet(wb, dcf_result, ticker)
    wb.save(output_path)
