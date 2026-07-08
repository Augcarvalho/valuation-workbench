"""Compare: 2-4 names side by side."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, get_store, verdict_pill
from src.modeling.assessment import build_assessment
from src.modeling.metrics import latest_rows
from src.utils import fmt_money, fmt_multiple, fmt_ordinal, fmt_pct, fmt_signed_pct


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    latest = latest_rows(df)
    labels = {
        f"{r.ticker.replace('.SA', '')} | {r.company_name}": r.company_id
        for r in latest.sort_values("ticker").itertuples()
    }
    default_label = next((k for k, v in labels.items() if v == company_id), list(labels.keys())[0])

    st.markdown(
        f"""
        <div class="pe-header">
          <div class="pe-header-top">
            <div>
              <div class="kicker">Investment Watchlist | Side-by-Side</div>
              <h1>Compare</h1>
            </div>
            <span class="pe-mode-pill {'pe-mode-demo' if DEMO_MODE else 'pe-mode-private'}">
              {'Public Demo Data' if DEMO_MODE else 'Capital IQ - Private'}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    picks = st.multiselect("Companies (2–4)", list(labels.keys()), default=[default_label], max_selections=4)
    if len(picks) < 2:
        ui.footnote("Pick at least two names to compare.")
        return

    assessments = [build_assessment(df, labels[p], store=store) for p in picks]

    def metric_row(label, getter, formatter=lambda v: v):
        return [label] + [formatter(getter(a)) for a in assessments]

    headers = ["Metric"] + [a.row["ticker"].replace(".SA", "") for a in assessments]
    rows = [
        metric_row("Verdict", lambda a: verdict_pill(a.verdict_key, a.verdict_label)),
        metric_row("Attention score", lambda a: f"{a.attention_score:.0f}"),
        metric_row("Peer group", lambda a: str(a.peer_group)[:28]),
        metric_row("Thesis stage", lambda a: a.thesis.stage_label if (a.thesis and a.thesis.exists) else "—"),
        metric_row("Revenue (TTM)", lambda a: fmt_money(a.row.get("revenue_ttm"), a.row.get("currency", "USD"))),
        metric_row("Revenue YoY", lambda a: fmt_signed_pct(a.row.get("revenue_yoy_growth"))),
        metric_row("Profitability (TTM)", lambda a: fmt_pct(a.row.get(
            "net_income_margin_ttm" if a.business_model == "financial" else "ebitda_margin_ttm"))),
        metric_row("FCF conversion", lambda a: fmt_pct(a.row.get("fcf_conversion_ttm"))),
        metric_row("ROIC / ROE", lambda a: fmt_pct(a.row.get("roe_ttm" if a.business_model == "financial" else "roic_ttm"))),
        metric_row("Net debt / EBITDA", lambda a: fmt_multiple(a.row.get("net_debt_to_ebitda_ttm"))),
        metric_row("Multiple", lambda a: f"{fmt_multiple(a.row.get('pe_ttm' if a.business_model == 'financial' else 'ev_to_ebitda_ttm'))} {a.valuation.get('multiple_name')}"),
        metric_row("vs peer median", lambda a: a.valuation.get("premium_label", "n/a")),
        metric_row("vs own history", lambda a: fmt_ordinal(a.history_context.get("percentile")) + " pctile"
                   if a.history_context.get("available") else "n/a"),
        metric_row("Estimate momentum", lambda a: a.revisions.get("direction", "n/a").title()),
        metric_row("Open flags", lambda a: str(sum(1 for f in a.red_flags if f.get("severity") in {"High", "Medium"}))),
        metric_row("As of", lambda a: ui.quarter_label(a.row["period"])),
    ]
    ui.section("Side-by-Side")
    ui.html_table(headers, rows, numeric_from=1)

    ui.section("Verdict Rationale")
    for a in assessments:
        ui.memo(a.row["ticker"].replace(".SA", ""), a.verdict_rationale)
