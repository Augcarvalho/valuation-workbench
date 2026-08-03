"""Shared app runtime: data mode, cached loaders, and small display helpers.

Everything a page needs beyond its own domain imports lives here, so page
modules stay focused on layout and the data path stays in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.config import (
    DEFAULT_PROCESSED_DATASET,
    DEFAULT_SOURCE_LOG,
    PRIVATE_PROCESSED_DATASET,
    PRIVATE_SOURCE_LOG,
)
from src.ingestion.store import load_store
from src.modeling.assessment import watchlist_summary
from src.pipeline.build_dataset import build_dataset
from src.utils import fmt_money, fmt_multiple, fmt_pct

DEMO_MODE = "--demo" in sys.argv

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

PAGES = {
    "SCREEN": ["Watchlist Home", "Compare"],
    "UNDERWRITE": ["Company Situation", "Peer Benchmarking", "Company Financials",
                   "Capital Structure", "Valuation Case"],
    "MONITOR": ["Actual vs Consensus", "Valuation & Expectations"],
    "GOVERNANCE": ["IC Memo Export", "Data Audit", "Data & Refresh"],
}


# --- data ---------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _read_dataset(path_str: str, mtime: float) -> pd.DataFrame:
    # mtime keys the cache so a rebuilt dataset is picked up without restart.
    df = pd.read_csv(path_str, parse_dates=["period"])
    return df.sort_values(["company_id", "period"])


def _dataset_path(demo: bool) -> Path:
    if demo or not PRIVATE_PROCESSED_DATASET.exists():
        return DEFAULT_PROCESSED_DATASET
    return PRIVATE_PROCESSED_DATASET


def load_data(demo: bool) -> pd.DataFrame:
    if demo or not DEFAULT_PROCESSED_DATASET.exists():
        build_dataset("public-demo")
    path = _dataset_path(demo)
    return _read_dataset(str(path), path.stat().st_mtime)


def get_store(demo: bool):
    return load_store(demo)


@st.cache_data(show_spinner="Ranking the watchlist…")
def _summary_cached(demo: bool, dataset_mtime: float, side_key: str) -> pd.DataFrame:
    df = load_data(demo)
    return watchlist_summary(df, store=get_store(demo))


def load_summary(demo: bool) -> pd.DataFrame:
    path = _dataset_path(demo)
    store = get_store(demo)
    side_key = f"{len(store.valuation_history)}-{len(store.estimates)}-{store.theses_dir}"
    return _summary_cached(demo, path.stat().st_mtime, side_key)


def load_source_log(demo: bool) -> pd.DataFrame:
    source_path = DEFAULT_SOURCE_LOG if demo else PRIVATE_SOURCE_LOG
    if source_path.exists():
        return pd.read_csv(source_path)
    if DEFAULT_SOURCE_LOG.exists():
        return pd.read_csv(DEFAULT_SOURCE_LOG)
    return pd.DataFrame(columns=["table_name", "source_name", "source_url", "retrieved_at", "notes"])


# --- shared display helpers -----------------------------------------------------

def tone(text: str, good: bool | None) -> str:
    if good is True:
        return f'<span class="tone-green">{text}</span>'
    if good is False:
        return f'<span class="tone-red">{text}</span>'
    return text


def verdict_pill(verdict_key: str, label: str) -> str:
    from src.branding import PALETTE, VERDICT_COLORS

    color = VERDICT_COLORS.get(verdict_key, PALETTE["muted_2"])
    soft = {
        "do_work": PALETTE["amber_soft"],
        "constructive": PALETTE["green_soft"],
        "avoid": PALETTE["red_soft"],
    }.get(verdict_key, PALETTE["panel_alt"])
    return (
        f'<span class="cell-pill" style="background:{soft};color:{color};white-space:nowrap">{label}</span>'
    )


def snapshot_financials(row: pd.Series, currency: str) -> None:
    def pct_tone(v):
        return tone(fmt_pct(v), (v > 0) if pd.notna(v) else None)

    rows = [
        ["Revenue", fmt_money(row.get("revenue"), currency), fmt_money(row.get("revenue_ttm"), currency),
         pct_tone(row.get("revenue_yoy_growth"))],
        ["Gross profit", fmt_money(row.get("gross_profit"), currency), fmt_money(row.get("gross_profit_ttm"), currency),
         fmt_pct(row.get("gross_margin_ttm"))],
        ["EBITDA", fmt_money(row.get("ebitda"), currency), fmt_money(row.get("ebitda_ttm"), currency),
         fmt_pct(row.get("ebitda_margin_ttm"))],
        ["Net income", fmt_money(row.get("net_income"), currency), fmt_money(row.get("net_income_ttm"), currency),
         fmt_pct(row.get("net_income_margin_ttm"))],
        ["CFO", fmt_money(row.get("cfo"), currency), fmt_money(row.get("cfo_ttm"), currency), "--"],
        ["Free cash flow", fmt_money(row.get("fcf"), currency), fmt_money(row.get("fcf_ttm"), currency),
         fmt_pct(row.get("fcf_conversion_ttm"))],
    ]
    if pd.notna(row.get("sbc_ttm")):
        rows.append(["Stock-based comp", fmt_money(row.get("sbc"), currency), fmt_money(row.get("sbc_ttm"), currency),
                     fmt_pct(row.get("sbc_pct_of_fcf_ttm"))])
    ui.html_table(["Metric", "Latest Reported Quarter", "LTM", "Growth / LTM Margin"], rows)


def snapshot_valuation(row: pd.Series, currency: str) -> None:
    rows = [
        ["Market cap", fmt_money(row.get("market_cap"), currency)],
        ["Net debt", fmt_money(row.get("net_debt"), currency)],
        ["Enterprise value", fmt_money(row.get("enterprise_value"), currency)],
        ["EV / Revenue (LTM)", fmt_multiple(row.get("ev_to_revenue_ttm"))],
        ["EV / EBITDA (LTM)", fmt_multiple(row.get("ev_to_ebitda_ttm"))],
        ["P / E (LTM)", fmt_multiple(row.get("pe_ttm"))],
        ["Net debt / EBITDA (LTM)", fmt_multiple(row.get("net_debt_to_ebitda_ttm"))],
        ["ROIC (LTM)", fmt_pct(row.get("roic_ttm"))],
    ]
    ui.html_table(["Trading & Valuation", "Current Market Snapshot / LTM Denominator"], rows)
