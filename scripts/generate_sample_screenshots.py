"""Render polished sample PNGs that mirror the dashboard's institutional look.

These are deterministic, high-DPI board-pack-style renders (not live browser
captures) used in the README so reviewers can see the product without running
it. They are built from the same data and judgment layer as the dashboard, so
the verdict, KPIs, and commentary match what the app shows.

    python scripts/generate_sample_screenshots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.branding import MPL_FONT_STACK, PALETTE, VERDICT_COLORS, signal_hex
from src.config import DEFAULT_PROCESSED_DATASET, REPORTS_SAMPLE_DIR
from src.modeling.assessment import build_assessment
from src.modeling.metrics import latest_rows
from src.pipeline.build_dataset import build_dataset
from src.utils import ensure_dir, fmt_money, fmt_multiple, fmt_pct

plt.rcParams.update({"font.family": MPL_FONT_STACK, "font.size": 10})

NAVY = PALETTE["navy"]
INK = PALETTE["ink"]
SLATE = PALETTE["slate"]
MUTED = PALETTE["muted"]
LINE = PALETTE["line"]
BG = PALETTE["bg"]
BLUE = PALETTE["blue"]
BLUE2 = PALETTE["blue_2"]
GREEN = PALETTE["green"]
GOLD = PALETTE["gold"]

SIG_TEXT = {"green": "GREEN", "yellow": "AMBER", "red": "RED", "n/a": "N/A"}


def _bg_axes(fig):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


def _load(company_id: str | None = None):
    if not DEFAULT_PROCESSED_DATASET.exists():
        build_dataset("public-demo")
    df = pd.read_csv(DEFAULT_PROCESSED_DATASET, parse_dates=["period"])
    if company_id is None:
        company_id = latest_rows(df).sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]
    return df, company_id


def _header(ax, row, verdict=None, height=0.135, y=0.865):
    ax.add_patch(Rectangle((0, y), 1, height, color=NAVY, zorder=1))
    name = row["company_name"]
    ax.text(0.018, y + height - 0.028, "PRIVATE EQUITY · PORTFOLIO COMPANY MONITORING · QUARTERLY REVIEW",
            fontsize=7.5, color="#93acc6", zorder=2, va="center")
    ax.text(0.018, y + height - 0.066, name, fontsize=18, color="white", weight="bold", zorder=2, va="center")
    period = pd.Timestamp(row["period"])
    meta = [
        ("SECTOR", str(row.get("sector", ""))),
        ("LISTING", f"{row.get('exchange','')} · Brazil"),
        ("PERIOD", f"Q{period.quarter} {period.year}"),
        ("CURRENCY", f"{row.get('currency','BRL')} · m"),
        ("AS OF", period.strftime("%d %b %Y")),
    ]
    x = 0.018
    for label, value in meta:
        ax.text(x, y + 0.030, label, fontsize=6.5, color="#8aa4bf", zorder=2, va="center")
        ax.text(x, y + 0.013, value, fontsize=8.5, color="#f1f6fb", zorder=2, va="center", weight="bold")
        x += 0.155
    if verdict is not None:
        color = VERDICT_COLORS.get(verdict.verdict_key, PALETTE["navy_3"])
        ax.text(0.982, y + height - 0.030, verdict.verdict_label.upper(), fontsize=10, color="white",
                weight="bold", ha="right", va="center", zorder=2,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=color, edgecolor="none"))


def _kpi_card(ax, x, y, w, h, k):
    sig = str(k.signal).lower()
    accent = signal_hex(sig)
    ax.add_patch(Rectangle((x, y), w, h, facecolor="white", edgecolor=LINE, linewidth=0.8, zorder=2))
    ax.add_patch(Rectangle((x, y + h - 0.006), w, 0.006, facecolor=accent, edgecolor="none", zorder=3))
    pad = 0.012
    ax.text(x + pad, y + h - 0.026, k.label.upper(), fontsize=7, color=MUTED, weight="bold", zorder=3, va="center")
    ax.text(x + pad, y + h - 0.060, k.value, fontsize=15.5, color=INK, weight="bold", zorder=3, va="center")
    ax.text(x + pad, y + h - 0.088, k.context[:34], fontsize=6.8, color=MUTED, zorder=3, va="center")
    pill = SIG_TEXT.get(sig, "N/A")
    ax.text(x + pad, y + 0.020, pill, fontsize=6.8, color=accent, weight="bold", zorder=3, va="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=accent, linewidth=0.7))
    if k.percentile_label:
        ax.text(x + w - pad, y + 0.020, k.percentile_label, fontsize=6.3, color=PALETTE["muted_2"],
                ha="right", zorder=3, va="center")


def _section(ax, x, y, title, note=""):
    ax.add_patch(Rectangle((x, y - 0.004), 0.004, 0.022, color=GOLD, zorder=3))
    ax.text(x + 0.012, y + 0.007, title.upper(), fontsize=9.5, color=NAVY, weight="bold", va="center", zorder=3)
    if note:
        ax.text(x + 0.012 + 0.0072 * len(title), y + 0.007, "   " + note, fontsize=7, color=MUTED, va="center", zorder=3)


def _table(ax, headers, rows, bbox, anchor_idx=None, median_idx=None, colw=None):
    table = ax.table(cellText=rows, colLabels=headers, loc="center", bbox=bbox, colWidths=colw)
    table.auto_set_font_size(False)
    table.set_fontsize(8.2)
    n = len(rows)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(PALETTE["line_soft"])
        cell.set_linewidth(0.6)
        cell.PAD = 0.04
        if r == 0:
            cell.set_facecolor(PALETTE["panel_alt"])
            cell.set_text_props(weight="bold", color=MUTED, fontsize=7.2)
            cell.set_height(cell.get_height() * 0.8)
        else:
            cell.set_facecolor("white")
            if anchor_idx is not None and r == anchor_idx + 1:
                cell.set_facecolor("#eef4fb")
                cell.set_text_props(weight="bold", color=NAVY)
            if median_idx is not None and r == median_idx + 1:
                cell.set_facecolor("#f3f1e9")
                cell.set_text_props(style="italic", color=SLATE)
        if c > 0:
            cell.set_text_props(ha="right")
    return table


# --- 1. KPI / Executive dashboard ------------------------------------------

def kpi_dashboard(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid)
    row = a.row
    fig = plt.figure(figsize=(12.8, 7.4), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header(ax, row, a)

    # Verdict strip.
    vcolor = VERDICT_COLORS.get(a.verdict_key, PALETTE["navy_3"])
    ax.add_patch(Rectangle((0.018, 0.793), 0.964, 0.052, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.793), 0.006, 0.052, facecolor=vcolor))
    ax.text(0.034, 0.832, "MONITORING CONCLUSION", fontsize=6.8, color=MUTED, va="center")
    ax.text(0.034, 0.812, a.verdict_label, fontsize=11, color=vcolor, weight="bold", va="center")
    ax.text(0.20, 0.819, a.verdict_rationale, fontsize=8, color=SLATE, va="center")

    # KPI cards.
    _section(ax, 0.018, 0.752, "Key Performance Indicators", "Traffic lights vs PE monitoring thresholds · sector percentiles")
    cards = a.kpis[:5]
    gap = 0.012
    w = (0.964 - gap * 4) / 5
    h = 0.150
    for i, k in enumerate(cards):
        _kpi_card(ax, 0.018 + i * (w + gap), 0.578, w, h, k)

    # Peer snapshot table.
    _section(ax, 0.018, 0.545, "Peer Snapshot", f"{row.get('sector')} comps, sorted by EV/EBITDA")
    peers = a.peers.sort_values("ev_to_ebitda_ttm")
    headers = ["Ticker", "Company", "Growth", "EBITDA mgn", "FCF conv", "ND/EBITDA", "EV/Rev", "EV/EBITDA"]
    trows, anchor_idx = [], None
    for i, (_, p) in enumerate(peers.iterrows()):
        if p["company_id"] == cid:
            anchor_idx = i
        trows.append([
            p["ticker"].replace(".SA", ""), str(p.get("company_name", ""))[:22],
            fmt_pct(p.get("revenue_yoy_growth")), fmt_pct(p.get("ebitda_margin_ttm")),
            fmt_pct(p.get("fcf_conversion_ttm")), fmt_multiple(p.get("net_debt_to_ebitda_ttm")),
            fmt_multiple(p.get("ev_to_revenue_ttm")), fmt_multiple(p.get("ev_to_ebitda_ttm")),
        ])
    med = a.peer_median
    trows.append(["—", "Peer median", fmt_pct(med.get("revenue_yoy_growth")), fmt_pct(med.get("ebitda_margin_ttm")),
                  fmt_pct(med.get("fcf_conversion_ttm")), fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
                  fmt_multiple(med.get("ev_to_revenue_ttm")), fmt_multiple(med.get("ev_to_ebitda_ttm"))])
    tax = fig.add_axes([0.018, 0.07, 0.62, 0.46])
    tax.axis("off")
    _table(tax, headers, trows, bbox=[0, 0, 1, 1], anchor_idx=anchor_idx, median_idx=len(trows) - 1,
           colw=[0.10, 0.24, 0.11, 0.12, 0.11, 0.12, 0.09, 0.12])

    # Commentary memo.
    ax.add_patch(Rectangle((0.655, 0.07), 0.327, 0.46, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.655, 0.07), 0.004, 0.46, facecolor=PALETTE["navy_3"]))
    ax.text(0.672, 0.505, "EXECUTIVE COMMENTARY", fontsize=7.2, color=NAVY, weight="bold", va="top")
    _wrapped(ax, a.commentary, 0.672, 0.480, width=46, fontsize=8.2, color=SLATE, style="italic")
    ax.text(0.672, 0.300, "SPONSOR / INVESTMENT VIEW", fontsize=7.2, color=NAVY, weight="bold", va="top")
    _wrapped(ax, a.sponsor_view, 0.672, 0.275, width=46, fontsize=8.2, color=SLATE, style="italic")

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def _wrapped(ax, text, x, y, width=48, fontsize=8, color=SLATE, style="normal", lh=0.020):
    import textwrap
    for i, line in enumerate(textwrap.wrap(text, width=width)):
        ax.text(x, y - i * lh, line, fontsize=fontsize, color=color, va="top", style=style, zorder=3)


# --- 2. Company tearsheet ---------------------------------------------------

def company_tearsheet(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid)
    row = a.row
    currency = row.get("currency", "BRL")
    fig = plt.figure(figsize=(12.8, 7.8), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header(ax, row, a)

    # Business description.
    ax.add_patch(Rectangle((0.018, 0.74, ), 0.964, 0.105, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.74), 0.004, 0.105, facecolor=PALETTE["navy_3"]))
    ax.text(0.034, 0.822, "BUSINESS DESCRIPTION", fontsize=7.2, color=NAVY, weight="bold", va="top")
    desc = (f"{row['company_name']} is a {str(row.get('sector','')).lower()} company listed on {row.get('exchange')} "
            f"(Brazil). Over the trailing twelve months it generated {fmt_money(row.get('revenue_ttm'), currency)} of "
            f"revenue at a {fmt_pct(row.get('ebitda_margin_ttm'))} EBITDA margin, with cash conversion of "
            f"{fmt_pct(row.get('fcf_conversion_ttm'))} and net leverage of {fmt_multiple(row.get('net_debt_to_ebitda_ttm'))}.")
    _wrapped(ax, desc, 0.034, 0.800, width=140, fontsize=8.6, color=SLATE, style="italic")

    # Financial snapshot table.
    _section(ax, 0.018, 0.712, "Financial Snapshot")
    fin_headers = ["Metric", "Latest Qtr", "TTM", "Margin/YoY"]
    fin_rows = [
        ["Revenue", fmt_money(row.get("revenue"), currency), fmt_money(row.get("revenue_ttm"), currency), fmt_pct(row.get("revenue_yoy_growth"))],
        ["Gross profit", fmt_money(row.get("gross_profit"), currency), fmt_money(row.get("gross_profit_ttm"), currency), fmt_pct(row.get("gross_margin_ttm"))],
        ["EBITDA", fmt_money(row.get("ebitda"), currency), fmt_money(row.get("ebitda_ttm"), currency), fmt_pct(row.get("ebitda_margin_ttm"))],
        ["Net income", fmt_money(row.get("net_income"), currency), fmt_money(row.get("net_income_ttm"), currency), fmt_pct(row.get("net_income_margin"))],
        ["CFO", fmt_money(row.get("cfo"), currency), fmt_money(row.get("cfo_ttm"), currency), "—"],
        ["Free cash flow", fmt_money(row.get("fcf"), currency), fmt_money(row.get("fcf_ttm"), currency), fmt_pct(row.get("fcf_conversion_ttm"))],
    ]
    tax1 = fig.add_axes([0.018, 0.40, 0.46, 0.285])
    tax1.axis("off")
    _table(tax1, fin_headers, fin_rows, bbox=[0, 0, 1, 1], colw=[0.30, 0.24, 0.24, 0.22])

    # Valuation snapshot table.
    _section(ax, 0.52, 0.712, "Trading & Valuation")
    val_headers = ["Metric", "Current"]
    val_rows = [
        ["Market cap", fmt_money(row.get("market_cap"), currency)],
        ["Enterprise value", fmt_money(row.get("enterprise_value"), currency)],
        ["EV / Revenue", fmt_multiple(row.get("ev_to_revenue_ttm"))],
        ["EV / EBITDA", fmt_multiple(row.get("ev_to_ebitda_ttm"))],
        ["P / E", fmt_multiple(row.get("pe_ttm"))],
        ["Net debt / EBITDA", fmt_multiple(row.get("net_debt_to_ebitda_ttm"))],
    ]
    tax2 = fig.add_axes([0.52, 0.40, 0.462, 0.285])
    tax2.axis("off")
    _table(tax2, val_headers, val_rows, bbox=[0, 0, 1, 1], colw=[0.6, 0.4])

    # Revenue / EBITDA chart.
    _section(ax, 0.018, 0.355, "Quarterly Revenue & EBITDA")
    cax = fig.add_axes([0.06, 0.08, 0.90, 0.25])
    history = df[df["company_id"] == cid].sort_values("period")
    x = range(len(history))
    cax.bar([i - 0.2 for i in x], history["revenue"], width=0.4, color=BLUE, label="Revenue")
    cax.bar([i + 0.2 for i in x], history["ebitda"], width=0.4, color=BLUE2, label="EBITDA")
    cax2 = cax.twinx()
    cax2.plot(list(x), history["ebitda_margin"], color=GOLD, marker="o", linewidth=2, label="EBITDA margin")
    cax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    cax2.tick_params(colors=GOLD, labelsize=8)
    cax.set_xticks(list(x))
    cax.set_xticklabels([f"Q{pd.Timestamp(p).quarter} {pd.Timestamp(p).year%100:02d}" for p in history["period"]], fontsize=8)
    cax.set_ylabel(f"{currency}m", fontsize=8)
    cax.grid(True, axis="y", alpha=0.18)
    cax.set_axisbelow(True)
    for s in ("top",):
        cax.spines[s].set_visible(False)
        cax2.spines[s].set_visible(False)
    h1, l1 = cax.get_legend_handles_labels()
    h2, l2 = cax2.get_legend_handles_labels()
    cax.legend(h1 + h2, l1 + l2, frameon=False, ncols=3, fontsize=8, loc="upper left")

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


# --- 3. Peer benchmarking ---------------------------------------------------

def peer_benchmarking(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid)
    row = a.row
    fig = plt.figure(figsize=(12.8, 7.6), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header(ax, row, a)

    _section(ax, 0.018, 0.815, "Peer Universe", f"{row.get('sector')} comps · Q{pd.Timestamp(row['period']).quarter} {pd.Timestamp(row['period']).year}")
    peers = a.peers.sort_values("ev_to_ebitda_ttm")
    headers = ["Ticker", "Company", "Growth", "EBITDA mgn", "FCF conv", "ND/EBITDA", "EV/Rev", "EV/EBITDA"]
    trows, anchor_idx = [], None
    for i, (_, p) in enumerate(peers.iterrows()):
        if p["company_id"] == cid:
            anchor_idx = i
        trows.append([
            p["ticker"].replace(".SA", ""), str(p.get("company_name", ""))[:22],
            fmt_pct(p.get("revenue_yoy_growth")), fmt_pct(p.get("ebitda_margin_ttm")),
            fmt_pct(p.get("fcf_conversion_ttm")), fmt_multiple(p.get("net_debt_to_ebitda_ttm")),
            fmt_multiple(p.get("ev_to_revenue_ttm")), fmt_multiple(p.get("ev_to_ebitda_ttm")),
        ])
    med = a.peer_median
    trows.append(["—", "Peer median", fmt_pct(med.get("revenue_yoy_growth")), fmt_pct(med.get("ebitda_margin_ttm")),
                  fmt_pct(med.get("fcf_conversion_ttm")), fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
                  fmt_multiple(med.get("ev_to_revenue_ttm")), fmt_multiple(med.get("ev_to_ebitda_ttm"))])
    tax = fig.add_axes([0.018, 0.50, 0.964, 0.29])
    tax.axis("off")
    _table(tax, headers, trows, bbox=[0, 0, 1, 1], anchor_idx=anchor_idx, median_idx=len(trows) - 1,
           colw=[0.08, 0.22, 0.10, 0.12, 0.11, 0.12, 0.10, 0.13])

    # Scatter: growth vs margin.
    _section(ax, 0.018, 0.455, "Growth vs Margin")
    sax = fig.add_axes([0.06, 0.08, 0.40, 0.35])
    med_x = peers["revenue_yoy_growth"].median()
    med_y = peers["ebitda_margin_ttm"].median()
    for _, p in peers.iterrows():
        anc = p["company_id"] == cid
        sax.scatter(p["revenue_yoy_growth"], p["ebitda_margin_ttm"], s=170 if anc else 90,
                    c=GREEN if anc else BLUE, edgecolors="white", linewidths=1.2, zorder=3)
        sax.annotate(p["ticker"].replace(".SA", ""), (p["revenue_yoy_growth"], p["ebitda_margin_ttm"]),
                     xytext=(5, 4), textcoords="offset points", fontsize=8, color=SLATE)
    sax.axvline(med_x, color=PALETTE["muted_2"], ls="--", lw=1)
    sax.axhline(med_y, color=PALETTE["muted_2"], ls="--", lw=1)
    sax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    sax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    sax.set_xlabel("Revenue YoY growth", fontsize=8)
    sax.set_ylabel("TTM EBITDA margin", fontsize=8)
    sax.grid(True, alpha=0.18)
    sax.set_axisbelow(True)
    for s in ("top", "right"):
        sax.spines[s].set_visible(False)

    # EV/EBITDA bar.
    _section(ax, 0.52, 0.455, "EV / EBITDA Benchmark")
    bax = fig.add_axes([0.56, 0.08, 0.40, 0.35])
    pv = peers.dropna(subset=["ev_to_ebitda_ttm"])
    colors = [GREEN if c == cid else BLUE for c in pv["company_id"]]
    bars = bax.bar([t.replace(".SA", "") for t in pv["ticker"]], pv["ev_to_ebitda_ttm"], color=colors)
    median = pv["ev_to_ebitda_ttm"].median()
    bax.axhline(median, color=GOLD, ls="--", lw=1.3)
    bax.text(len(pv) - 0.5, median, f" median {median:.1f}x", color=GOLD, fontsize=7.5, va="bottom", ha="right")
    for b, v in zip(bars, pv["ev_to_ebitda_ttm"]):
        bax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}x", ha="center", va="bottom", fontsize=7.5, color=SLATE)
    bax.set_ylabel("EV / EBITDA (TTM)", fontsize=8)
    bax.tick_params(axis="x", labelsize=8)
    bax.grid(True, axis="y", alpha=0.18)
    bax.set_axisbelow(True)
    for s in ("top", "right"):
        bax.spines[s].set_visible(False)

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ensure_dir(REPORTS_SAMPLE_DIR)
    kpi_dashboard(REPORTS_SAMPLE_DIR / "kpi_dashboard.png")
    company_tearsheet(REPORTS_SAMPLE_DIR / "company_tearsheet.png")
    peer_benchmarking(REPORTS_SAMPLE_DIR / "peer_benchmarking.png")
    print(f"Sample screenshots written to {REPORTS_SAMPLE_DIR}")


if __name__ == "__main__":
    main()
