"""Capital Structure: EV bridge, covenant headroom, debt capacity."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store
from src.modeling.assessment import Kpi, build_assessment
from src.reporting.charts import leverage_chart
from src.reporting.periods import company_snapshot_context


def render(df: pd.DataFrame, company_id: str) -> None:
    import src.reporting.valuation_charts as vch

    from src.modeling.capital_structure import build_capital_structure, ev_bridge, leverage_history

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    ui.header_band(row, DEMO_MODE)

    cs = build_capital_structure(row)
    if not cs.applicable:
        ui.section("Capital Structure", "Financial institution")
        st.info(cs.warnings[0])
        st.markdown("See the **Financials Valuation** section on the Valuation Case page "
                    "for the applicable framework (P/E, P/B, ROE vs COE, excess returns).")
        return

    ui.section("Leverage Today",
               f"{company_snapshot_context(store, row)} | {currency}m | leverage and coverage use LTM denominators")
    ui.kpi_grid([
        Kpi("nd", "Net Debt", f"{cs.net_debt:,.0f}" if cs.net_debt is not None else "n/a",
            f"gross {cs.gross_debt:,.0f} - cash & ST investments {cs.cash:,.0f}"
            if cs.gross_debt is not None and cs.cash is not None else "",
            "n/a"),
        Kpi("lev", "Net Leverage", f"{cs.net_leverage:.1f}x" if cs.net_leverage is not None else "n/a",
            "net debt / EBITDA",
            "green" if (cs.net_leverage or 9) < 2 else ("yellow" if (cs.net_leverage or 9) < 3.5 else "red")),
        Kpi("cov", "Interest Coverage", f"{cs.interest_coverage:.1f}x" if cs.interest_coverage else "n/a",
            "EBITDA / cash interest",
            "green" if (cs.interest_coverage or 0) > 4 else ("yellow" if (cs.interest_coverage or 0) > 2 else "red")),
        Kpi("ltv", "Net Debt % of EV", f"{cs.net_debt_pct_ev:.0%}" if cs.net_debt_pct_ev is not None else "n/a",
            "illustrative LTV", "n/a"),
        Kpi("cash", "Cash % of Debt", f"{cs.cash_pct_debt:.0%}" if cs.cash_pct_debt is not None else "n/a",
            "liquidity vs gross debt", "n/a"),
    ], columns=5)

    ui.section("Debt Capacity", "Gross-debt capacity constrained by leverage and minimum coverage")
    rows = []
    for turns in sorted(cs.underwritten_capacity):
        rows.append([
            f"{turns:.1f}x EBITDA",
            f"{cs.capacity[turns]:,.0f}",
            f"{cs.coverage_capacity:,.0f}" if cs.coverage_capacity is not None else "n/a",
            f"{cs.underwritten_capacity[turns]:,.0f}",
            f"{cs.underwritten_incremental[turns]:+,.0f}",
            cs.limiting_constraint[turns],
        ])
    ui.html_table([
        "Leverage level", f"Leverage cap ({currency}m)", f"Coverage cap ({currency}m)",
        f"Underwritten gross debt ({currency}m)", "Incremental gross debt", "Binding constraint",
    ], rows, numeric_from=1)
    ui.kpi_grid([
        Kpi("hl", "Covenant Headroom (Leverage)",
            f"{cs.leverage_headroom:+.1f}x" if cs.leverage_headroom is not None else "n/a",
            "vs 4.0x net-leverage covenant proxy",
            "green" if (cs.leverage_headroom or -1) > 1 else ("yellow" if (cs.leverage_headroom or -1) > 0 else "red")),
        Kpi("hc", "Covenant Headroom (Coverage)",
            f"{cs.coverage_headroom:+.1f}x" if cs.coverage_headroom is not None else "n/a",
            "vs 2.0x interest-coverage floor",
            "green" if (cs.coverage_headroom or -1) > 1 else ("yellow" if (cs.coverage_headroom or -1) > 0 else "red")),
        Kpi("sp", "Incremental Debt Capacity",
            f"{cs.sponsor_leverage_capacity:,.0f}" if cs.sponsor_leverage_capacity is not None else "n/a",
            "lesser of 4.0x leverage and coverage capacity", "n/a"),
        Kpi("mc", "Minimum Cash",
            f"{cs.minimum_cash:,.0f}" if cs.minimum_cash is not None else "n/a",
            "preserved for operations; review manually", "n/a"),
    ], columns=4)

    ui.section("Current EV Bridge", "Calculated vs reported enterprise value")
    bridge = ev_bridge(row)
    st.plotly_chart(vch.current_ev_bridge_chart(bridge), use_container_width=True, config=PLOTLY_CONFIG)
    if bridge.get("mismatch"):
        st.warning(f"Calculated EV differs from the reported CapIQ TEV by {bridge['gap']:+.0%} - "
                   "check as-of dates, pensions, minority interests and exact share counts.")

    hist = leverage_history(df, company_id)
    if not hist.empty and "net_debt" in hist.columns:
        ui.section("Leverage Trend")
        st.plotly_chart(leverage_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    for w in cs.warnings:
        ui.footnote(w)
    ui.footnote("Covenant thresholds (4.0x leverage, 2.0x coverage) are screening proxies, "
                "not actual credit-document terms. Capacity preserves minimum cash and uses the lower "
                "of gross-leverage and interest-coverage constraints; it remains subject to lender review.")
