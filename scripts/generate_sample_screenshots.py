"""Render polished sample PNGs that mirror the dashboard's institutional look.

These are deterministic, high-DPI board-pack-style renders (not live browser
captures) used in the README so reviewers can see the product without running
it. They are built from the same data and judgment layer as the dashboard, so
the verdict, KPIs, and commentary match what the app shows.

    python scripts/generate_sample_screenshots.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.branding import MPL_FONT_STACK, PALETTE, VERDICT_COLORS, signal_hex
from src.config import DEFAULT_PROCESSED_DATASET, REPORTS_SAMPLE_DIR
from src.ingestion.store import load_store
from src.modeling.assessment import build_assessment
from src.modeling.data_audit import audit_scores, run_audit
from src.modeling.metrics import latest_rows
from src.modeling.multiples import multiples_summary
from src.modeling.valuation_case import CaseNotApplicableError, build_valuation_case, case_warnings
from src.pipeline.build_dataset import build_dataset
from src.reporting.valuation_charts import football_field_data
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
SHOWCASE_COMPANY_ID = "GOOGL"


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
        latest = latest_rows(df)
        company_id = SHOWCASE_COMPANY_ID if SHOWCASE_COMPANY_ID in set(latest["company_id"]) else (
            latest.sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]
        )
    return df, company_id


def _store():
    return load_store(demo=True)


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
    positions = [0.018, 0.320, 0.475, 0.625, 0.815]
    for x, (label, value) in zip(positions, meta):
        ax.text(x, y + 0.030, label, fontsize=6.5, color="#8aa4bf", zorder=2, va="center")
        ax.text(x, y + 0.013, value, fontsize=8.5, color="#f1f6fb", zorder=2, va="center", weight="bold")
    if verdict is not None:
        color = VERDICT_COLORS.get(verdict.verdict_key, PALETTE["navy_3"])
        ax.text(0.982, y + height - 0.030, verdict.verdict_label.upper(), fontsize=10, color="white",
                weight="bold", ha="right", va="center", zorder=2,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=color, edgecolor="none"))


def _header_clean(ax, row, verdict=None, height=0.135, y=0.865):
    ax.add_patch(Rectangle((0, y), 1, height, color=NAVY, zorder=1))
    name = row["company_name"]
    ax.text(
        0.018,
        y + height - 0.028,
        "VALUATION WORKBENCH | PUBLIC DEMO | QUARTERLY REVIEW",
        fontsize=7.5,
        color="#93acc6",
        zorder=2,
        va="center",
    )
    ax.text(0.018, y + height - 0.066, name, fontsize=18, color="white", weight="bold", zorder=2, va="center")
    period = pd.Timestamp(row["period"])
    country = "United States" if str(row.get("exchange", "")).upper() in {"NASDAQ", "NYSE"} else "Brazil"
    sector_label = str(row.get("sector", ""))
    if sector_label == "Mega-Cap Tech & Digital Platforms":
        sector_label = "Mega-Cap Tech Platforms"
    meta = [
        ("SECTOR", sector_label),
        ("LISTING", f"{row.get('exchange', '')} | {country}"),
        ("PERIOD", f"Q{period.quarter} {period.year}"),
        ("CURRENCY", f"{row.get('currency', 'BRL')}m"),
        ("AS OF", period.strftime("%d %b %Y")),
    ]
    x = 0.018
    for label, value in meta:
        ax.text(x, y + 0.030, label, fontsize=6.5, color="#8aa4bf", zorder=2, va="center")
        ax.text(x, y + 0.013, value, fontsize=8.5, color="#f1f6fb", zorder=2, va="center", weight="bold")
        x += 0.155
    if verdict is not None:
        color = VERDICT_COLORS.get(verdict.verdict_key, PALETTE["navy_3"])
        ax.text(
            0.982,
            y + height - 0.030,
            verdict.verdict_label.upper(),
            fontsize=10,
            color="white",
            weight="bold",
            ha="right",
            va="center",
            zorder=2,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=color, edgecolor="none"),
        )


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


def _clean_text(value):
    if isinstance(value, str):
        return (
            value.replace("Â·", "|")
            .replace("â€”", "--")
            .replace("Ã©", "e")
            .replace("Ã£", "a")
        )
    return value


def _section(ax, x, y, title, note=""):
    title = _clean_text(title)
    note = _clean_text(note)
    ax.add_patch(Rectangle((x, y - 0.004), 0.004, 0.022, color=GOLD, zorder=3))
    ax.text(x + 0.012, y + 0.007, title.upper(), fontsize=9.5, color=NAVY, weight="bold", va="center", zorder=3)
    if note:
        ax.text(x + 0.012 + 0.0072 * len(title), y + 0.007, "   " + note, fontsize=7, color=MUTED, va="center", zorder=3)


def _table(ax, headers, rows, bbox, anchor_idx=None, median_idx=None, colw=None, numeric_from=1):
    headers = [_clean_text(h) for h in headers]
    rows = [[_clean_text(c) for c in row] for row in rows]
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
        if c >= numeric_from:
            cell.set_text_props(ha="right")
    return table


# --- 1. KPI / Executive dashboard ------------------------------------------

def kpi_dashboard(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid, store=_store())
    row = a.row
    fig = plt.figure(figsize=(12.8, 7.4), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, a)

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
    a = build_assessment(df, cid, store=_store())
    row = a.row
    currency = row.get("currency", "BRL")
    fig = plt.figure(figsize=(12.8, 7.8), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, a)

    # Business description.
    ax.add_patch(Rectangle((0.018, 0.74, ), 0.964, 0.105, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.74), 0.004, 0.105, facecolor=PALETTE["navy_3"]))
    ax.text(0.034, 0.822, "BUSINESS DESCRIPTION", fontsize=7.2, color=NAVY, weight="bold", va="top")
    country = "the U.S." if str(row.get("exchange", "")).upper() in {"NASDAQ", "NYSE"} else "Brazil"
    desc = (f"{row['company_name']} is a {str(row.get('sector','')).lower()} company listed on {row.get('exchange')} "
            f"({country}). Over the trailing twelve months it generated {fmt_money(row.get('revenue_ttm'), currency)} of "
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
    a = build_assessment(df, cid, store=_store())
    row = a.row
    fig = plt.figure(figsize=(12.8, 7.6), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, a)

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


def _pct_signed(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):+.0%}"


def _price(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.2f}"


def _case(df: pd.DataFrame, cid: str):
    try:
        return build_valuation_case(df, cid, store=_store())
    except CaseNotApplicableError:
        return None


def valuation_case_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    a = case.assessment
    row = a.row
    currency = str(row.get("currency", "USD"))

    fig = plt.figure(figsize=(12.8, 7.6), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, a)

    _section(ax, 0.018, 0.815, "Valuation Case", "DCF, scenario targets, and model-quality warnings")
    cards = [
        ("Current Price", _price(case.base.current_price), "latest public market close", GOLD),
        ("Base Target", _price(case.base.target_price), f"{_pct_signed(case.base.upside)} upside", GREEN),
        ("WACC", fmt_pct(case.wacc.wacc), f"beta {case.wacc.beta:.2f} | {case.wacc.beta_source}", BLUE),
        ("Exit Multiple", fmt_multiple(case.exit_multiple), case.exit_multiple_source[:34], PALETTE["charcoal"]),
    ]
    gap = 0.014
    w = (0.964 - gap * 3) / 4
    for i, (label, value, note, color) in enumerate(cards):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.695), w, 0.095, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.785), w, 0.005, facecolor=color, edgecolor="none"))
        ax.text(x + 0.012, 0.762, label.upper(), fontsize=6.8, color=MUTED, weight="bold")
        ax.text(x + 0.012, 0.734, value, fontsize=16, color=INK, weight="bold")
        ax.text(x + 0.012, 0.710, note, fontsize=7, color=MUTED)

    forecast = case.base.forecast.copy()
    fax = fig.add_axes([0.055, 0.325, 0.52, 0.31])
    years = [f"Y{int(y)}" for y in forecast["year"]]
    x = np.arange(len(forecast))
    fax.bar(x - 0.18, forecast["revenue"], width=0.36, color=BLUE, label="Revenue")
    fax.bar(x + 0.18, forecast["ebitda"], width=0.36, color=BLUE2, label="EBITDA")
    fax2 = fax.twinx()
    fax2.plot(x, forecast["ebitda_margin"], color=GOLD, marker="o", linewidth=2.2, label="EBITDA margin")
    fax.set_xticks(x)
    fax.set_xticklabels(years, fontsize=8)
    fax.set_ylabel(f"{currency}m", fontsize=8)
    fax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    fax2.tick_params(colors=GOLD, labelsize=8)
    fax.grid(True, axis="y", alpha=0.18)
    fax.set_axisbelow(True)
    for s in ("top",):
        fax.spines[s].set_visible(False)
        fax2.spines[s].set_visible(False)
    h1, l1 = fax.get_legend_handles_labels()
    h2, l2 = fax2.get_legend_handles_labels()
    fax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, ncols=3, loc="upper left")
    ax.text(0.055, 0.652, "BASE FORECAST", fontsize=8, color=NAVY, weight="bold")

    rows = []
    for name in ("bear", "base", "bull"):
        res = case.scenarios[name]
        rows.append([
            name.title(),
            fmt_money(res.enterprise_value, currency),
            fmt_money(res.implied_equity, currency),
            _price(res.target_price),
            _pct_signed(res.upside),
        ])
    tax = fig.add_axes([0.61, 0.445, 0.372, 0.19])
    tax.axis("off")
    _table(tax, ["Scenario", "EV", "Equity", "Target", "Upside"], rows, bbox=[0, 0, 1, 1],
           anchor_idx=1, colw=[0.20, 0.24, 0.24, 0.16, 0.16])

    ax.add_patch(Rectangle((0.61, 0.09), 0.372, 0.31, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.61, 0.09), 0.004, 0.31, facecolor=GOLD))
    ax.text(0.628, 0.365, "MODEL WARNINGS / DILIGENCE QUESTIONS", fontsize=7.2, color=NAVY, weight="bold")
    warnings = case_warnings(case)[:4]
    if not warnings:
        warnings = [{"severity": "info", "text": "No major model-quality warning on the illustrative case."}]
    y = 0.337
    for warning in warnings:
        sev = str(warning.get("severity", "info")).upper()
        ax.text(0.628, y, sev, fontsize=6.5, color=GOLD if sev != "HIGH" else PALETTE["red"], weight="bold")
        _wrapped(ax, warning["text"], 0.680, y + 0.002, width=43, fontsize=7.2, color=SLATE, lh=0.017)
        y -= 0.068

    ax.text(0.055, 0.270, "INVESTMENT QUESTION", fontsize=8, color=NAVY, weight="bold")
    thesis = a.thesis
    question = thesis.key_debate if thesis is not None and thesis.key_debate else a.sponsor_view
    _wrapped(ax, question, 0.055, 0.248, width=78, fontsize=8.3, color=SLATE, style="italic")

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def football_field_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        peer_benchmarking(path)
        return
    row = case.assessment.row
    data = football_field_data(case, price_history=_store().valuation_history)
    ranges = data.get("ranges", [])

    fig = plt.figure(figsize=(12.8, 6.8), dpi=150)
    fig.patch.set_facecolor(BG)
    ax_bg = _bg_axes(fig)
    _header_clean(ax_bg, row, case.assessment)
    _section(ax_bg, 0.018, 0.805, "Football Field", "Implied share-price ranges from DCF, peer multiples, history, and trading range")

    chart = fig.add_axes([0.18, 0.13, 0.75, 0.58])
    if not ranges:
        chart.text(0.5, 0.5, "Insufficient data for football field", ha="center", va="center", color=MUTED)
        chart.axis("off")
    else:
        labels = [r["label"] for r in ranges][::-1]
        lows = np.array([r["low"] for r in ranges][::-1], dtype=float)
        highs = np.array([r["high"] for r in ranges][::-1], dtype=float)
        mids = [r.get("mid") for r in ranges][::-1]
        y = np.arange(len(labels))
        chart.barh(y, highs - lows, left=lows, color=PALETTE["sage_soft"], edgecolor=GREEN, height=0.52)
        for yi, mid in zip(y, mids):
            if mid is not None and not pd.isna(mid):
                chart.scatter(mid, yi, marker="|", s=420, color=INK, linewidths=2.3, zorder=3)
        if data.get("current_price") is not None:
            chart.axvline(data["current_price"], color=GOLD, linestyle="--", linewidth=2)
            chart.text(data["current_price"], len(labels) - 0.35, f" current {_price(data['current_price'])}",
                       color=GOLD, fontsize=8, ha="left")
        if data.get("base_target") is not None:
            chart.axvline(data["base_target"], color=GREEN, linewidth=1.7)
            chart.text(data["base_target"], len(labels) - 0.75, f" target {_price(data['base_target'])}",
                       color=GREEN, fontsize=8, ha="left")
        chart.set_yticks(y)
        chart.set_yticklabels(labels, fontsize=8.2)
        chart.set_xlabel(f"Share price ({data.get('currency', '')})", fontsize=8)
        chart.grid(True, axis="x", alpha=0.18)
        chart.set_axisbelow(True)
        for s in ("top", "right", "left"):
            chart.spines[s].set_visible(False)

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def multiples_scorecard_snapshot(path: Path) -> None:
    df, cid = _load()
    store = _store()
    a = build_assessment(df, cid, store=store)
    summary = multiples_summary(a.row, a.peers, cid, store.valuation_history)

    fig = plt.figure(figsize=(12.8, 7.0), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, a.row, a)
    _section(ax, 0.018, 0.805, "Multi-Multiple Scorecard", "Which valuation lens matters for this business model")

    rows = []
    bar_items = []
    for m in summary:
        premium = _pct_signed(m.get("premium")) if m.get("premium") is not None else "n/a"
        hist = f"{float(m['hist_percentile']):.0%} pctile" if m.get("hist_percentile") is not None else "n/a"
        rows.append([
            m["label"],
            m["role_label"],
            fmt_multiple(m.get("current")),
            fmt_multiple(m.get("peer_median")),
            premium,
            hist,
            m["interpretation"].title(),
        ])
        if m.get("current") and m.get("peer_median") and m["role"] != "not_meaningful":
            bar_items.append(m)

    tax = fig.add_axes([0.018, 0.48, 0.964, 0.28])
    tax.axis("off")
    _table(tax, ["Multiple", "Role", "Current", "Peer med.", "Premium", "History", "Read"],
           rows, bbox=[0, 0, 1, 1], colw=[0.16, 0.14, 0.12, 0.12, 0.11, 0.14, 0.16])

    bx = fig.add_axes([0.07, 0.12, 0.40, 0.28])
    if bar_items:
        labels = [m["label"] for m in bar_items]
        x = np.arange(len(labels))
        bx.bar(x - 0.18, [m["current"] for m in bar_items], width=0.36, color=GREEN, label="Company")
        bx.bar(x + 0.18, [m["peer_median"] for m in bar_items], width=0.36, color=BLUE, label="Peer median")
        bx.set_xticks(x)
        bx.set_xticklabels(labels, fontsize=8, rotation=0)
        bx.set_ylabel("Multiple", fontsize=8)
        bx.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}x")
        bx.grid(True, axis="y", alpha=0.18)
        bx.legend(frameon=False, fontsize=8, ncols=2)
        for s in ("top", "right"):
            bx.spines[s].set_visible(False)
    else:
        bx.text(0.5, 0.5, "No valid positive multiples", ha="center", va="center", color=MUTED)
        bx.axis("off")

    ax.add_patch(Rectangle((0.535, 0.12), 0.447, 0.28, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.535, 0.12), 0.004, 0.28, facecolor=GOLD))
    ax.text(0.552, 0.365, "WHY THIS IS NOT A GENERIC MULTIPLE TABLE", fontsize=7.2, color=NAVY, weight="bold")
    notes = [
        "EV/Revenue is useful when margin differences or AI investment distort EBITDA.",
        "EV/EBITDA is still the primary operating-company lens when margins are normalized.",
        "P/E matters when equity holders care about buybacks, tax rate, and net cash.",
        "Outliers and negative denominators are flagged before they enter peer medians.",
    ]
    y = 0.335
    for note in notes:
        ax.text(0.558, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, note, 0.575, y, width=52, fontsize=7.8, color=SLATE, lh=0.018)
        y -= 0.055

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def data_audit_snapshot(path: Path) -> None:
    df, _ = _load()
    latest = latest_rows(df)
    issues = run_audit(df, latest)
    scores = audit_scores(issues, latest)

    fig = plt.figure(figsize=(12.8, 7.0), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    row = latest[latest["company_id"].eq(SHOWCASE_COMPANY_ID)].iloc[0] if SHOWCASE_COMPANY_ID in set(latest["company_id"]) else latest.iloc[0]
    _header_clean(ax, row, None)
    _section(ax, 0.018, 0.805, "Data Audit", "The model checks the data before trusting the valuation")

    counts = issues["severity"].value_counts().to_dict() if not issues.empty else {}
    sev_cards = [("High", counts.get("high", 0), PALETTE["red"]),
                 ("Medium", counts.get("medium", 0), GOLD),
                 ("Low", counts.get("low", 0), BLUE),
                 ("Info", counts.get("info", 0), MUTED)]
    gap = 0.014
    w = (0.964 - gap * 3) / 4
    for i, (label, value, color) in enumerate(sev_cards):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.685), w, 0.105, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.785), w, 0.005, facecolor=color, edgecolor="none"))
        ax.text(x + 0.012, 0.758, f"{label} findings".upper(), fontsize=6.8, color=MUTED, weight="bold")
        ax.text(x + 0.012, 0.722, f"{value}", fontsize=20, color=INK, weight="bold")

    rows = []
    for _, r in scores.head(8).iterrows():
        rows.append([r["ticker"], str(r["score"]), str(r["high"]), str(r["medium"]), str(r["low"])])
    tax = fig.add_axes([0.018, 0.36, 0.45, 0.27])
    tax.axis("off")
    _table(tax, ["Ticker", "Score", "High", "Med.", "Low"], rows, bbox=[0, 0, 1, 1],
           colw=[0.28, 0.20, 0.17, 0.17, 0.17])

    issue_rows = []
    if not issues.empty:
        for _, r in issues.head(7).iterrows():
            check = "\n".join(textwrap.wrap(str(r["check"]).replace("_", " "), width=16)[:2])
            detail = "\n".join(textwrap.wrap(str(r["detail"]), width=48)[:2])
            issue_rows.append([
                r["ticker"],
                str(r["severity"]).upper(),
                check,
                detail,
            ])
    else:
        issue_rows.append(["--", "OK", "No findings", "No material data-audit findings in the demo dataset."])
    tax2 = fig.add_axes([0.50, 0.22, 0.482, 0.41])
    tax2.axis("off")
    issue_table = _table(tax2, ["Ticker", "Severity", "Check", "Detail"], issue_rows, bbox=[0, 0, 1, 1],
                         colw=[0.11, 0.15, 0.22, 0.52], numeric_from=99)
    for (r, c), cell in issue_table.get_celld().items():
        if r > 0 and c in (2, 3):
            cell.set_text_props(ha="left", fontsize=7.6)
        elif r > 0:
            cell.set_text_props(ha="center", fontsize=7.8)

    ax.text(0.018, 0.285, "KEY CONTROLS", fontsize=8, color=NAVY, weight="bold")
    controls = [
        "Market cap is reconciled against price x shares.",
        "Enterprise value is checked against market cap, debt, cash, minority interest, and preferred equity.",
        "TTM completeness and stale periods are flagged before using multiples.",
        "Extreme multiples are excluded from adjusted peer medians.",
    ]
    y = 0.255
    for control in controls:
        ax.text(0.028, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, control, 0.044, y, width=60, fontsize=7.8, color=SLATE, lh=0.017)
        y -= 0.042

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ensure_dir(REPORTS_SAMPLE_DIR)
    kpi_dashboard(REPORTS_SAMPLE_DIR / "01_watchlist_home.png")
    peer_benchmarking(REPORTS_SAMPLE_DIR / "02_peer_benchmarking.png")
    valuation_case_snapshot(REPORTS_SAMPLE_DIR / "03_valuation_case.png")
    football_field_snapshot(REPORTS_SAMPLE_DIR / "04_football_field.png")
    multiples_scorecard_snapshot(REPORTS_SAMPLE_DIR / "05_multiples_scorecard.png")
    data_audit_snapshot(REPORTS_SAMPLE_DIR / "06_data_audit.png")
    print(f"Sample screenshots written to {REPORTS_SAMPLE_DIR}")


if __name__ == "__main__":
    main()
