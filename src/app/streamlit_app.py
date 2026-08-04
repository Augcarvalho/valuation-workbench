"""Streamlit entry point: page config, sidebar, and routing.

Page content lives in src/app/pages/ (one module per page, each exposing
``render(df, company_id)``); shared runtime in src/app/context.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when launched via `streamlit run`,
# which otherwise only puts the script's own directory on sys.path.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Valuation Workbench",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.app import components as ui                      # noqa: E402
from src.app.context import DEMO_MODE, PAGES, load_data   # noqa: E402
from src.app.pages import (                               # noqa: E402
    capital_structure,
    consensus,
    data_audit,
    financials,
    ic_memo,
    operating_drivers,
    peers,
    situation,
    valuation_case,
    watchlist,
)
from src.app.theme import inject_theme                    # noqa: E402
from src.modeling.metrics import latest_rows              # noqa: E402

inject_theme()

ROUTES = {
    "Watchlist Home": watchlist.render,
    "Company Situation": situation.render,
    "Peer Benchmarking": peers.render,
    "Operating Drivers": operating_drivers.render,
    "Actual vs Consensus": consensus.render,
    "Company Financials": financials.render,
    "Capital Structure": capital_structure.render,
    "Valuation Case": valuation_case.render,
    "IC Memo Export": ic_memo.render,
    "Data Audit & Refresh": data_audit.render,
}


def sidebar(df: pd.DataFrame) -> tuple[str, str]:
    st.sidebar.markdown(
        '<div class="sb-brand">Valuation Workbench</div><div class="sb-brand-rule"></div>'
        '<div class="sb-sub">Thesis-Driven Coverage</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<div class="sb-group">Company</div>', unsafe_allow_html=True)
    latest = latest_rows(df)
    if "coverage_role" in latest.columns:
        selectable = latest[latest["coverage_role"].fillna("watchlist") == "watchlist"].copy()
    else:
        selectable = latest
    if selectable.empty:
        selectable = latest
    labels = {
        f"{row.ticker.replace('.SA', '')} | {row.company_name}": row.company_id
        for row in selectable.sort_values("ticker").itertuples()
    }
    selection = st.sidebar.selectbox("Select company", list(labels.keys()), label_visibility="collapsed")
    company_id = labels[selection]

    st.sidebar.markdown('<div class="sb-group">Views</div>', unsafe_allow_html=True)
    flat_pages = [p for group in PAGES.values() for p in group]
    page = st.sidebar.radio("Views", flat_pages, label_visibility="collapsed")

    row = latest[latest["company_id"] == company_id].iloc[0]
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    mode = "Public Demo" if DEMO_MODE else "Capital IQ - Private"
    st.sidebar.markdown(
        f'<div class="sb-sub">Data mode<br><b style="color:#fff">{mode}</b></div>'
        f'<div class="sb-sub" style="margin-top:10px">Financials through {ui.as_of_label(row["period"])}</div>'
        f'<div class="sb-sub" style="margin-top:14px;color:#7f96ad;font-size:10.5px;line-height:1.5">'
        f'Illustrative watchlist artifact. Not investment advice. '
        f'Licensed Capital IQ exports stay in <code>data_private/</code>.</div>',
        unsafe_allow_html=True,
    )
    return company_id, page


def main() -> None:
    df = load_data(DEMO_MODE)
    company_id, page = sidebar(df)
    ROUTES.get(page, watchlist.render)(df, company_id)


if __name__ == "__main__":
    main()
