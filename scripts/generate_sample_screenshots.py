"""Render polished sample PNGs that mirror the dashboard's institutional look.

These are deterministic, high-DPI board-pack-style renders (not live browser
captures) used in the README so reviewers can see the product without running
it. They are built from the same data and judgment layer as the dashboard, so
the verdict, KPIs, and commentary match what the app shows.

    python scripts/generate_sample_screenshots.py
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.branding import MPL_FONT_STACK, PALETTE, VERDICT_COLORS, signal_hex
from src.config import DEFAULT_PROCESSED_DATASET, PRIVATE_PROCESSED_DATASET, REPORTS_SAMPLE_DIR
from src.ingestion.store import load_store
from src.modeling.assessment import build_assessment
from src.modeling.assessment import watchlist_summary
from src.modeling.capital_structure import build_capital_structure, ev_bridge
from src.modeling.consensus import build_consensus_read
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
BLUE = PALETTE["series_revenue"]
BLUE2 = PALETTE["series_ebitda"]
GREEN = PALETTE["anchor"]
PEER = PALETTE["peer"]
GOLD = PALETTE["series_margin"]

SIG_TEXT = {"green": "GREEN", "yellow": "AMBER", "red": "RED", "n/a": "N/A"}
SHOWCASE_COMPANY_ID = "GOOGL"
SCREENSHOT_DEMO = True


def _bg_axes(fig):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


def _load(company_id: str | None = None):
    path = DEFAULT_PROCESSED_DATASET if SCREENSHOT_DEMO else PRIVATE_PROCESSED_DATASET
    if SCREENSHOT_DEMO and not path.exists():
        build_dataset("public-demo")
    if not path.exists():
        raise FileNotFoundError(f"Screenshot dataset not found: {path}")
    df = pd.read_csv(path, parse_dates=["period"])
    if company_id is None:
        latest = latest_rows(df)
        company_id = SHOWCASE_COMPANY_ID if SHOWCASE_COMPANY_ID in set(latest["company_id"]) else (
            latest.sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]
        )
    return df, company_id


def _store():
    return load_store(demo=SCREENSHOT_DEMO)


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
        ("FINANCIALS THROUGH", f"Q{period.quarter} {period.year}"),
        ("CURRENCY", f"{row.get('currency','BRL')} · m"),
        ("MARKET SNAPSHOT", period.strftime("%d %b %Y")),
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
        ("INVESTMENT ANALYSIS PLATFORM | PUBLIC DEMO | QUARTERLY REVIEW"
         if SCREENSHOT_DEMO else
         "INVESTMENT ANALYSIS PLATFORM | PRIVATE DATA WORKFLOW | ANALYST CASE"),
        fontsize=7.5,
        color="#93acc6",
        zorder=2,
        va="center",
    )
    ax.text(0.018, y + height - 0.066, name, fontsize=18, color="white", weight="bold", zorder=2, va="center")
    period = pd.Timestamp(row["period"])
    exchange = str(row.get("exchange", "")).upper()
    country = "United States" if exchange.startswith("NASDAQ") or exchange.startswith("NYSE") else "Brazil"
    sector_label = str(row.get("sector", ""))
    if sector_label == "Mega-Cap Tech & Digital Platforms":
        sector_label = "Mega-Cap Tech Platforms"
    elif sector_label == "Software-Enabled Services":
        sector_label = "Software & Services"
    meta = [
        ("SECTOR", sector_label),
        ("LISTING", f"{row.get('exchange', '')} | {country}"),
        ("FINANCIALS THROUGH", f"Q{period.quarter} {period.year}"),
        ("CURRENCY", f"{row.get('currency', 'BRL')}m"),
        ("MARKET SNAPSHOT", period.strftime("%d %b %Y")),
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


def _platform_header(ax, title: str, subtitle: str, badge: str = "PUBLIC DEMO") -> None:
    ax.add_patch(Rectangle((0, 0.865), 1, 0.135, color=NAVY, zorder=1))
    ax.text(0.018, 0.971, "INVESTMENT ANALYSIS PLATFORM", fontsize=7.5,
            color="#93acc6", zorder=2, va="center")
    ax.text(0.018, 0.929, title, fontsize=18, color="white", weight="bold", zorder=2, va="center")
    ax.text(0.018, 0.891, subtitle, fontsize=8.3, color="#dce5ec", zorder=2, va="center")
    ax.text(0.982, 0.969, badge, fontsize=8, color="white", weight="bold", ha="right", va="center",
            bbox=dict(boxstyle="round,pad=0.45", facecolor=PALETTE["navy_3"], edgecolor="none"))


def _table(ax, headers, rows, bbox, anchor_idx=None, median_idx=None, colw=None, numeric_from=1):
    headers = [_clean_text(h) for h in headers]
    rows = [[_clean_text(c) for c in row] for row in rows]
    table = ax.table(cellText=rows, colLabels=headers, loc="center", bbox=bbox, colWidths=colw)
    table.auto_set_font_size(False)
    table.set_fontsize(8.2)
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
                cell.set_facecolor(PALETTE["sage_soft"])
                cell.set_text_props(weight="bold", color=NAVY)
            if median_idx is not None and r == median_idx + 1:
                cell.set_facecolor(PALETTE["panel_alt"])
                cell.set_text_props(style="italic", color=SLATE)
        if c >= numeric_from:
            cell.set_text_props(ha="right")
    return table


# --- 1. Multi-company universe ----------------------------------------------

def watchlist_overview(path: Path) -> None:
    df, _ = _load()
    store = _store()
    summary = watchlist_summary(df, store=store).copy()
    latest = latest_rows(df)

    fig = plt.figure(figsize=(12.8, 7.5), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _platform_header(
        ax,
        "Multi-Company Investment Watchlist",
        f"{len(summary)} monitored names | {len(latest)} companies in the analytical universe | "
        f"{summary['peer_group'].nunique()} reviewed peer groups",
    )

    verdict_counts = summary["verdict_key"].value_counts().to_dict()
    cards = [
        ("MONITORED NAMES", str(len(summary)), "ranked by analytical attention", GREEN),
        ("ANALYTICAL UNIVERSE", str(len(latest)), "watchlist companies plus trading comps", BLUE),
        ("PEER GROUPS", str(summary["peer_group"].nunique()), "Brazil and U.S. coverage", GOLD),
        ("DO WORK", str(verdict_counts.get("do_work", 0)), "dislocations requiring analyst review", GOLD),
        ("OPEN FLAGS", str(int(summary["flags"].sum())), "high and medium severity", PALETTE["red"]),
    ]
    gap = 0.012
    w = (0.964 - gap * 4) / 5
    for i, (label, value, note, color) in enumerate(cards):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.705), w, 0.112, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.812), w, 0.005, facecolor=color, edgecolor="none"))
        ax.text(x + 0.012, 0.785, label, fontsize=6.8, color=MUTED, weight="bold")
        ax.text(x + 0.012, 0.747, value, fontsize=19, color=INK, weight="bold")
        ax.text(x + 0.012, 0.720, note, fontsize=6.5, color=MUTED)

    _section(
        ax,
        0.018,
        0.665,
        "Ranked Watchlist",
        "Latest-quarter growth | LTM profitability and valuation | target excluded from peer median",
    )
    headers = ["#", "Attn", "Ticker", "Company", "Peer group", "Verdict",
               "Growth\nLatest Q YoY", "Profitability\nLTM", "Current multiple\nLTM", "Flags"]
    rows = []
    for _, r in summary.sort_values("rank").iterrows():
        mult = fmt_multiple(r.get("multiple_value"))
        mult = f"{mult} {r.get('multiple_name', '')}" if mult != "n/a" else "n/a"
        rows.append([
            str(int(r["rank"])), f"{r['attention_score']:.0f}", str(r["ticker"]),
            str(r["company_name"])[:25], str(r["peer_group"])[:28], str(r["verdict_label"]),
            fmt_pct(r.get("revenue_yoy_growth")), fmt_pct(r.get("profitability")), mult,
            str(int(r.get("flags", 0))),
        ])
    tax = fig.add_axes([0.018, 0.205, 0.964, 0.43])
    tax.axis("off")
    _table(tax, headers, rows, bbox=[0, 0, 1, 1], colw=[0.04, 0.06, 0.07, 0.17, 0.20, 0.11, 0.10, 0.09, 0.12, 0.04], numeric_from=6)

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.09, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.09, facecolor=GREEN))
    ax.text(0.035, 0.142, "SCALABLE COVERAGE MODEL", fontsize=7.2, color=NAVY, weight="bold")
    ax.text(
        0.035,
        0.108,
        "The same ingestion, data audit, peer review, consensus, capital-structure and valuation workflow can be "
        "applied to any company added through a Capital IQ export.",
        fontsize=8.2,
        color=SLATE,
    )
    ax.text(0.982, 0.047, "Demo estimates are illustrative; licensed Capital IQ data stays outside GitHub.",
            fontsize=6.8, color=MUTED, ha="right")

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def comparison_snapshot(path: Path) -> None:
    df, _ = _load()
    store = _store()
    anchor = build_assessment(df, SHOWCASE_COMPANY_ID, store=store)
    peer_ids = [c for c in anchor.peers["company_id"].tolist() if c != SHOWCASE_COMPANY_ID]
    selected = [SHOWCASE_COMPANY_ID] + peer_ids[:3]
    assessments = [build_assessment(df, cid, store=store) for cid in selected]

    fig = plt.figure(figsize=(12.8, 7.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _platform_header(
        ax,
        "Cross-Company Comparison",
        "A single analytical framework across geographies, sectors and currencies",
    )
    _section(ax, 0.018, 0.815, "Side-by-Side", "Company-specific values; no cross-currency aggregation")

    headers = ["Metric"] + [a.row["ticker"].replace(".SA", "") for a in assessments]
    rows = [
        ["Company"] + [str(a.row["company_name"])[:23] for a in assessments],
        ["Peer group"] + [str(a.peer_group)[:28] for a in assessments],
        ["Investment read"] + [a.verdict_label for a in assessments],
        ["Revenue growth (latest Q YoY)"] + [fmt_pct(a.row.get("revenue_yoy_growth")) for a in assessments],
        ["EBITDA margin (LTM)"] + [fmt_pct(a.row.get("ebitda_margin_ttm")) for a in assessments],
        ["FCF conversion (LTM)"] + [fmt_pct(a.row.get("fcf_conversion_ttm")) for a in assessments],
        ["Net debt / EBITDA (LTM)"] + [fmt_multiple(a.row.get("net_debt_to_ebitda_ttm")) for a in assessments],
        ["EV / Revenue (LTM)"] + [fmt_multiple(a.row.get("ev_to_revenue_ttm")) for a in assessments],
        ["EV / EBITDA (LTM)"] + [fmt_multiple(a.row.get("ev_to_ebitda_ttm")) for a in assessments],
        ["P / E (LTM)"] + [fmt_multiple(a.row.get("pe_ttm")) for a in assessments],
        ["Estimate momentum"] + [str(a.revisions.get("direction", "n/a")).title() for a in assessments],
        ["Financials through"] + [f"Q{pd.Timestamp(a.row['period']).quarter} {pd.Timestamp(a.row['period']).year}" for a in assessments],
    ]
    tax = fig.add_axes([0.018, 0.21, 0.964, 0.56])
    tax.axis("off")
    _table(tax, headers, rows, bbox=[0, 0, 1, 1], colw=[0.28, 0.18, 0.18, 0.18, 0.18], numeric_from=1)

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.09, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.09, facecolor=GOLD))
    ax.text(0.035, 0.139, "ANALYST USE", fontsize=7.2, color=NAVY, weight="bold")
    ax.text(0.035, 0.106, "Compare operating quality, valuation and estimate momentum before deciding where deeper diligence is worth the time.",
            fontsize=8.2, color=SLATE)

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


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
    _section(ax, 0.018, 0.545, "Peer Snapshot",
             "Latest-quarter growth | LTM margins, cash, leverage and multiples | anchor excluded from median")
    peers = a.peers.sort_values("ev_to_ebitda_ttm")
    headers = ["Ticker", "Company", "Growth\nLatest Q YoY", "EBITDA mgn\nLTM", "FCF conv\nLTM",
               "ND/EBITDA\nLTM", "EV/Rev\nLTM", "EV/EBITDA\nLTM"]
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
    trows.append(["—", "Peer median (ex-company)", fmt_pct(med.get("revenue_yoy_growth")), fmt_pct(med.get("ebitda_margin_ttm")),
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
    fin_headers = ["Metric", "Latest Reported Qtr", "LTM", "Growth / LTM Margin"]
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
    _section(ax, 0.018, 0.355, "Reported Quarterly Revenue & EBITDA",
             "Standalone-quarter bars and margin")
    cax = fig.add_axes([0.06, 0.08, 0.90, 0.25])
    history = df[df["company_id"] == cid].sort_values("period")
    x = range(len(history))
    cax.bar([i - 0.2 for i in x], history["revenue"], width=0.4, color=BLUE, label="Revenue (quarter)")
    cax.bar([i + 0.2 for i in x], history["ebitda"], width=0.4, color=BLUE2, label="EBITDA (quarter)")
    cax2 = cax.twinx()
    cax2.plot(list(x), history["ebitda_margin"], color=GOLD, marker="o", linewidth=2,
              label="EBITDA margin (quarter)")
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
    headers = ["Ticker", "Company", "Growth\nLatest Q YoY", "EBITDA mgn\nLTM", "FCF conv\nLTM",
               "ND/EBITDA\nLTM", "EV/Rev\nLTM", "EV/EBITDA\nLTM"]
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
    trows.append(["—", "Peer median (ex-company)", fmt_pct(med.get("revenue_yoy_growth")), fmt_pct(med.get("ebitda_margin_ttm")),
                  fmt_pct(med.get("fcf_conversion_ttm")), fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
                  fmt_multiple(med.get("ev_to_revenue_ttm")), fmt_multiple(med.get("ev_to_ebitda_ttm"))])
    tax = fig.add_axes([0.018, 0.50, 0.964, 0.29])
    tax.axis("off")
    _table(tax, headers, trows, bbox=[0, 0, 1, 1], anchor_idx=anchor_idx, median_idx=len(trows) - 1,
           colw=[0.08, 0.22, 0.10, 0.12, 0.11, 0.12, 0.10, 0.13])

    # Scatter: growth vs margin.
    _section(ax, 0.018, 0.455, "Growth vs Margin")
    sax = fig.add_axes([0.06, 0.08, 0.40, 0.35])
    peers_only = peers[peers["company_id"] != cid]
    med_x = peers_only["revenue_yoy_growth"].median()
    med_y = peers_only["ebitda_margin_ttm"].median()
    for _, p in peers.iterrows():
        anc = p["company_id"] == cid
        sax.scatter(p["revenue_yoy_growth"], p["ebitda_margin_ttm"], s=170 if anc else 90,
                    c=GREEN if anc else PEER, edgecolors="white", linewidths=1.2, zorder=3)
        sax.annotate(p["ticker"].replace(".SA", ""), (p["revenue_yoy_growth"], p["ebitda_margin_ttm"]),
                     xytext=(5, 4), textcoords="offset points", fontsize=8, color=SLATE)
    sax.axvline(med_x, color=PALETTE["muted_2"], ls="--", lw=1)
    sax.axhline(med_y, color=PALETTE["muted_2"], ls="--", lw=1)
    sax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    sax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    sax.set_xlabel("Revenue growth (latest quarter YoY)", fontsize=8)
    sax.set_ylabel("EBITDA margin (LTM)", fontsize=8)
    sax.grid(True, alpha=0.18)
    sax.set_axisbelow(True)
    for s in ("top", "right"):
        sax.spines[s].set_visible(False)

    # EV/EBITDA bar.
    _section(ax, 0.52, 0.455, "EV / EBITDA Benchmark")
    bax = fig.add_axes([0.56, 0.08, 0.40, 0.35])
    pv = peers.dropna(subset=["ev_to_ebitda_ttm"])
    colors = [GREEN if c == cid else PEER for c in pv["company_id"]]
    bars = bax.bar([t.replace(".SA", "") for t in pv["ticker"]], pv["ev_to_ebitda_ttm"], color=colors)
    median = pv.loc[pv["company_id"] != cid, "ev_to_ebitda_ttm"].median()
    bax.axhline(median, color=GOLD, ls="--", lw=1.3)
    bax.text(len(pv) - 0.5, median, f" median {median:.1f}x", color=GOLD, fontsize=7.5, va="bottom", ha="right")
    for b, v in zip(bars, pv["ev_to_ebitda_ttm"]):
        bax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}x", ha="center", va="bottom", fontsize=7.5, color=SLATE)
    bax.set_ylabel("Current EV / EBITDA (LTM)", fontsize=8)
    bax.tick_params(axis="x", labelsize=8)
    bax.grid(True, axis="y", alpha=0.18)
    bax.set_axisbelow(True)
    for s in ("top", "right"):
        bax.spines[s].set_visible(False)

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def consensus_snapshot(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid, store=_store())
    read = build_consensus_read(a.row)
    currency = str(a.row.get("currency", "USD"))

    fig = plt.figure(figsize=(12.8, 7.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, a.row, a)
    _section(ax, 0.018, 0.815, "Actual vs Consensus & Revisions",
             "Illustrative demo estimates | private workflow uses Capital IQ estimate exports")

    cards = []
    for metric in ("Revenue", "EBITDA"):
        item = next((r for r in read.rows if r["metric"] == metric), None)
        if item:
            cards.append((f"{metric} vs estimate", _pct_signed(item["delta_pct"]), item["status"],
                          GREEN if item["delta_pct"] >= 0 else PALETTE["red"]))
    rev30 = read.revisions.get("revenue", {}).get("d30")
    rev90 = read.revisions.get("revenue", {}).get("d90")
    cards.extend([
        ("Revenue revision 30d", _pct_signed(rev30), "NTM estimate momentum", GREEN if (rev30 or 0) >= 0 else PALETTE["red"]),
        ("Revenue revision 90d", _pct_signed(rev90), "NTM estimate momentum", GREEN if (rev90 or 0) >= 0 else PALETTE["red"]),
    ])
    gap = 0.014
    w = (0.964 - gap * 3) / 4
    for i, (label, value, note, color) in enumerate(cards[:4]):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.69), w, 0.10, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.785), w, 0.005, facecolor=color, edgecolor="none"))
        ax.text(x + 0.012, 0.760, label.upper(), fontsize=6.7, color=MUTED, weight="bold")
        ax.text(x + 0.012, 0.727, value, fontsize=17, color=INK, weight="bold")
        ax.text(x + 0.012, 0.705, note, fontsize=6.8, color=MUTED)

    _section(ax, 0.018, 0.645, read.comparison_label)
    comparison_rows = []
    for item in read.rows:
        comparison_rows.append([
            item["metric"], fmt_money(item["actual"], currency), fmt_money(item["consensus"], currency),
            fmt_money(item["delta"], currency), _pct_signed(item["delta_pct"]), item["status"].title(),
        ])
    tax = fig.add_axes([0.018, 0.39, 0.53, 0.22])
    tax.axis("off")
    _table(tax, ["Metric", "Actual", "Estimate", "Delta", "Delta %", "Read"], comparison_rows,
           bbox=[0, 0, 1, 1], colw=[0.16, 0.19, 0.19, 0.17, 0.13, 0.16])

    rax = fig.add_axes([0.61, 0.39, 0.34, 0.22])
    labels = ["Revenue", "EPS"]
    d30 = [read.revisions.get("revenue", {}).get("d30"), read.revisions.get("eps", {}).get("d30")]
    d90 = [read.revisions.get("revenue", {}).get("d90"), read.revisions.get("eps", {}).get("d90")]
    x = np.arange(len(labels))
    rax.bar(x - 0.18, [v or 0 for v in d30], 0.36, color=GREEN, label="30 days")
    rax.bar(x + 0.18, [v or 0 for v in d90], 0.36, color=GOLD, label="90 days")
    rax.axhline(0, color=INK, linewidth=0.8)
    rax.set_xticks(x)
    rax.set_xticklabels(labels, fontsize=8)
    rax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    rax.set_ylabel("Change in NTM estimate", fontsize=8)
    rax.grid(True, axis="y", alpha=0.18)
    rax.legend(frameon=False, fontsize=8, ncols=2, loc="lower center", bbox_to_anchor=(0.5, 1.02))
    for s in ("top", "right"):
        rax.spines[s].set_visible(False)

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.25, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.25, facecolor=GOLD))
    ax.text(0.035, 0.292, "INTERPRETATION & DATA DISCIPLINE", fontsize=7.2, color=NAVY, weight="bold")
    notes = [
        "Actual-versus-estimate comparisons are only called beats or misses when a matched pre-report consensus exists.",
        "The private workflow tracks revenue, EBITDA and EPS revisions over 30 and 90 days when exported from Capital IQ.",
        "Missing guidance, analyst count or revision snapshots remain explicit; the model never fabricates unavailable fields.",
    ]
    y = 0.255
    for note in notes:
        ax.text(0.037, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, note, 0.054, y, width=135, fontsize=8.0, color=SLATE, lh=0.018)
        y -= 0.055
    ax.text(0.982, 0.045, "Public-demo estimates are deterministic and illustrative, not market consensus.",
            fontsize=6.8, color=MUTED, ha="right")

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def capital_structure_snapshot(path: Path) -> None:
    df, cid = _load()
    a = build_assessment(df, cid, store=_store())
    cs = build_capital_structure(a.row)
    bridge = ev_bridge(a.row)
    currency = str(a.row.get("currency", "USD"))

    fig = plt.figure(figsize=(12.8, 7.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, a.row, a)
    _section(ax, 0.018, 0.815, "Capital Structure & Debt Capacity",
             "Credit-side underwriting | illustrative leverage cases, not actual covenants")

    cards = [
        ("Gross debt", fmt_money(cs.gross_debt, currency), "latest reported quarter", BLUE),
        ("Cash", fmt_money(cs.cash, currency), "cash and equivalents", GREEN),
        ("Net leverage", fmt_multiple(cs.net_leverage), "net debt / LTM EBITDA", GOLD),
        ("Interest coverage", fmt_multiple(cs.interest_coverage), "LTM EBITDA / interest", GREEN),
    ]
    gap = 0.014
    w = (0.964 - gap * 3) / 4
    for i, (label, value, note, color) in enumerate(cards):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.69), w, 0.10, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.785), w, 0.005, facecolor=color, edgecolor="none"))
        ax.text(x + 0.012, 0.760, label.upper(), fontsize=6.7, color=MUTED, weight="bold")
        ax.text(x + 0.012, 0.727, value, fontsize=14, color=INK, weight="bold")
        ax.text(x + 0.012, 0.705, note, fontsize=6.8, color=MUTED)

    _section(ax, 0.018, 0.645, "Debt Capacity", "Net debt supported at standard leverage cases")
    dax = fig.add_axes([0.07, 0.345, 0.40, 0.25])
    turns = sorted(cs.capacity)
    supported = [cs.capacity[t] for t in turns]
    incremental = [cs.incremental[t] for t in turns]
    x = np.arange(len(turns))
    dax.bar(x - 0.18, supported, 0.36, color=GREEN, label="Supported net debt")
    dax.bar(x + 0.18, incremental, 0.36, color=GOLD, label="Incremental vs today")
    dax.set_xticks(x)
    dax.set_xticklabels([f"{t:.1f}x" for t in turns], fontsize=8)
    dax.set_ylabel(f"{currency}m", fontsize=8)
    dax.grid(True, axis="y", alpha=0.18)
    dax.legend(frameon=False, fontsize=8, ncols=2, loc="lower center", bbox_to_anchor=(0.5, 1.02))
    for s in ("top", "right"):
        dax.spines[s].set_visible(False)

    _section(ax, 0.535, 0.645, "Current EV Bridge", "Calculated from equity value and balance-sheet items")
    bridge_rows = []
    if bridge.get("available"):
        bridge_rows = [
            ["Market capitalization", fmt_money(bridge.get("market_cap"), currency)],
            ["+ Total debt", fmt_money(bridge.get("total_debt"), currency)],
            ["+ Minority interest", fmt_money(bridge.get("minority_interest"), currency)],
            ["+ Preferred equity", fmt_money(bridge.get("preferred_equity"), currency)],
            ["- Cash", fmt_money(bridge.get("cash"), currency)],
            ["Calculated enterprise value", fmt_money(bridge.get("calculated_ev"), currency)],
            ["Reported enterprise value", fmt_money(bridge.get("reported_ev"), currency)],
            ["Reconciliation gap", _pct_signed(bridge.get("gap"))],
        ]
    tax = fig.add_axes([0.535, 0.305, 0.447, 0.29])
    tax.axis("off")
    _table(tax, ["EV bridge", "Value"], bridge_rows, bbox=[0, 0, 1, 1], colw=[0.62, 0.38])

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.17, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.17, facecolor=GOLD))
    ax.text(0.035, 0.215, "SPONSOR / LENDER READ", fontsize=7.2, color=NAVY, weight="bold")
    ax.text(0.035, 0.178, f"Illustrative incremental capacity at 4.0x EBITDA: {fmt_money(cs.sponsor_capacity, currency)}.",
            fontsize=8.4, color=SLATE)
    ax.text(0.035, 0.143, "The module separates reported capital structure, EV reconciliation and scenario capacity; actual debt pricing, "
            "covenants and rating constraints remain analyst inputs.", fontsize=8.0, color=SLATE)
    ax.text(0.035, 0.108, "Financial institutions are routed to a dedicated P/E, P/TBV, ROE and capital-ratio framework instead of EBITDA leverage.",
            fontsize=8.0, color=SLATE)

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


def _waterfall_axes(ax, labels, values, measures, currency, title):
    running = 0.0
    bases, heights, colors = [], [], []
    for value, measure in zip(values, measures):
        if measure == "absolute":
            base, height = 0.0, value
            running = value
            color = NAVY
        elif measure == "total":
            base, height = 0.0, value
            running = value
            color = NAVY
        else:
            start = running
            running += value
            base, height = min(start, running), abs(value)
            color = GREEN if value >= 0 else PALETTE["navy_3"]
        bases.append(base)
        heights.append(height)
        colors.append(color)
    x = np.arange(len(labels))
    bars = ax.bar(x, heights, bottom=bases, color=colors, width=0.62)
    for bar, value, measure in zip(bars, values, measures):
        y = bar.get_y() + bar.get_height()
        prefix = "" if measure in {"absolute", "total"} else ("+" if value >= 0 else "-")
        ax.text(bar.get_x() + bar.get_width() / 2, y, f"{prefix}{abs(value):,.0f}",
                ha="center", va="bottom", fontsize=7.3, color=SLATE)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5, rotation=12, ha="right")
    ax.set_ylabel(f"{currency}m", fontsize=8)
    ax.set_title(title, loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    ax.grid(True, axis="y", alpha=0.15)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _annotated_heatmap(ax, frame: pd.DataFrame, title: str, formatter, center=None):
    z = frame.to_numpy(dtype=float)
    cmap = LinearSegmentedColormap.from_list(
        "investment_teal", [PALETTE["line"], PALETTE["panel"], PALETTE["teal"]]
    )
    finite = z[np.isfinite(z)]
    if finite.size:
        vmin, vmax = float(finite.min()), float(finite.max())
        if center is not None:
            spread = max(abs(vmin - center), abs(vmax - center), 1e-9)
            vmin, vmax = center - spread, center + spread
    else:
        vmin, vmax = 0.0, 1.0
    ax.imshow(z, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            value = z[i, j]
            if np.isfinite(value):
                ax.text(j, i, formatter(value), ha="center", va="center",
                        fontsize=7.7, color=INK, weight="bold" if (i, j) == (z.shape[0] // 2, z.shape[1] // 2) else "normal")
    ax.set_xticks(np.arange(len(frame.columns)))
    ax.set_xticklabels(frame.columns, fontsize=7.5)
    ax.set_yticks(np.arange(len(frame.index)))
    ax.set_yticklabels(frame.index, fontsize=7.5)
    ax.set_title(title, loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    for side in ax.spines.values():
        side.set_color(LINE)


def valuation_forecast_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    row, base = case.assessment.row, case.base
    currency = str(row.get("currency", "USD"))
    forecast = base.forecast

    fig = plt.figure(figsize=(12.8, 7.4), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, case.assessment)
    _section(ax, 0.018, 0.815, "Operating Forecast & Free Cash Flow", "Base case | explicit forecast before terminal value")

    fax = fig.add_axes([0.055, 0.42, 0.52, 0.32])
    labels = ["LTM"] + [f"Y{int(y)}" for y in forecast["year"]]
    revenue = [row.get("revenue_ttm")] + forecast["revenue"].tolist()
    ebitda = [row.get("ebitda_ttm")] + forecast["ebitda"].tolist()
    ufcf = [np.nan] + forecast["ufcf"].tolist()
    x = np.arange(len(labels))
    fax.bar(x, revenue, color=[PALETTE["line"]] + [BLUE] * len(forecast), width=0.58, label="Revenue")
    fax.plot(x, ebitda, color=NAVY, marker="o", linewidth=2.3, label="EBITDA")
    fax.plot(x, ufcf, color=PALETTE["navy_3"], marker="o", linewidth=2.1, linestyle="--", label="UFCF")
    fax.set_xticks(x)
    fax.set_xticklabels(labels, fontsize=8)
    fax.set_ylabel(f"{currency}m", fontsize=8)
    fax.set_title("REVENUE, EBITDA AND UFCF", loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    fax.grid(True, axis="y", alpha=0.15)
    fax.legend(frameon=False, fontsize=8, ncols=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    for side in ("top", "right"):
        fax.spines[side].set_visible(False)

    terminal = forecast.iloc[-1]
    taxes = -float(terminal["taxes"])
    capex = -float(terminal["capex"])
    delta_nwc = -float(terminal["delta_nwc"])
    bridge_ax = fig.add_axes([0.62, 0.42, 0.34, 0.32])
    _waterfall_axes(
        bridge_ax,
        ["EBITDA", "Cash taxes", "Capex", "Change NWC", "UFCF"],
        [float(terminal["ebitda"]), taxes, capex, delta_nwc, float(terminal["ufcf"])],
        ["absolute", "relative", "relative", "relative", "total"],
        currency,
        "TERMINAL-YEAR UFCF BRIDGE",
    )

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.27, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.27, facecolor=GREEN))
    ax.text(0.038, 0.318, "FORECAST DRIVERS", fontsize=7.2, color=NAVY, weight="bold")
    segments = case.assumptions.segments or []
    total = sum(float(s.get("revenue_per_unit", 0)) * float(s.get("units", 1)) for s in segments) or 1.0
    rows = []
    for segment in segments[:4]:
        growth = segment.get("rpu_growth", {}).get("base", [])
        amount = float(segment.get("revenue_per_unit", 0)) * float(segment.get("units", 1))
        rows.append([segment.get("name", "Segment"), f"{amount / total:.0%}",
                     fmt_pct(growth[0] if growth else None), fmt_pct(growth[-1] if growth else None),
                     str(segment.get("source", "analyst"))[:24]])
    tax = fig.add_axes([0.038, 0.115, 0.60, 0.17])
    tax.axis("off")
    _table(tax, ["Segment", "LTM mix", "Y1 growth", "Y5 growth", "Source"], rows,
           bbox=[0, 0, 1, 1], colw=[0.27, 0.13, 0.14, 0.14, 0.32])
    notes = [
        f"D&A anchor: {case.assumptions.anchors['d_and_a_pct']:.1%} of revenue, checked against EBITDA minus EBIT.",
        f"Capex: {case.assumptions.scenarios['base'].capex_pct[0]:.1%} of revenue; working capital modeled using operating days.",
        "Scenario and sensitivity changes flow through the segment forecast instead of being ignored.",
    ]
    y = 0.292
    for note in notes:
        ax.text(0.67, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, note, 0.688, y, width=48, fontsize=7.7, color=SLATE, lh=0.018)
        y -= 0.067
    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def valuation_sensitivity_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    row = case.assessment.row
    fig = plt.figure(figsize=(12.8, 7.6), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, case.assessment)
    _section(ax, 0.018, 0.815, "Valuation Sensitivities", "Target price, terminal reasonableness and one-way driver analysis")

    h1 = fig.add_axes([0.055, 0.43, 0.40, 0.31])
    _annotated_heatmap(h1, case.sens_wacc_multiple, "TARGET PRICE | WACC x EXIT MULTIPLE", lambda v: f"{v:,.0f}", center=case.base.current_price)
    h1.set_xlabel("Exit EV / EBITDA", fontsize=8)
    h1.set_ylabel("WACC", fontsize=8)
    h2 = fig.add_axes([0.545, 0.43, 0.40, 0.31])
    _annotated_heatmap(h2, case.sens_implied_growth, "IMPLIED PERPETUITY GROWTH", lambda v: f"{v:+.1%}", center=case.assumptions.perpetuity_growth)
    h2.set_xlabel("Exit EV / EBITDA", fontsize=8)
    h2.set_ylabel("Terminal WACC", fontsize=8)

    tornado = case.tornado.sort_values("low_price")
    tax = fig.add_axes([0.08, 0.10, 0.55, 0.24])
    y = np.arange(len(tornado))
    tax.barh(y, tornado["high_price"] - tornado["low_price"], left=tornado["low_price"], color=BLUE, height=0.55)
    tax.axvline(case.base.target_price, color=NAVY, linewidth=1.5, linestyle="--")
    tax.set_yticks(y)
    tax.set_yticklabels(tornado["driver"], fontsize=7.6)
    tax.set_xlabel("Implied share price", fontsize=8)
    tax.set_title("TORNADO | ONE-WAY DRIVER SENSITIVITY", loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    tax.grid(True, axis="x", alpha=0.15)
    for side in ("top", "right", "left"):
        tax.spines[side].set_visible(False)

    ax.add_patch(Rectangle((0.68, 0.09), 0.302, 0.26, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.68, 0.09), 0.004, 0.26, facecolor=PALETTE["navy_3"]))
    ax.text(0.698, 0.318, "READ-THROUGH", fontsize=7.2, color=NAVY, weight="bold")
    notes = [
        f"Base target: {_price(case.base.target_price)} versus current {_price(case.base.current_price)}.",
        f"Largest one-way driver: {case.tornado.iloc[0]['driver']}.",
        "The implied-growth grid checks whether a selected exit multiple embeds a credible growth-forever assumption.",
    ]
    yy = 0.285
    for note in notes:
        ax.text(0.700, yy, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, note, 0.718, yy, width=39, fontsize=7.7, color=SLATE, lh=0.018)
        yy -= 0.070
    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def valuation_bridges_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    row, base = case.assessment.row, case.base
    currency = str(row.get("currency", "USD"))
    fig = plt.figure(figsize=(12.8, 7.3), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, case.assessment)
    _section(ax, 0.018, 0.815, "Terminal Value & Equity Bridge", "Reconcile enterprise value, debt-like claims and share-price implications")

    left = fig.add_axes([0.055, 0.38, 0.52, 0.35])
    bridge_labels = ["PV explicit FCF", "PV terminal value", "Enterprise value", "Net debt", "Minority", "Preferred", "Equity value"]
    bridge_values = [base.pv_explicit, base.pv_terminal_exit, base.enterprise_value,
                     -base.net_debt, -base.minority_interest, -base.preferred_equity, base.implied_equity]
    bridge_measures = ["absolute", "relative", "total", "relative", "relative", "relative", "total"]
    _waterfall_axes(left, bridge_labels, bridge_values, bridge_measures, currency, "BASE-CASE EQUITY VALUE BRIDGE")

    right = fig.add_axes([0.65, 0.40, 0.30, 0.32])
    market_pv = base.pv_terminal_exit * case.market_reference_multiple / case.exit_multiple if case.market_reference_multiple else np.nan
    values = [base.pv_terminal_exit, base.pv_terminal_perp, market_pv]
    labels = [f"Exit {case.exit_multiple:.1f}x", f"Perpetuity {case.assumptions.perpetuity_growth:.1%}", "Peer reference"]
    bars = right.bar(labels, values, color=[BLUE, PALETTE["navy"], PALETTE["navy_3"]], width=0.58)
    for bar, value in zip(bars, values):
        if np.isfinite(value):
            right.text(bar.get_x() + bar.get_width()/2, value, f"{value:,.0f}", ha="center", va="bottom", fontsize=7.6)
    right.set_title("PV OF TERMINAL VALUE", loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    right.set_ylabel(f"{currency}m", fontsize=8)
    right.tick_params(axis="x", labelsize=7.5, rotation=12)
    right.grid(True, axis="y", alpha=0.15)
    for side in ("top", "right"):
        right.spines[side].set_visible(False)

    perp_equity = base.enterprise_value_perp - base.net_debt - base.minority_interest - base.preferred_equity
    perp_target = base.current_price * perp_equity / base.market_cap if base.current_price and base.market_cap else np.nan
    cards = [
        ("Current price", _price(base.current_price), "market anchor"),
        ("Exit-method target", _price(base.target_price), _pct_signed(base.upside)),
        ("Perpetuity target", _price(perp_target), f"implied {base.implied_exit_multiple:.1f}x" if base.implied_exit_multiple else "n/a"),
        ("Terminal value / EV", fmt_pct(base.terminal_pct_of_ev), "dependency check"),
    ]
    gap, w = 0.014, (0.964 - 0.014 * 3) / 4
    for i, (label, value, note) in enumerate(cards):
        x0 = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x0, 0.16), w, 0.11, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x0, 0.265), w, 0.005, facecolor=[BLUE, NAVY, PALETTE["navy_3"], LINE][i]))
        ax.text(x0 + 0.012, 0.238, label.upper(), fontsize=6.7, color=MUTED, weight="bold")
        ax.text(x0 + 0.012, 0.204, value, fontsize=15, color=INK, weight="bold")
        ax.text(x0 + 0.012, 0.178, note, fontsize=6.8, color=MUTED)
    gap_pct = base.enterprise_value_perp / base.enterprise_value - 1.0
    ax.text(0.018, 0.095, f"METHOD RECONCILIATION: perpetuity EV is {gap_pct:+.1%} versus the exit-multiple EV. "
            "The difference is disclosed because the analyst exit multiple and stable-growth economics are independent checks.",
            fontsize=8.0, color=SLATE)
    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def valuation_assumptions_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    row, wacc = case.assessment.row, case.wacc
    fig = plt.figure(figsize=(12.8, 7.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, row, case.assessment)
    _section(ax, 0.018, 0.815, "WACC & Assumption Provenance", "Every material input is labeled as analyst, Capital IQ or derived")

    wax = fig.add_axes([0.07, 0.42, 0.40, 0.30])
    labels = ["Risk-free", "Beta x ERP", "After-tax debt", "WACC", "Terminal WACC"]
    values = [wacc.risk_free_rate, wacc.beta * wacc.equity_risk_premium,
              wacc.cost_of_debt_aftertax, wacc.wacc, case.base.terminal_wacc]
    bars = wax.barh(labels, values, color=[PALETTE["line"], BLUE, PALETTE["navy_3"], NAVY, BLUE])
    for bar, value in zip(bars, values):
        wax.text(value, bar.get_y() + bar.get_height()/2, f" {value:.1%}", va="center", fontsize=8, color=INK)
    wax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    wax.set_title("WACC BUILD", loc="left", fontsize=9, color=NAVY, weight="bold", pad=10)
    wax.grid(True, axis="x", alpha=0.15)
    for side in ("top", "right", "left"):
        wax.spines[side].set_visible(False)

    base = case.assumptions.scenarios["base"]
    rows = [
        ["Revenue growth", fmt_pct(base.revenue_growth[0]), fmt_pct(base.revenue_growth[-1]), "Analyst glidepath"],
        ["EBITDA margin", fmt_pct(base.ebitda_margin[0]), fmt_pct(base.ebitda_margin[-1]), "Analyst glidepath"],
        ["D&A / revenue", fmt_pct(base.d_and_a_pct[0]), fmt_pct(base.d_and_a_pct[-1]), "Validated historical anchor"],
        ["Capex / revenue", fmt_pct(base.capex_pct[0]), fmt_pct(base.capex_pct[-1]), "Analyst assumption"],
        ["Exit EV / EBITDA", fmt_multiple(case.exit_multiple), fmt_multiple(case.exit_multiple), case.exit_multiple_source],
        ["Perpetuity growth", fmt_pct(case.assumptions.perpetuity_growth), fmt_pct(case.assumptions.perpetuity_growth), case.assumptions.perpetuity_source],
        ["Terminal ROIC", fmt_pct(case.base.terminal_roic), fmt_pct(case.base.terminal_roic), case.assumptions.terminal_roic_source],
    ]
    tax = fig.add_axes([0.53, 0.40, 0.452, 0.33])
    tax.axis("off")
    _table(tax, ["Driver", "Y1", "Terminal", "Provenance"], rows, bbox=[0, 0, 1, 1], colw=[0.26, 0.16, 0.18, 0.40])

    ax.add_patch(Rectangle((0.018, 0.075), 0.964, 0.25, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.075), 0.004, 0.25, facecolor=GREEN))
    ax.text(0.038, 0.292, "CONTROL NOTES", fontsize=7.2, color=NAVY, weight="bold")
    notes = [
        f"Beta {wacc.beta:.2f} from {wacc.beta_source}; capital weights use current market equity and reported debt.",
        f"WACC {wacc.wacc:.1%} is an analyst override; computed economics remain disclosed in the model notes.",
        f"Peer set: {case.assessment.peer_set_name}; reviewed status: {'approved' if case.assessment.peer_reviewed else 'pending analyst approval'}.",
        "The Lululemon assumptions remain draft, so outputs are labeled indicative rather than a formal recommendation.",
    ]
    y = 0.255
    for note in notes:
        ax.text(0.040, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, note, 0.058, y, width=135, fontsize=8.0, color=SLATE, lh=0.018)
        y -= 0.052
    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


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
        warnings = [{"severity": "info", "text": "Draft assumptions and unreviewed peers: indicative calibration, not a formal recommendation."}]
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
    _table(tax, ["Multiple", "Role", "Current", "Peer med.\n(ex-company)", "Premium", "History", "Read"],
           rows, bbox=[0, 0, 1, 1], colw=[0.16, 0.14, 0.12, 0.12, 0.11, 0.14, 0.16])

    bx = fig.add_axes([0.07, 0.12, 0.40, 0.28])
    if bar_items:
        labels = [m["label"] for m in bar_items]
        x = np.arange(len(labels))
        bx.bar(x - 0.18, [m["current"] for m in bar_items], width=0.36, color=GREEN, label="Company")
        bx.bar(x + 0.18, [m["peer_median"] for m in bar_items], width=0.36, color=PEER,
               label="Peer median (ex-company)")
        bx.set_xticks(x)
        bx.set_xticklabels(labels, fontsize=8, rotation=0)
        bx.set_ylabel("Multiple", fontsize=8)
        bx.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}x")
        bx.grid(True, axis="y", alpha=0.18)
        bx.legend(frameon=False, fontsize=8, ncols=2, loc="lower center", bbox_to_anchor=(0.5, 1.02))
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
        "LTM completeness and stale periods are flagged before using multiples.",
        "Extreme multiples are excluded from adjusted peer medians.",
    ]
    y = 0.255
    for control in controls:
        ax.text(0.028, y, u"\u2022", fontsize=10, color=GREEN, va="top")
        _wrapped(ax, control, 0.044, y, width=60, fontsize=7.8, color=SLATE, lh=0.017)
        y -= 0.042

    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def ic_memo_snapshot(path: Path) -> None:
    df, cid = _load()
    case = _case(df, cid)
    if case is None:
        company_tearsheet(path)
        return
    a, base = case.assessment, case.base
    thesis = a.thesis
    fig = plt.figure(figsize=(12.8, 7.8), dpi=150)
    fig.patch.set_facecolor(BG)
    ax = _bg_axes(fig)
    _header_clean(ax, a.row, a)
    _section(ax, 0.018, 0.815, "Investment Committee Memo", "Machine-checked evidence plus explicit analyst judgment")

    cards = [
        ("Analytical status", case.recommendation.stance, "draft assumptions"),
        ("Current price", _price(base.current_price), "market reference"),
        ("Base target", _price(base.target_price), _pct_signed(base.upside)),
        ("Peer discount", a.valuation.get("premium_label", "n/a"), a.valuation.get("multiple_name", "")),
        ("Attention score", f"{a.attention_score:.0f}", "diligence priority"),
    ]
    gap, w = 0.012, (0.964 - 0.012 * 4) / 5
    for i, (label, value, note) in enumerate(cards):
        x = 0.018 + i * (w + gap)
        ax.add_patch(Rectangle((x, 0.70), w, 0.10, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.add_patch(Rectangle((x, 0.795), w, 0.005, facecolor=BLUE if i in (1, 2) else PALETTE["navy_3"]))
        ax.text(x + 0.010, 0.770, label.upper(), fontsize=6.5, color=MUTED, weight="bold")
        ax.text(x + 0.010, 0.738, str(value), fontsize=13.5, color=INK, weight="bold")
        ax.text(x + 0.010, 0.715, str(note), fontsize=6.5, color=MUTED)

    ax.add_patch(Rectangle((0.018, 0.39), 0.47, 0.27, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.018, 0.39), 0.004, 0.27, facecolor=GREEN))
    ax.text(0.038, 0.630, "THESIS & VARIANT PERCEPTION", fontsize=7.2, color=NAVY, weight="bold")
    thesis_text = thesis.thesis if thesis else a.sponsor_view
    variant = thesis.variant_perception if thesis else a.verdict_rationale
    _wrapped(ax, thesis_text, 0.038, 0.602, width=80, fontsize=7.6, color=SLATE, style="italic", lh=0.018)
    ax.text(0.038, 0.485, "VARIANT VIEW", fontsize=6.8, color=MUTED, weight="bold")
    _wrapped(ax, variant, 0.038, 0.460, width=80, fontsize=7.2, color=SLATE, lh=0.016)

    ax.add_patch(Rectangle((0.512, 0.39), 0.47, 0.27, facecolor="white", edgecolor=LINE, linewidth=0.8))
    ax.add_patch(Rectangle((0.512, 0.39), 0.004, 0.27, facecolor=PALETTE["navy_3"]))
    ax.text(0.532, 0.630, "KEY DEBATE", fontsize=7.2, color=NAVY, weight="bold")
    debate = thesis.key_debate if thesis else a.sponsor_view
    _wrapped(ax, debate, 0.532, 0.602, width=68, fontsize=8.0, color=SLATE, style="italic", lh=0.020)
    ax.text(0.532, 0.485, "WHAT NEEDS TO BE TRUE", fontsize=6.8, color=MUTED, weight="bold")
    conditions = a.valuation.get("what_needs_to_be_true", [])[:3]
    y = 0.458
    for condition in conditions:
        ax.text(0.534, y, u"\u2022", fontsize=9, color=GREEN, va="top")
        _wrapped(ax, condition, 0.550, y, width=60, fontsize=7.5, color=SLATE, lh=0.017)
        y -= 0.055

    _section(ax, 0.018, 0.355, "Catalysts, Risks & Management Questions")
    columns = [
        ("CATALYSTS", [f"{c.get('date')}: {c.get('event')}" for c in (thesis.catalysts[:3] if thesis else [])]),
        ("KEY RISKS", thesis.risks[:3] if thesis else a.concerns[:3]),
        ("QUESTIONS FOR MANAGEMENT", thesis.management_questions[:3] if thesis else a.management_questions[:3]),
    ]
    widths = [0.30, 0.31, 0.325]
    x = 0.018
    for (label, items), width in zip(columns, widths):
        ax.add_patch(Rectangle((x, 0.075), width, 0.235, facecolor="white", edgecolor=LINE, linewidth=0.8))
        ax.text(x + 0.015, 0.280, label, fontsize=7, color=NAVY, weight="bold")
        y = 0.250
        for item in items:
            ax.text(x + 0.015, y, u"\u2022", fontsize=9, color=GREEN, va="top")
            _wrapped(ax, str(item), x + 0.032, y, width=max(30, int(width * 170)), fontsize=7.2, color=SLATE, lh=0.016)
            y -= 0.060
        x += width + 0.014
    fig.savefig(path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate README screenshots from demo or private data.")
    parser.add_argument("--private", action="store_true", help="Use local Capital IQ-derived private data.")
    parser.add_argument("--company-id", default=None, help="Anchor company ID, e.g. NASDAQ:LULU.")
    args = parser.parse_args()
    global SCREENSHOT_DEMO, SHOWCASE_COMPANY_ID
    SCREENSHOT_DEMO = not args.private
    if args.company_id:
        SHOWCASE_COMPANY_ID = args.company_id
    ensure_dir(REPORTS_SAMPLE_DIR)
    watchlist_overview(REPORTS_SAMPLE_DIR / "01_watchlist_overview.png")
    kpi_dashboard(REPORTS_SAMPLE_DIR / "02_company_situation.png")
    company_tearsheet(REPORTS_SAMPLE_DIR / "03_company_financials.png")
    comparison_snapshot(REPORTS_SAMPLE_DIR / "04_compare_companies.png")
    peer_benchmarking(REPORTS_SAMPLE_DIR / "05_peer_benchmarking.png")
    consensus_snapshot(REPORTS_SAMPLE_DIR / "06_actual_vs_consensus.png")
    capital_structure_snapshot(REPORTS_SAMPLE_DIR / "07_capital_structure.png")
    valuation_case_snapshot(REPORTS_SAMPLE_DIR / "08_valuation_case.png")
    valuation_forecast_snapshot(REPORTS_SAMPLE_DIR / "09_operating_forecast.png")
    valuation_sensitivity_snapshot(REPORTS_SAMPLE_DIR / "10_dcf_sensitivity.png")
    valuation_bridges_snapshot(REPORTS_SAMPLE_DIR / "11_terminal_value_bridges.png")
    valuation_assumptions_snapshot(REPORTS_SAMPLE_DIR / "12_wacc_assumptions.png")
    football_field_snapshot(REPORTS_SAMPLE_DIR / "13_football_field.png")
    multiples_scorecard_snapshot(REPORTS_SAMPLE_DIR / "14_multiples_scorecard.png")
    data_audit_snapshot(REPORTS_SAMPLE_DIR / "15_data_audit.png")
    ic_memo_snapshot(REPORTS_SAMPLE_DIR / "16_ic_memo.png")
    print(f"Sample screenshots written to {REPORTS_SAMPLE_DIR}")


if __name__ == "__main__":
    main()
