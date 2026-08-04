"""Streamlit presentation for business-model-aware operating drivers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.app import components as ui
from src.app.context import PLOTLY_CONFIG
from src.branding import FONT_SANS, PALETTE
from src.modeling.assessment import Kpi
from src.utils import fmt_money, fmt_pct


def _style(fig: go.Figure, title: str, subtitle: str, height: int = 350) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>", x=0, xanchor="left",
            subtitle=dict(text=subtitle, font=dict(size=11, color=PALETTE["muted"])),
            font=dict(size=17, family=FONT_SANS, color=PALETTE["ink"]),
        ),
        height=height,
        margin=dict(l=24, r=20, t=88, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, color=PALETTE["slate"], size=11),
        legend=dict(orientation="h", y=1.01, x=1, xanchor="right"),
        hoverlabel=dict(bgcolor=PALETTE["panel"], bordercolor=PALETTE["line"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=PALETTE["line"])
    fig.update_yaxes(showgrid=True, gridcolor=PALETTE["line_soft"], zeroline=False)
    return fig


def _channel_history(build, currency: str) -> go.Figure:
    metrics = {
        "revenue_store_channel": "Stores",
        "revenue_ecommerce": "E-commerce",
        "revenue_other_channels": "Other channels",
    }
    history = build.historical[build.historical["metric_id"].isin(metrics)].copy()
    if "period_type" in history.columns:
        history = history[history["period_type"].astype(str).str.lower() == "annual"]
    history["channel"] = history["metric_id"].map(metrics)
    history["fiscal_period"] = history["fiscal_period"].fillna(
        history["period"].dt.year.astype(str)
    )
    colors = {
        "Stores": PALETTE["teal"],
        "E-commerce": PALETTE["navy"],
        "Other channels": PALETTE["navy_3"],
    }
    fig = go.Figure()
    for name in metrics.values():
        rows = history[history["channel"] == name]
        fig.add_bar(
            name=name,
            x=rows["fiscal_period"],
            y=rows["value"],
            marker_color=colors[name],
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:,.1f}} {currency}m<extra></extra>",
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title=f"{currency}m")
    return _style(
        fig,
        "Reported Revenue by Channel",
        "Issuer-defined annual channels | filing definitions retained",
    )


def _footprint_history(build) -> go.Figure:
    history = build.historical.copy()
    stores = history[history["metric_id"] == "store_count_total"].sort_values("period")
    productivity = history[history["metric_id"] == "sales_per_square_foot"].sort_values("period")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            name="Stores",
            x=stores["period"], y=stores["value"],
            mode="lines+markers", line=dict(color=PALETTE["teal"], width=3),
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} stores<extra></extra>",
        ),
        secondary_y=False,
    )
    if not productivity.empty:
        fig.add_trace(
            go.Scatter(
                name="Sales / sq. ft.",
                x=productivity["period"], y=productivity["value"],
                mode="lines+markers", line=dict(color=PALETTE["navy_3"], width=2, dash="dot"),
                hovertemplate="%{x|%Y}<br>$%{y:,.0f}<extra></extra>",
            ),
            secondary_y=True,
        )
    fig.update_yaxes(title="Store count", secondary_y=False)
    fig.update_yaxes(title="Sales / sq. ft.", secondary_y=True, showgrid=False)
    return _style(
        fig,
        "Store Footprint and Productivity",
        "Point-in-time stores; productivity shown when disclosed",
    )


def _period_labels(projected: pd.DataFrame, explicit_years: int) -> list[str]:
    return [
        f"Y{int(year)}" if int(year) <= explicit_years else f"T{int(year) - explicit_years}"
        for year in projected["year"]
    ]


def _projection_chart(
    build, scenario: str, currency: str, explicit_years: int
) -> go.Figure:
    projected = build.projection[build.projection["scenario"] == scenario].copy()
    labels = _period_labels(projected, explicit_years)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for column, label, color in (
        ("stores_revenue", "Stores", PALETTE["teal"]),
        ("e_commerce_revenue", "E-commerce", PALETTE["navy"]),
        ("other_channels_revenue", "Other channels", PALETTE["navy_3"]),
    ):
        if column in projected.columns:
            fig.add_trace(
                go.Bar(
                    name=label, x=labels, y=projected[column],
                    marker_color=color,
                    hovertemplate=f"Y%{{x}}<br>{label}: %{{y:,.1f}} {currency}m<extra></extra>",
                ),
                secondary_y=False,
            )
    fig.add_trace(
        go.Scatter(
            name="Revenue growth",
            x=labels, y=projected["revenue_growth"],
            mode="lines+markers+text",
            text=[f"{value:+.1%}" for value in projected["revenue_growth"]],
            textposition="top center",
            line=dict(color=PALETTE["slate"], width=2.5),
            hovertemplate="Y%{x}<br>%{y:+.1%}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title=f"Revenue ({currency}m)", secondary_y=False)
    fig.update_yaxes(title="Growth", tickformat=".0%", secondary_y=True, showgrid=False)
    return _style(
        fig,
        f"{scenario.title()} Revenue Build",
        "Y = detailed operating build | T = automatic transition to stable growth",
        height=390,
    )


def _driver_rows(
    build, scenario: str, currency: str, explicit_years: int
) -> list[list[str]]:
    projected = build.projection[build.projection["scenario"] == scenario]
    labels = _period_labels(projected, explicit_years)
    rows: list[list[str]] = []
    for label, (_, row) in zip(labels, projected.iterrows()):
        rows.append([
            label,
            f"{row.get('ending_stores', float('nan')):,.0f}",
            f"{row.get('net_store_adds', float('nan')):+,.0f}",
            fmt_pct(row.get("stores_rpu_growth")),
            fmt_money(row.get("stores_revenue"), currency),
            fmt_money(row.get("e_commerce_revenue"), currency),
            fmt_money(row.get("other_channels_revenue"), currency),
            fmt_money(row.get("revenue"), currency),
            fmt_pct(row.get("revenue_growth")),
        ])
    return rows


def _metric_name(metric: str) -> str:
    return str(metric).replace("_", " ").title()


def render_operating_driver_build(case, currency: str) -> None:
    build = getattr(case.assumptions, "operating_driver_build", None)
    if build is None:
        return

    ui.section(
        "Operating Driver Build",
        "Business-model equation -> sourced KPIs -> revenue forecast -> DCF",
    )
    rec = build.reconciliation
    matched = int((rec["status"] == "matched").sum()) if not rec.empty else 0
    mismatched = int((rec["status"] == "mismatch").sum()) if not rec.empty else 0
    source_types = set(
        build.sources.get("source_type", pd.Series(dtype=str)).astype(str).str.lower()
    )
    if matched or mismatched:
        reconciliation_text = f"{matched} matched | {mismatched} mismatch"
        reconciliation_note = "1% tolerance where Capital IQ and filing overlap"
        reconciliation_tone = "red" if mismatched else "green"
    elif any("filing" in source for source in source_types):
        reconciliation_text = "Filing anchor | CapIQ refresh-ready"
        reconciliation_note = "Independent Excel check activates after mnemonic refresh"
        reconciliation_tone = "yellow"
    else:
        reconciliation_text = "Single-source coverage"
        reconciliation_note = "A second source is required for an independent check"
        reconciliation_tone = "yellow"
    ui.kpi_grid([
        Kpi("tier", "Model Depth", build.tier_label, build.status, "green" if build.tier == 3 else "yellow"),
        Kpi("profile", "Revenue Architecture", build.profile.label, build.profile.model_id, "n/a"),
        Kpi("coverage", "Primary KPI Coverage", f"{build.coverage_pct:.0%}",
            f"{len(build.available_metrics)} operating metrics loaded",
            "green" if build.coverage_pct == 1 else "yellow"),
        Kpi("tie", "CapIQ / Filing Check", reconciliation_text,
            reconciliation_note, reconciliation_tone),
    ], columns=4)
    ui.memo("Revenue equation", build.profile.equation)

    if build.tier == 3 and not build.projection.empty:
        explicit_years = int(case.assumptions.explicit_horizon_years)
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(_channel_history(build, currency), use_container_width=True, config=PLOTLY_CONFIG)
        with c2:
            st.plotly_chart(_footprint_history(build), use_container_width=True, config=PLOTLY_CONFIG)

        scenario = st.segmented_control(
            "Operating scenario",
            options=["base", "bear", "bull"],
            default="base",
            key=f"operating_driver_scenario_{case.company_id}",
            label_visibility="collapsed",
        ) or "base"
        st.plotly_chart(
            _projection_chart(build, scenario, currency, explicit_years),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        ui.html_table(
            [
                "Year", "Ending stores", "Net adds", "Store productivity",
                "Store revenue", "E-commerce", "Other", "Total revenue", "YoY",
            ],
            _driver_rows(build, scenario, currency, explicit_years),
            numeric_from=1,
            dense=True,
        )
        for note in build.notes:
            ui.footnote(note)

        with st.expander("Operating KPI sources and reconciliation"):
            source_rows = []
            if not build.sources.empty:
                for _, row in build.sources.iterrows():
                    source_rows.append([
                        str(row.get("source_type", "n/a")),
                        str(row.get("source_name", "n/a")),
                        str(row.get("filing_form", "n/a")),
                        str(row.get("retrieved_at", "n/a"))[:10],
                        str(row.get("definition", "")),
                    ])
            ui.html_table(
                ["Source type", "Source", "Filing", "Retrieved", "Definition"],
                source_rows,
                numeric_from=99,
                wrap=True,
                dense=True,
            )
            if not rec.empty:
                rec_rows = []
                for _, row in rec.iterrows():
                    rec_rows.append([
                        _metric_name(row["metric_id"]),
                        str(row.get("scope", "")),
                        pd.Timestamp(row["period"]).strftime("%d %b %Y"),
                        "n/a" if pd.isna(row["capiq_value"]) else f"{row['capiq_value']:,.2f}",
                        "n/a" if pd.isna(row["filing_value"]) else f"{row['filing_value']:,.2f}",
                        str(row["status"]).title(),
                    ])
                ui.html_table(
                    ["Metric", "Scope", "Period", "Capital IQ", "Filing", "Check"],
                    rec_rows,
                    numeric_from=3,
                    dense=True,
                )
        return

    if build.tier == 2 and not build.segment_history.empty:
        segment_data = build.segment_history.sort_values("revenue_usd", ascending=True)
        fig = go.Figure(go.Bar(
            x=segment_data["revenue_usd"],
            y=segment_data["segment"],
            orientation="h",
            marker_color=PALETTE["teal"],
            text=[f"{value:,.0f}" for value in segment_data["revenue_usd"]],
            textposition="outside",
        ))
        st.plotly_chart(
            _style(fig, "Reported Segment Mix", "Capital IQ segment disclosure; USD-converted for mix analysis"),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )

    missing = [_metric_name(metric) for metric in build.missing_metrics]
    if missing:
        ui.bullet_list("Operating KPIs required for Tier 3", missing, "q")
    for note in build.notes:
        ui.footnote(note)
