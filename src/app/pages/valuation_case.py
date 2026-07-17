"""Valuation Case: DCF, WACC build, bridges, sensitivities, export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store
from src.modeling.assessment import Kpi, build_assessment
from src.reporting.periods import company_snapshot_context
from src.utils import fmt_money


def render(df: pd.DataFrame, company_id: str) -> None:

    from src.branding import PALETTE
    from src.modeling.valuation_case import (
        CaseNotApplicableError,
        build_valuation_case,
        case_warnings,
    )
    from src.reporting import valuation_charts as vch
    from src.reporting.valuation_case import generate_valuation_case

    store = get_store(DEMO_MODE)
    a_head = build_assessment(df, company_id, store=store)
    ui.header_band(a_head.row, DEMO_MODE)

    # --- Applicability gate: never crash, degrade gracefully ------------------
    try:
        case = build_valuation_case(df, company_id, store=store)
    except CaseNotApplicableError as exc:
        st.markdown(
            f"""
            <div class="pe-verdict">
              <div class="pe-verdict-flag" style="background:{PALETTE['muted_2']}"></div>
              <div class="pe-verdict-body">
                <div class="pe-verdict-kicker">Valuation Case</div>
                <div class="pe-verdict-label" style="color:{PALETTE['slate']}">Not applicable - {exc.reason}</div>
                <div class="pe-verdict-rationale">{exc.detail}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # --- Financials-specific valuation (banks / lenders / platforms) --------
        a_gate = build_assessment(df, company_id, store=store)
        if str(a_gate.business_model) == "financial":
            from src.modeling.financials_valuation import build_financials_valuation
            from src.modeling.valuation_assumptions import load_wacc_params
            from src.modeling.wacc import build_wacc

            params = load_wacc_params(str(a_gate.row.get("currency", "USD")))
            w = build_wacc(a_gate.row, params, peers=a_gate.peers)
            fv = build_financials_valuation(a_gate.row, cost_of_equity=w.cost_of_equity)

            ui.section("Financials Valuation", "The framework banks and lenders are actually valued on")
            if fv.book_value is not None:
                roe_tone = ("green" if (fv.roe or 0) > w.cost_of_equity
                            else ("red" if fv.roe is not None else "n/a"))
                ui.kpi_grid([
                    Kpi("pe", "P/E (LTM)", f"{fv.pe:.1f}x" if fv.pe else "n/m",
                        "negative earnings" if fv.pe is None else "", "n/a"),
                    Kpi("pb", fv.pb_label, f"{fv.pb:.2f}x" if fv.pb else "n/a",
                        f"book source: {fv.book_source}", "n/a"),
                    Kpi("roe", "ROE vs COE",
                        f"{fv.roe:.1%} vs {w.cost_of_equity:.1%}" if fv.roe is not None else "n/a",
                        "value created only when ROE > COE", roe_tone),
                    Kpi("jpb", "Justified P/B",
                        f"{fv.justified_pb:.2f}x" if fv.justified_pb else "n/a",
                        f"(ROE - g) / (COE - g), g = {fv.growth:.1%}", "n/a"),
                    Kpi("erv", "Excess-Return Value",
                        f"{fv.excess_return_value:,.0f}" if fv.excess_return_value else "n/a",
                        (f"{fv.excess_return_upside:+.0%} vs market cap"
                         if fv.excess_return_upside is not None else "residual income model"),
                        ("green" if (fv.excess_return_upside or 0) > 0.15
                         else ("red" if (fv.excess_return_upside or 0) < -0.15 else "yellow"))
                        if fv.excess_return_upside is not None else "n/a"),
                ], columns=5)
                if fv.pb is not None and fv.justified_pb is not None:
                    verdict = "trades BELOW" if fv.pb < fv.justified_pb else "trades ABOVE"
                    ui.memo("Reading", f"At {fv.pb:.2f}x {fv.pb_label} vs a justified "
                            f"{fv.justified_pb:.2f}x, the market says this franchise {verdict} the "
                            f"multiple its ROE/COE spread supports. The excess-return model "
                            f"(book value + PV of returns above the cost of equity) is the "
                            f"cross-check - both collapse to book value when ROE = COE.")
            for wmsg in fv.warnings:
                ui.footnote(wmsg)
            ui.footnote("Limitations: LTM ROE (not normalized through the credit cycle), "
                        "growth is an assumption, and dividend-discount needs payout data "
                        "(dividends_paid exported but sparse). This is calibration, not a rating.")
        else:
            ui.section("What you can use instead")
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                ui.bullet_list("Available now", [
                    "Valuation & Expectations page: P/E vs peers and vs own history, revision momentum.",
                    "Peer Benchmarking: growth / profitability / multiple quartiles on the true comp set.",
                    "Company Situation: qualitative thesis case and journal.",
                ], "q")
            with c2:
                ui.bullet_list("Missing input", [
                    exc.detail,
                ], "con")
        return

    a = case.assessment
    row = a.row
    currency = row.get("currency", "USD")
    base = case.base
    ui.footnote(company_snapshot_context(store, row)
                + " | Current valuation uses LTM denominators; forecast years are forward estimates.")

    # --- Status card (prominent, its own block) ---------------------------------
    status_key, status_label = vch.assumptions_status(case)
    badge_color = {"auto": PALETTE["red"], "illustrative": PALETTE["amber"],
                   "draft": PALETTE["amber"], "final": PALETTE["green"]}.get(status_key, PALETTE["muted_2"])
    if status_key != "final":
        from src.modeling.valuation_assumptions import assumptions_filename
        target_file = assumptions_filename(company_id)
        folder_name = "data/sample/assumptions" if DEMO_MODE else "data_private/assumptions"
        detail = {
            "auto": (f"Every driver was derived mechanically from LTM data - no analyst file exists. "
                     f"Create <code>{folder_name}/{target_file}</code> from the template to set a real view."),
            "illustrative": "The analyst assumptions behind this case are labeled placeholders pending diligence.",
            "draft": "Analyst assumptions are in draft; numbers are directional.",
        }.get(status_key, "")
        st.markdown(
            f"""
            <div class="pe-memo" style="border-left-color:{badge_color};margin-bottom:10px">
              <h4 style="color:{badge_color}">{status_label}</h4>
              <p style="font-family:var(--font-sans);font-size:12.5px">{detail}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Recommendation banner ----------------------------------------------------
    rec_color = {"BUY": PALETTE["green"], "SELL": PALETTE["red"], "HOLD": PALETTE["gold"],
                 "INDICATIVE": PALETTE["muted_2"]}.get(case.recommendation.stance, PALETTE["muted_2"])
    target_txt = f" - target {base.target_price:,.2f} vs {base.current_price:,.2f}" if base.target_price else ""
    recommendation_label = ("Indicative calibration" if case.recommendation.stance == "INDICATIVE"
                            else case.recommendation.stance)
    st.markdown(
        f"""
        <div class="pe-verdict">
          <div class="pe-verdict-flag" style="background:{rec_color}"></div>
          <div class="pe-verdict-body">
            <div class="pe-verdict-kicker">DCF {'Calibration' if status_key == 'auto' else 'Recommendation'} | WACC {case.wacc.wacc:.1%} | Exit {case.exit_multiple:.1f}x ({case.exit_multiple_source})</div>
            <div class="pe-verdict-label" style="color:{rec_color}">{recommendation_label}{target_txt}</div>
            <div class="pe-verdict-rationale">{case.recommendation.headline} {case.recommendation.reconciliation}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Model-quality warnings ------------------------------------------------------
    warnings = case_warnings(case)
    tv_note = vch.terminal_value_divergence(case)
    if tv_note:
        warnings.append({"severity": "medium", "text": tv_note})
    if a.peer_warning:
        warnings.append({"severity": "high", "text": a.peer_warning})
    if not a.peer_reviewed:
        if a.peer_source == "capiq_comp_set":
            warnings.append({"severity": "low",
                             "text": "Comp set is S&P Capital IQ's official peer list (not yet analyst-reviewed) - "
                                     "approve it on the Peer Benchmarking page to sign off."})
        elif a.peer_source == "fallback":
            warnings.append({"severity": "low",
                             "text": "Comp set is the CapIQ-attribute scored set (not yet analyst-reviewed) - "
                                     "approve or edit it on the Peer Benchmarking page."})
        else:
            warnings.append({"severity": "medium",
                             "text": f"Comp set is the {a.peer_source.replace('_', ' ')} (not analyst-reviewed) - "
                                     f"approve a peer set on the Peer Benchmarking page to firm up the exit multiple."})
    if warnings:
        flags = [{"severity": w["severity"].title(), "area": "Model quality",
                  "observation": w["text"], "management_question": ""} for w in warnings]
        ui.section("Model-Quality Warnings", "Read these before trusting the target")
        ui.flag_list(flags)

    # --- Row 1: scenario targets | sensitivity heatmap --------------------------------
    ui.section("Valuation Range", "Where the DCF, comps, and history place the share price")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.scenario_target_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.sensitivity_heatmap(case), use_container_width=True, config=PLOTLY_CONFIG)

    c3, c4 = st.columns(2, gap="medium")
    with c3:
        st.plotly_chart(vch.tornado_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c4:
        st.plotly_chart(vch.implied_growth_heatmap(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 2: football field (full width) ---------------------------------------------
    _vh = store.valuation_history
    _own_hist = _vh[_vh["company_id"] == company_id] if (_vh is not None and not _vh.empty) else None
    st.plotly_chart(vch.football_field_chart(case, price_history=_own_hist),
                    use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 3: forecast | FCF bridge ----------------------------------------------------
    ui.section("From Assumptions to Cash Flow")
    pick = st.radio("Scenario", ["base", "bear", "bull"], horizontal=True, label_visibility="collapsed")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.forecast_chart(case, pick), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.fcf_bridge_chart(case, pick), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 4: equity bridge + current EV bridge ------------------------------------------
    from src.modeling.capital_structure import ev_bridge as _ev_bridge

    ui.section("Valuation Mechanics")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.equity_bridge_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        bridge = _ev_bridge(row)
        st.plotly_chart(vch.current_ev_bridge_chart(bridge), use_container_width=True, config=PLOTLY_CONFIG)
        if bridge.get("mismatch"):
            ui.footnote(f"Calculated EV vs reported CapIQ TEV: {bridge['gap']:+.0%} gap - "
                        f"leases/pensions/share-count detail not fully exported.")

    # --- Row 5: WACC | terminal value ------------------------------------------------------
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.wacc_build_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.terminal_value_chart(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 6: PE lens - LBO returns -------------------------------------------------------
    from src.modeling.lbo import lbo_from_case

    ui.section("Sponsor Feasibility - LBO Returns",
               "Levered IRR/MOIC on the same operating forecast | debt sized on EBITDA, not percent of EV")
    row_lbo = case.assessment.row
    own_mult = row_lbo.get("ev_to_ebitda_ttm")
    default_entry = float(own_mult) if pd.notna(own_mult) and own_mult > 0 else float(case.exit_multiple)
    input_max = max(40.0, round(default_entry + 10.0, 0), round(float(case.exit_multiple) + 10.0, 0))
    kd_default = float(case.wacc.cost_of_debt_pretax or 0.08)
    lc1, lc2, lc3, lc4 = st.columns(4)
    with lc1:
        entry_m = st.number_input("Entry EV/EBITDA (x)", min_value=2.0, max_value=input_max,
                                  value=round(default_entry, 1), step=0.5)
    with lc2:
        exit_m = st.number_input("Exit EV/EBITDA (x)", min_value=2.0, max_value=input_max,
                                 value=round(float(case.exit_multiple), 1), step=0.5)
    with lc3:
        entry_leverage = st.slider("Entry debt / EBITDA (x)", 0.0, 6.0, 3.0, 0.25)
    with lc4:
        kd_in = st.number_input("Pre-tax cost of debt (%)", min_value=1.0, max_value=25.0,
                                value=round(kd_default * 100, 1), step=0.5) / 100.0

    lbo = lbo_from_case(case, entry_multiple=entry_m, exit_multiple=exit_m,
                        entry_leverage=entry_leverage, cost_of_debt=kd_in)
    if lbo.valid:
        entry_leverage = lbo.entry_debt / lbo.entry_ebitda if lbo.entry_ebitda > 0 else None
        if entry_m > 30.0:
            st.warning(f"Entry valuation is {entry_m:.1f}x EBITDA. This is outside a conventional "
                       "sponsor underwriting range; the return case should be read as a feasibility "
                       "screen, not as an executable take-private proposal.")
        if entry_leverage is not None and entry_leverage > 4.0:
            st.warning(f"Entry leverage is {entry_leverage:.1f}x EBITDA, above the dashboard's "
                       "illustrative 4.0x senior-capacity reference. Treat the return case as "
                       "unfinanceable until debt terms are underwritten.")
        moic_tone = "green" if (lbo.moic or 0) >= 2.0 else ("yellow" if (lbo.moic or 0) >= 1.5 else "red")
        exit_lev = (lbo.exit_debt / lbo.exit_ebitda) if lbo.exit_ebitda > 0 else None
        ui.kpi_grid([
            Kpi("chk", "Equity Check", f"{lbo.equity_check:,.0f}",
                f"{(1 - lbo.debt_pct):.0%} of EV + fees", "n/a"),
            Kpi("moic", "MOIC", f"{lbo.moic:.2f}x" if lbo.moic else "n/a",
                f"{lbo.horizon}-year hold", moic_tone),
            Kpi("irr", "Sponsor IRR", f"{lbo.irr:.1%}" if lbo.irr is not None else "n/a",
                "no interim distributions", moic_tone),
            Kpi("lev", "Entry -> Exit Leverage",
                f"{(lbo.entry_debt / lbo.entry_ebitda):.1f}x -> {exit_lev:.1f}x" if exit_lev is not None else "n/a",
                "debt / EBITDA", "n/a"),
            Kpi("xeq", "Exit Equity", f"{lbo.exit_equity:,.0f}",
                f"EV {lbo.exit_ev:,.0f} - debt {lbo.exit_debt:,.0f} + cash {lbo.excess_cash:,.0f}", "n/a"),
        ], columns=5)
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(vch.value_creation_bridge_chart(lbo), use_container_width=True, config=PLOTLY_CONFIG)
        with c2:
            st.plotly_chart(vch.debt_paydown_chart(lbo), use_container_width=True, config=PLOTLY_CONFIG)
        for note in lbo.notes:
            ui.footnote(note)
        ui.footnote("Simple-LBO conventions: entry debt sized as debt / LTM EBITDA, 100% cash sweep, "
                    "after-tax cash interest, no interim "
                    "dividends, excess cash retained, fees 2% of EV. Base-scenario forecast; flex the assumptions "
                    "file for segment-driven builds.")
    else:
        st.info(lbo.notes[0] if lbo.notes else "LBO not applicable for this name.")
        if tv_note:
            ui.footnote(tv_note)

    # --- Row 6: peer quartiles (full width) --------------------------------------------------
    ui.section("Market Context")
    st.plotly_chart(vch.peer_quartile_panels(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 7: revisions | working capital ---------------------------------------------------
    rev_fig = vch.revision_momentum_chart(case)
    wc_fig = vch.working_capital_chart(df, case)
    if rev_fig is not None or wc_fig is not None:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            if rev_fig is not None:
                st.plotly_chart(rev_fig, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                ui.footnote("Estimate revisions not populated for this name.")
        with c2:
            if wc_fig is not None:
                st.plotly_chart(wc_fig, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                ui.footnote("Working-capital days not populated for this name.")

    # --- Provenance --------------------------------------------------------------------------
    ui.section("Assumptions Provenance", "Every input classified - no black box")
    prov = vch.assumptions_provenance(case)
    pill = {"analyst": ("Analyst", "yellow"), "anchored": ("Anchored LTM", "green"), "default": ("Default", "red")}
    rows = [[r["item"], r["value"], ui.cell_pill(*pill.get(r["source"], (r["source"], "na")))]
            for _, r in prov.iterrows()]
    ui.html_table(["Input", "Value", "Source"], rows, numeric_from=99)
    ui.footnote("Analyst = set in the assumptions YAML. Anchored = derived from the company's own LTM data "
                "or the peer group. Default = generic fallback pending better data - treat with caution."
                + (f" File: <code>{Path(str(case.assumptions.path)).name}</code>" if case.assumptions.from_file else ""))

    # --- Detail tables (kept, collapsed) --------------------------------------------------------
    with st.expander("Forecast, WACC, and terminal value detail tables"):
        res = case.scenarios[pick]
        f = res.forecast
        headers = ["Line"] + [f"Y{int(y)}" for y in f["year"]]
        rows = [
            ["Revenue"] + [fmt_money(v, currency) for v in f["revenue"]],
            ["  growth"] + [f"{v:+.1%}" for v in f["revenue_growth"]],
            ["EBITDA"] + [fmt_money(v, currency) for v in f["ebitda"]],
            ["  margin"] + [f"{v:.1%}" for v in f["ebitda_margin"]],
            ["NOPAT"] + [fmt_money(v, currency) for v in f["nopat"]],
            ["Capex"] + [fmt_money(v, currency) for v in f["capex"]],
            ["Change in NWC"] + [fmt_money(v, currency) for v in f["delta_nwc"]],
            ["UFCF"] + [fmt_money(v, currency) for v in f["ufcf"]],
        ]
        ui.html_table(headers, rows)
        w = case.wacc
        if w.notes:
            ui.footnote(" | ".join(w.notes))

    # --- Export -----------------------------------------------------------------------------------
    ui.section("Export", "Generated only on request so opening the page stays fast and silent")
    export_state_key = f"valuation_case_export::{DEMO_MODE}::{company_id}"
    if st.button("Generate / Refresh Valuation Case (HTML)",
                 key=f"generate_valuation_case::{DEMO_MODE}::{company_id}"):
        with st.spinner("Rendering valuation case and chart images..."):
            generated_path = generate_valuation_case(demo=DEMO_MODE, company_id=company_id)
        if generated_path is not None:
            st.session_state[export_state_key] = str(generated_path)
            st.success("Valuation case ready for download.")
        else:
            st.error("The valuation case could not be generated for this company.")

    saved_path = st.session_state.get(export_state_key)
    if saved_path and Path(saved_path).exists():
        path = Path(saved_path)
        st.download_button("Download Valuation Case (HTML)", data=path.read_bytes(),
                           file_name=path.name, mime="text/html", use_container_width=False)
        ui.footnote(f"Written to <code>{path.parent.name}/</code>"
                    + (" - private outputs never enter version control." if not DEMO_MODE else "."))
    else:
        ui.footnote("The interactive dashboard is ready. Generate the standalone HTML only when you need it.")
