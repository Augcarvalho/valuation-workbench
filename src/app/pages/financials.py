"""Company Financials: operating trends, cash, leverage."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store, snapshot_financials, snapshot_valuation, tone
from src.modeling.assessment import Kpi, build_assessment
from src.reporting.charts import cash_conversion_chart, leverage_chart, margin_trend_chart, revenue_ebitda_chart
from src.reporting.periods import company_snapshot_context
from src.utils import fmt_money, fmt_multiple, fmt_pct, fmt_signed_pct


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    ui.header_band(row, DEMO_MODE)

    ui.section("Financial Snapshot",
               f"{company_snapshot_context(store, row)} | LTM = trailing four reported quarters")
    fcol, vcol = st.columns([1.25, 1.0], gap="medium")
    with fcol:
        snapshot_financials(row, currency)
    with vcol:
        snapshot_valuation(row, currency)

    ui.section("Quarterly Performance",
               "Standalone reported quarters; growth is YoY, while FCF conversion is rolling LTM")
    history = df[df["company_id"] == company_id].sort_values("period").tail(8)
    headers = ["Reported Quarter", "Revenue (Quarter)", "Rev Growth (Quarter YoY)",
               "EBITDA (Quarter)", "EBITDA Margin (Quarter)", "FCF (Quarter)", "FCF Conv. (LTM)"]
    rows, classes = [], []
    for _, h in history.iterrows():
        g = h.get("revenue_yoy_growth")
        rows.append([
            ui.quarter_label(h["period"]),
            fmt_money(h.get("revenue"), currency),
            tone(fmt_signed_pct(g), (g > 0) if pd.notna(g) else None),
            fmt_money(h.get("ebitda"), currency),
            fmt_pct(h.get("ebitda_margin")),
            fmt_money(h.get("fcf"), currency),
            fmt_pct(h.get("fcf_conversion_ttm")),
        ])
        classes.append("anchor" if h["period"] == row["period"] else "")
    ui.html_table(headers, rows, classes)

    ui.section("Operating Profile")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(revenue_ebitda_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(margin_trend_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Cash, Working Capital & Leverage")
    cards = [
        Kpi("cfo", "CFO (LTM)", fmt_money(row.get("cfo_ttm"), currency), "Trailing four reported quarters"),
        Kpi("fcf", "FCF (LTM)", fmt_money(row.get("fcf_ttm"), currency), "LTM CFO less LTM capex"),
        Kpi("conv", "FCF Conversion (LTM)", fmt_pct(row.get("fcf_conversion_ttm")), "LTM FCF / LTM EBITDA",
            row.get("fcf_conversion_ttm_signal", "n/a")),
        Kpi("roic", "ROIC (LTM)", fmt_pct(row.get("roic_ttm")), "LTM NOPAT / average invested capital",
            row.get("roic_ttm_signal", "n/a")),
        Kpi("ccc", "Cash Conversion Cycle",
            f"{row.get('cash_conversion_cycle'):.0f}d" if pd.notna(row.get("cash_conversion_cycle")) else "n/a",
            "DSO + DIO − DPO"),
        Kpi("lev", "Net Debt / EBITDA (LTM)", fmt_multiple(row.get("net_debt_to_ebitda_ttm")), "Current net debt / LTM EBITDA",
            row.get("net_debt_to_ebitda_ttm_signal", "n/a")),
    ]
    ui.kpi_grid(cards, columns=6)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(cash_conversion_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(leverage_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
