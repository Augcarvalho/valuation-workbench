"""Operating Drivers: company-specific revenue architecture and data coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, get_store
from src.app.operating_driver_view import render_operating_driver_build
from src.modeling.assessment import build_assessment
from src.modeling.operating_drivers import (
    COMPANY_PROFILE,
    build_operating_driver_model,
)
from src.modeling.valuation_case import build_valuation_case, dcf_applicability


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    assessment = build_assessment(df, company_id, store=store)
    row = assessment.row
    ui.header_band(row, DEMO_MODE)

    applicable, _, _ = dcf_applicability(row)
    if applicable:
        case = build_valuation_case(df, company_id, store=store)
        render_operating_driver_build(case, str(row.get("currency", "LC")))
        _render_watchlist_coverage(df, store)
        return

    anchor = row.get("revenue_yoy_growth")
    anchor = float(anchor) if pd.notna(anchor) else 0.04
    scenario_growth = {
        "bear": [max(anchor - 0.05, -0.10), 0.00, 0.01, 0.02, 0.025],
        "base": [anchor, 0.04, 0.035, 0.03, 0.025],
        "bull": [min(anchor + 0.05, 0.40), 0.08, 0.06, 0.04, 0.03],
    }
    build = build_operating_driver_model(
        row,
        store.operating_kpis,
        store.company_segments,
        scenario_growth,
        {},
        5,
    )
    case = SimpleNamespace(
        company_id=company_id,
        assumptions=SimpleNamespace(operating_driver_build=build),
    )
    render_operating_driver_build(case, str(row.get("currency", "LC")))
    ui.footnote(
        "For financial institutions this page governs operating revenue drivers; "
        "valuation remains on P/E, P/TBV and excess-return methods rather than EBITDA DCF."
    )
    _render_watchlist_coverage(df, store)


def _render_watchlist_coverage(df: pd.DataFrame, store) -> None:
    """Disclose the operating-data queue for every monitored company."""
    latest = (
        df[df["company_id"].astype(str).isin(COMPANY_PROFILE)]
        .sort_values("period")
        .groupby("company_id", as_index=False)
        .tail(1)
        .set_index("company_id")
    )
    rows: list[list[str]] = []
    for candidate_id in COMPANY_PROFILE:
        if candidate_id not in latest.index:
            continue
        candidate = latest.loc[candidate_id]
        anchor = candidate.get("revenue_yoy_growth")
        anchor = float(anchor) if pd.notna(anchor) else 0.04
        growth = {
            "bear": [max(anchor - 0.05, -0.10), 0.00, 0.01, 0.02, 0.025],
            "base": [anchor, 0.04, 0.035, 0.03, 0.025],
            "bull": [min(anchor + 0.05, 0.40), 0.08, 0.06, 0.04, 0.03],
        }
        build = build_operating_driver_model(
            candidate,
            store.operating_kpis,
            store.company_segments,
            growth,
            {},
            5,
        )
        rows.append([
            candidate_id.split(":")[-1],
            build.profile.label,
            f"Tier {build.tier}",
            f"{build.coverage_pct:.0%}",
            ", ".join(metric.replace("_", " ") for metric in build.missing_metrics) or "Complete",
        ])

    with st.expander("Watchlist operating-driver coverage and next Excel refresh queue"):
        ui.footnote(
            "Tier 3 = physical KPIs; Tier 2 = reported segments; Tier 1 = reviewed "
            "consolidated growth. Missing fields are never synthetically populated."
        )
        ui.html_table(
            ["Ticker", "Revenue architecture", "Current tier", "Physical KPI coverage", "Required next fields"],
            rows,
            numeric_from=3,
            wrap=True,
            dense=True,
        )
