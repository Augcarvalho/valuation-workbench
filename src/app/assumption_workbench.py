"""Editable valuation assumptions with automatic defaults and private storage."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.modeling.assumption_overrides import (
    AssumptionValidationError,
    read_assumption_payload,
    reset_assumption_payload,
    save_assumption_payload,
)
from src.modeling.valuation_case import build_valuation_case


MANAGED_ROOT_KEYS = {
    "status", "horizon_years", "transition_years", "scenarios",
    "wacc", "terminal", "segments", "review_note",
}


def _pct_input(label: str, value: float, key: str, help_text: str = "") -> float:
    return st.number_input(
        label,
        min_value=-100.0,
        max_value=150.0,
        value=round(float(value) * 100.0, 2),
        step=0.25,
        format="%.2f",
        help=help_text or None,
        key=key,
    ) / 100.0


def _number_input(
    label: str,
    value: float,
    key: str,
    *,
    minimum: float = 0.0,
    maximum: float = 100.0,
    step: float = 0.1,
    help_text: str = "",
) -> float:
    return float(st.number_input(
        label,
        min_value=float(minimum),
        max_value=float(maximum),
        value=round(float(value), 3),
        step=float(step),
        format="%.3f",
        help=help_text or None,
        key=key,
    ))


def _endpoints(values: list[float], explicit_horizon: int) -> tuple[float, float]:
    end_index = min(max(explicit_horizon - 1, 0), len(values) - 1)
    return float(values[0]), float(values[end_index])


def _different(left: float, right: float, tolerance: float = 6e-4) -> bool:
    # Inputs are displayed at two decimal places for percentages and three for
    # days/multiples. Ignore display-rounding noise so an untouched automatic
    # case saves zero analyst overrides.
    return abs(float(left) - float(right)) > tolerance


def _is_auto(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() == "auto"
    )


def _raw_endpoint(raw_spec: Any, endpoint: str) -> Any:
    if isinstance(raw_spec, dict):
        return raw_spec.get(endpoint, "auto")
    if isinstance(raw_spec, list) and raw_spec:
        return raw_spec[0] if endpoint == "start" else raw_spec[-1]
    return raw_spec


def _path_editor_spec(
    start: float,
    end: float,
    current_start: float,
    current_end: float,
    raw_spec: Any,
) -> Any:
    start_changed = _different(start, current_start)
    end_changed = _different(end, current_end)
    raw_start = _raw_endpoint(raw_spec, "start")
    raw_end = _raw_endpoint(raw_spec, "end")

    if not start_changed and not end_changed:
        has_explicit = not _is_auto(raw_start) or not _is_auto(raw_end)
        return raw_spec if has_explicit else None

    start_value = round(float(start), 8) if start_changed else (
        round(float(raw_start), 8) if not _is_auto(raw_start) else "auto"
    )
    end_value = round(float(end), 8) if end_changed else (
        round(float(raw_end), 8) if not _is_auto(raw_end) else "auto"
    )
    return {"start": start_value, "end": end_value}


def _scalar_editor_override(value: float, current_value: float, raw_value: Any) -> float | None:
    if _different(value, current_value):
        return round(float(value), 8)
    if not _is_auto(raw_value):
        return round(float(raw_value), 8)
    return None


def _scenario_editor(
    name: str,
    current,
    automatic,
    horizon: int,
    auto_horizon: int,
    prefix: str,
    raw_scenario: dict[str, Any],
) -> dict:
    overrides: dict[str, Any] = {}

    current_growth = _endpoints(current.revenue_growth, horizon)
    auto_growth = _endpoints(automatic.revenue_growth, auto_horizon)
    current_margin = _endpoints(current.ebitda_margin, horizon)
    auto_margin = _endpoints(automatic.ebitda_margin, auto_horizon)
    current_da = _endpoints(current.d_and_a_pct, horizon)
    current_capex = _endpoints(current.capex_pct, horizon)

    st.caption(
        f"Automatic anchors: growth {auto_growth[0]:+.1%} to {auto_growth[1]:+.1%}; "
        f"margin {auto_margin[0]:.1%} to {auto_margin[1]:.1%}. "
        "Only values changed from these anchors are stored as analyst overrides."
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        growth_start = _pct_input(
            "Revenue growth - Year 1 (%)", current_growth[0],
            f"{prefix}_{name}_growth_start",
        )
    with c2:
        growth_end = _pct_input(
            "Revenue growth - final detailed year (%)", current_growth[1],
            f"{prefix}_{name}_growth_end",
        )
    with c3:
        margin_start = _pct_input(
            "EBITDA margin - Year 1 (%)", current_margin[0],
            f"{prefix}_{name}_margin_start",
        )
    with c4:
        margin_end = _pct_input(
            "EBITDA margin - final detailed year (%)", current_margin[1],
            f"{prefix}_{name}_margin_end",
        )

    growth_override = _path_editor_spec(
        growth_start, growth_end, *current_growth,
        raw_scenario.get("revenue_growth"),
    )
    margin_override = _path_editor_spec(
        margin_start, margin_end, *current_margin,
        raw_scenario.get("ebitda_margin"),
    )
    if growth_override is not None:
        overrides["revenue_growth"] = growth_override
    if margin_override is not None:
        overrides["ebitda_margin"] = margin_override

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        da_start = _pct_input(
            "D&A / revenue - Year 1 (%)", current_da[0],
            f"{prefix}_{name}_da_start",
        )
    with c2:
        da_end = _pct_input(
            "D&A / revenue - final year (%)", current_da[1],
            f"{prefix}_{name}_da_end",
        )
    with c3:
        capex_start = _pct_input(
            "Capex / revenue - Year 1 (%)", current_capex[0],
            f"{prefix}_{name}_capex_start",
        )
    with c4:
        capex_end = _pct_input(
            "Capex / revenue - final year (%)", current_capex[1],
            f"{prefix}_{name}_capex_end",
        )

    da_override = _path_editor_spec(
        da_start, da_end, *current_da,
        raw_scenario.get("d_and_a_pct_revenue"),
    )
    capex_override = _path_editor_spec(
        capex_start, capex_end, *current_capex,
        raw_scenario.get("capex_pct_revenue"),
    )
    if da_override is not None:
        overrides["d_and_a_pct_revenue"] = da_override
    if capex_override is not None:
        overrides["capex_pct_revenue"] = capex_override

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tax = _pct_input(
            "Normalized cash tax rate (%)", current.tax_rate,
            f"{prefix}_{name}_tax",
        )
    tax_override = _scalar_editor_override(
        tax, current.tax_rate, raw_scenario.get("tax_rate")
    )
    if tax_override is not None:
        overrides["tax_rate"] = tax_override

    if current.nwc_mode == "days":
        current_days = [float(values[0]) for values in (current.dso, current.dih, current.dpo)]
        labels = (("DSO", "dso"), ("Inventory days", "dih"), ("DPO", "dpo"))
        for column, (label, field), value in zip(
            (c2, c3, c4), labels, current_days
        ):
            with column:
                edited = _number_input(
                    label, value, f"{prefix}_{name}_{field}",
                    maximum=730.0, step=1.0,
                )
            override = _scalar_editor_override(
                edited, value, raw_scenario.get(field)
            )
            if override is not None:
                overrides[field] = override
    else:
        current_nwc = float(current.nwc_pct_revenue[0])
        with c2:
            nwc_pct = _pct_input(
                "Operating NWC / revenue (%)", current_nwc,
                f"{prefix}_{name}_nwc_pct",
            )
        nwc_override = _scalar_editor_override(
            nwc_pct, current_nwc, raw_scenario.get("nwc_pct_revenue")
        )
        if nwc_override is not None:
            overrides["nwc_pct_revenue"] = nwc_override

    return overrides


def render_assumption_workbench(
    df: pd.DataFrame,
    company_id: str,
    store,
    case,
    *,
    demo_mode: bool,
) -> None:
    """Render the editor and persist only analyst deviations from auto anchors."""
    flash_key = f"assumption_flash_{company_id}"
    if flash_key in st.session_state:
        st.success(st.session_state.pop(flash_key))

    assumptions_dir = getattr(store, "assumptions_dir", None)
    if assumptions_dir is None:
        st.info("No assumptions directory is configured for this data mode.")
        return

    current = case.assumptions
    if current.from_file:
        auto_store = replace(store, assumptions_dir=None)
        automatic_case = build_valuation_case(df, company_id, store=auto_store)
    else:
        automatic_case = case
    automatic = automatic_case.assumptions
    raw = read_assumption_payload(current.path)
    file_stamp = (
        Path(current.path).stat().st_mtime_ns
        if current.path is not None and Path(current.path).exists()
        else "automatic"
    )
    prefix = f"assumption_editor_{company_id.replace(':', '_')}_{file_stamp}"

    source_label = (
        f"Loaded from {Path(current.path).name}"
        if current.from_file
        else "No analyst file: fields below are pre-filled from the automatic model"
    )
    with st.expander(
        "Assumption Workbench | Edit valuation assumptions",
        expanded=not current.from_file,
    ):
        st.caption(
            source_label
            + ". Saving creates a private draft and recalculates every DCF, sensitivity, "
              "bridge and export from the same assumption set."
        )
        if demo_mode:
            st.info("The public demo is read-only. Switch to Capital IQ private mode to save assumptions.")

        with st.form(f"{prefix}_form", border=False):
            c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.0, 1.4])
            with c1:
                default_status = current.status if current.status != "auto" else "draft"
                status = st.selectbox(
                    "Review status",
                    ["draft", "final", "illustrative"],
                    index=["draft", "final", "illustrative"].index(default_status),
                    key=f"{prefix}_status",
                    help="Final means the analyst has reviewed the full assumption set.",
                )
            with c2:
                horizon = int(st.number_input(
                    "Detailed forecast years", min_value=3, max_value=15,
                    value=int(current.explicit_horizon_years), step=1,
                    key=f"{prefix}_horizon",
                ))
            with c3:
                transition_is_auto = current.transition_source != "analyst"
                transition_mode = st.selectbox(
                    "Stable-growth transition", ["Automatic", "Manual"],
                    index=0 if transition_is_auto else 1,
                    key=f"{prefix}_transition_mode",
                )
            with c4:
                transition_years = int(st.number_input(
                    "Transition years", min_value=0, max_value=10,
                    value=int(current.transition_years), step=1,
                    disabled=transition_mode == "Automatic",
                    key=f"{prefix}_transition_years",
                    help="Automatic limits the growth fade to approximately 200 bps per year.",
                ))

            if isinstance(raw.get("segments"), list):
                revenue_options = [
                    "Preserve custom segment build",
                    "Capital IQ segment mix",
                    "Top-down growth paths",
                ]
                revenue_index = 0
            else:
                revenue_options = ["Capital IQ segment mix", "Top-down growth paths"]
                revenue_index = 0 if current.segments else 1
            revenue_method = st.selectbox(
                "Revenue forecast method",
                revenue_options,
                index=revenue_index,
                key=f"{prefix}_revenue_method",
                help=("Capital IQ segments retain the reported mix and relative segment growth; "
                      "the scenario growth paths below control the company-level trajectory."),
            )

            tabs = st.tabs(["Base case", "Bear case", "Bull case"])
            scenario_overrides: dict[str, dict] = {}
            for tab, name in zip(tabs, ("base", "bear", "bull")):
                with tab:
                    overrides = _scenario_editor(
                        name,
                        current.scenarios[name],
                        automatic.scenarios[name],
                        current.explicit_horizon_years,
                        automatic.explicit_horizon_years,
                        prefix,
                        (raw.get("scenarios") or {}).get(name, {}),
                    )
                    if overrides:
                        scenario_overrides[name] = overrides

            st.markdown("##### Discount rate and terminal value")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                beta = _number_input(
                    "Beta", case.wacc.beta, f"{prefix}_beta",
                    minimum=0.1, maximum=5.0, step=0.05,
                    help_text=f"Automatic: {automatic_case.wacc.beta:.2f}",
                )
            with c2:
                cost_of_debt = _pct_input(
                    "Pre-tax cost of debt (%)", case.wacc.cost_of_debt_pretax,
                    f"{prefix}_cost_of_debt",
                    f"Automatic: {automatic_case.wacc.cost_of_debt_pretax:.1%}",
                )
            with c3:
                wacc = _pct_input(
                    "Current WACC (%)", case.wacc.wacc, f"{prefix}_wacc",
                    f"Automatic build: {automatic_case.wacc.wacc:.1%}",
                )
            with c4:
                terminal_wacc = _pct_input(
                    "Terminal WACC (%)", current.terminal_wacc,
                    f"{prefix}_terminal_wacc",
                    f"Automatic stable-state WACC: {automatic.terminal_wacc:.1%}",
                )

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                perpetual_growth = _pct_input(
                    "Perpetuity growth (%)", current.perpetuity_growth,
                    f"{prefix}_perpetuity_growth",
                    f"Automatic currency anchor: {automatic.perpetuity_growth:.1%}",
                )
            with c2:
                terminal_roic = _pct_input(
                    "Terminal ROIC (%)", current.terminal_roic,
                    f"{prefix}_terminal_roic",
                    f"Automatic stable-state ROIC: {automatic.terminal_roic:.1%}",
                )
            with c3:
                exit_multiple = _number_input(
                    "Exit EV / EBITDA (x)", case.exit_multiple,
                    f"{prefix}_exit_multiple",
                    minimum=0.5, maximum=100.0, step=0.25,
                    help_text=(f"Automatic Gordon-consistent multiple: "
                               f"{automatic_case.exit_multiple:.1f}x"),
                )
            with c4:
                review_note = st.text_area(
                    "Analyst rationale",
                    value=str(raw.get("review_note", "")),
                    placeholder="What changed, why, and which evidence supports it?",
                    height=86,
                    key=f"{prefix}_review_note",
                )

            preserved = {k: v for k, v in raw.items() if k not in MANAGED_ROOT_KEYS}
            payload: dict[str, Any] = {
                **preserved,
                "status": status,
                "horizon_years": horizon,
                "transition_years": "auto" if transition_mode == "Automatic" else transition_years,
            }
            if scenario_overrides:
                payload["scenarios"] = scenario_overrides

            wacc_overrides = {}
            raw_wacc = raw.get("wacc") or {}
            for key, value, current_value in (
                ("beta", beta, case.wacc.beta),
                ("pretax_cost_of_debt", cost_of_debt, case.wacc.cost_of_debt_pretax),
                ("wacc_override", wacc, case.wacc.wacc),
            ):
                override = _scalar_editor_override(
                    value, current_value, raw_wacc.get(key)
                )
                if override is not None:
                    wacc_overrides[key] = override
            if wacc_overrides:
                payload["wacc"] = wacc_overrides

            terminal_overrides = {}
            raw_terminal = raw.get("terminal") or {}
            for key, value, current_value in (
                ("perpetuity_growth", perpetual_growth, current.perpetuity_growth),
                ("roic", terminal_roic, current.terminal_roic),
                ("wacc", terminal_wacc, current.terminal_wacc),
                ("exit_multiple", exit_multiple, case.exit_multiple),
            ):
                override = _scalar_editor_override(
                    value, current_value, raw_terminal.get(key)
                )
                if override is not None:
                    terminal_overrides[key] = override
            if terminal_overrides:
                payload["terminal"] = terminal_overrides

            if revenue_method == "Capital IQ segment mix":
                payload["segments"] = "auto"
            elif revenue_method == "Preserve custom segment build":
                payload["segments"] = raw["segments"]
            if review_note.strip():
                payload["review_note"] = review_note.strip()

            override_count = sum(len(v) for v in scenario_overrides.values())
            override_count += len(wacc_overrides) + len(terminal_overrides)
            st.caption(
                f"{override_count} analyst override(s) will be stored. Unchanged fields remain automatic."
            )
            submitted = st.form_submit_button(
                "Save assumptions and recalculate",
                type="primary",
                disabled=demo_mode,
                use_container_width=True,
            )

        if submitted:
            effective_errors = []
            if perpetual_growth >= terminal_wacc:
                effective_errors.append("Perpetuity growth must be below terminal WACC.")
            if terminal_roic <= perpetual_growth:
                effective_errors.append("Terminal ROIC must exceed perpetuity growth.")
            if status == "final" and not review_note.strip():
                effective_errors.append("A final assumption set requires an analyst rationale.")
            if effective_errors:
                for error in effective_errors:
                    st.error(error)
            else:
                try:
                    path = save_assumption_payload(company_id, assumptions_dir, payload)
                    st.session_state[flash_key] = (
                        f"Assumptions saved to {path.name}. The valuation has been recalculated."
                    )
                    st.rerun()
                except AssumptionValidationError as exc:
                    for error in exc.errors:
                        st.error(error)

        if current.from_file and not demo_mode:
            st.divider()
            confirm = st.checkbox(
                "I understand this archives the current file and restores all automatic assumptions",
                key=f"{prefix}_reset_confirm",
            )
            if st.button(
                "Restore automatic assumptions",
                disabled=not confirm,
                key=f"{prefix}_reset",
            ):
                if reset_assumption_payload(company_id, assumptions_dir):
                    st.session_state[flash_key] = (
                        "Analyst assumptions archived; the company is back on automatic defaults."
                    )
                    st.rerun()
