"""Valuation & Expectations: multi-multiple scorecard, momentum, scenarios."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store, tone
from src.modeling.assessment import Kpi, build_assessment
from src.modeling.scenarios import cases_from_thesis, implied_expectations, run_cases, sensitivity_grid
from src.reporting.charts import peer_valuation_scatter, valuation_chart
from src.reporting.periods import company_snapshot_context
from src.utils import fmt_money, fmt_multiple, fmt_ordinal, fmt_pct, fmt_signed_pct


def render(df: pd.DataFrame, company_id: str) -> None:
    from src.modeling.comps import comps_spread
    from src.modeling.multiples import (
        MULTIPLE_SPECS,
        multiple_history,
        multiple_momentum,
        multiples_summary,
        valuation_commentary,
    )
    from src.reporting import multiples_charts as mch

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    val = a.valuation
    financial = a.business_model == "financial"
    ui.header_band(row, DEMO_MODE)

    ui.section("Valuation Snapshot",
               f"{company_snapshot_context(store, row)} | current market values over LTM denominators")
    hc = a.history_context
    cards = [
        Kpi("mc", "Market Cap", fmt_money(row.get("market_cap"), currency), "Equity value"),
        Kpi("ev", "Enterprise Value", fmt_money(row.get("enterprise_value"), currency), "EV = mkt cap + net debt"),
        Kpi("mult", val["multiple_name"], val["pe"] if financial else val["ev_to_ebitda"],
            f"vs {val['pe_median'] if financial else val['ev_to_ebitda_median']} peer median",
            row.get(("pe_ttm" if financial else "ev_to_ebitda_ttm") + "_signal", "n/a"),
            delta=(f"{val['premium_label']} vs peers" if val.get("premium") is not None else None),
            delta_dir=("up" if (val.get("premium") or 0) > 0 else "down")),
        Kpi("hist", "vs Own History", fmt_ordinal(hc.get("percentile")) + " pctile" if hc.get("available") else "n/a",
            (f"z {hc.get('z_score'):+.1f} · median {fmt_multiple(hc.get('median'))}" if hc.get("available")
             else "history not populated"), "n/a"),
        Kpi("revs", "Estimate Momentum", a.revisions.get("direction", "n/a").title(),
            (f"NTM rev {fmt_signed_pct(a.revisions.get('revenue_30d'))} / 30d"
             if a.revisions.get("revenue_30d") is not None else "consensus not populated"),
            {"cutting": "red", "raising": "green"}.get(a.revisions.get("direction"), "n/a")),
    ]
    ui.kpi_grid(cards, columns=5)

    # --- Multi-multiple framework -------------------------------------------------
    spread = comps_spread(a.peers, store.estimates)
    summary = multiples_summary(row, spread, company_id, store.valuation_history)
    ui.section("Multi-Multiple Scorecard",
               "Which multiple matters for this business model, and what each one says")
    ui.multiple_scorecard(summary)
    m1, m2 = st.columns([1.05, 1.0], gap="medium")
    with m1:
        ui.business_model_map(summary, a.business_model)
    with m2:
        hist_metrics = [m for m, s in MULTIPLE_SPECS.items() if s["hist_col"]]
        peer_ids = list(a.peers["company_id"])
        momentum = {m: multiple_momentum(store.valuation_history, company_id, peer_ids,
                                         MULTIPLE_SPECS[m]["hist_col"]) for m in hist_metrics}
        notes = valuation_commentary(summary, momentum, row)
        if notes:
            ui.bullet_list("Valuation Read-Out", notes, "q")

    ui.section("Historical Multiples", "Company vs peer median | is the multiple high vs its own range?")
    label_by_metric = {m: MULTIPLE_SPECS[m]["label"] for m in hist_metrics}
    pick_hist = st.radio("Multiple", [label_by_metric[m] for m in hist_metrics],
                         horizontal=True, label_visibility="collapsed", key="hist_multiple")
    metric_pick = next(m for m in hist_metrics if label_by_metric[m] == pick_hist)
    hist = multiple_history(store.valuation_history, company_id, peer_ids,
                            MULTIPLE_SPECS[metric_pick]["hist_col"])
    st.plotly_chart(mch.multiple_history_chart(hist, pick_hist),
                    use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Multiple Momentum", "Re-rating, de-rating, or moving with the sector?")
    # Approximate price decomposition through the primary multiple lens.
    primary_hist = next((m["metric"] for m in summary
                         if m["role"] == "primary" and MULTIPLE_SPECS[m["metric"]]["hist_col"]
                         and m["interpretation"] != "not meaningful"), None)
    decomp = mch.rerating_decomposition(store.valuation_history, company_id,
                                        MULTIPLE_SPECS[primary_hist]["hist_col"]) \
        if primary_hist else {"available": False}
    h1, h2 = st.columns([1.0, 1.15], gap="medium")
    with h1:
        st.plotly_chart(mch.momentum_heatmap(momentum), use_container_width=True, config=PLOTLY_CONFIG)
    with h2:
        if decomp.get("available"):
            st.plotly_chart(mch.rerating_bridge_chart(decomp, MULTIPLE_SPECS[primary_hist]["label"]),
                            use_container_width=True, config=PLOTLY_CONFIG)

    by_metric = {m["metric"]: m for m in summary}
    _short = {"re-rating - company-specific": "re-rating (company-specific)",
              "de-rating - company-specific": "de-rating (company-specific)",
              "re-rating - sector-driven": "re-rating (sector-driven)",
              "de-rating - sector-driven": "de-rating (sector-driven)",
              "insufficient history": "short history"}
    mrows = []
    def fmt_change(value):
        return f"{value:+.0%}" if value is not None else "n/a"

    for metric in hist_metrics:
        mom = momentum[metric]
        if not mom.get("available"):
            continue
        verdict = mom.get("verdict") or "n/a"
        sm = by_metric.get(metric, {})
        mrows.append([
            MULTIPLE_SPECS[metric]["label"],
            f"{mom['current']:.1f}x",
            fmt_change(mom["chg"].get(3)), fmt_change(mom["chg"].get(6)), fmt_change(mom["chg"].get(12)),
            f"P{mom['percentile'] * 100:.0f}" if mom.get("percentile") is not None else "n/a",
            fmt_change(sm.get("premium")),
            _short.get(verdict, verdict),
        ])
    if mrows:
        ui.html_table(["Multiple", "Current", "3M", "6M", "12M", "Own pctile",
                       "vs peers", "Read"], mrows, numeric_from=1)
        ui.footnote("Monthly closes from the valuation-history export (its LTM multiples can "
                    "differ slightly from the dataset's LTM computation). Own pctile = current vs "
                    "own history; 'vs peers' = premium/discount to the adjusted peer median today; "
                    "Read compares the company's 12m multiple move with the peer median's move.")
    else:
        ui.footnote("Momentum requires populated valuation history.")

    ui.section("Valuation in Context")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(valuation_chart(df, None, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(peer_valuation_scatter(df, None, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    # Scenario engine.
    thesis_scen = a.thesis.scenarios if a.thesis else None
    results = run_cases(row, thesis_scen)
    ui.section("Public-Market Scenario Returns",
               "Exit value = exit-year profit x exit multiple; annualized equity-value return")
    srows = []
    for res in results:
        srows.append([
            res.case.name.title(),
            fmt_signed_pct(res.case.revenue_cagr),
            fmt_pct(res.case.exit_margin),
            f"{res.case.exit_multiple:g}x",
            f"{res.moic:.2f}x" if res.valid else "n/a",
            tone(f"{res.irr:+.1%}", res.irr >= 0) if res.valid else "n/a",
            res.case.source,
        ])
    ui.html_table(["Case", "Rev CAGR", "Exit Margin", "Exit Multiple", "Value / Current",
                   f"Annualized Return ({results[0].case.horizon_years}y)", "Source"], srows)

    base_case = cases_from_thesis(row, thesis_scen)[1]
    grid = sensitivity_grid(row, base_case)
    grid_rows = [[idx] + [("n/a" if pd.isna(v) else tone(f"{v:+.0%}", v >= 0)) for v in grid.loc[idx]]
                 for idx in grid.index]
    g1, g2 = st.columns([1.15, 1.0], gap="medium")
    with g1:
        ui.section("Annualized Return Sensitivity", "Revenue CAGR (rows) x exit multiple (columns), base-case margin held")
        ui.html_table(["Rev CAGR \\ Exit"] + list(grid.columns), grid_rows)
    with g2:
        fair_mult = a.peer_median.get("pe_ttm") if financial else a.peer_median.get("ev_to_ebitda_ttm")
        ie = implied_expectations(row, fair_mult)
        ui.section("What Is Priced In", f"Exit at peer-median {ie['multiple_name']}")
        if ie["available"]:
            items = [
                f"To earn {r['return']:.0%} a year, {ie['metric']} must compound at {r['implied_profit_cagr']:+.1%} for {ie['horizon_years']} years."
                for r in ie["required"]
            ]
            ui.bullet_list("Implied Expectations", items, "q")
        else:
            ui.footnote("Insufficient data (needs positive current profit, value, and a peer-median multiple).")
        st.write("")
        ui.memo("Valuation Commentary", val.get("commentary", ""))

    ui.footnote("Public-market scenario model: today's net debt is held constant and interim FCF/dividends "
                "are ignored. This is an implied equity-value CAGR, not a sponsor LBO IRR. Financial "
                "institutions run on net income x P/E instead of EBITDA x EV/EBITDA.")
