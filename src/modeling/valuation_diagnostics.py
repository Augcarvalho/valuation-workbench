"""Structured valuation diagnostics.

The old page put every caveat under "Model-Quality Warnings". That blurred
three different questions:

1. Is the model mathematically/economically valid?
2. Which assumptions still require manual sign-off?
3. What is the valuation telling us versus the market?

Keeping those questions separate makes the framework stricter, not softer:
blocking errors remain prominent while normal valuation judgment is no longer
misrepresented as a broken model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValuationDiagnostic:
    code: str
    category: str             # integrity | assumption | cross_check
    severity: str             # high | medium | low
    title: str
    text: str
    action: str = ""

    def as_flag(self) -> dict:
        return {
            "severity": self.severity.title(),
            "area": self.title,
            "observation": self.text,
            "management_question": self.action,
        }


def _add(items: list[ValuationDiagnostic], code: str, category: str,
         severity: str, title: str, text: str, action: str = "") -> None:
    items.append(ValuationDiagnostic(code, category, severity, title, text, action))


def diagnose_case(case) -> list[ValuationDiagnostic]:
    """Return deterministic diagnostics for any operating-company DCF."""
    items: list[ValuationDiagnostic] = []
    base = case.base
    assumptions = case.assumptions
    wacc = case.wacc
    reviewed_cross_checks = getattr(assumptions, "reviewed_cross_checks", {}) or {}

    def _pending_cross_check(code: str) -> bool:
        """Only documented, final manual reviews can clear market cross-checks."""
        rationale = str(reviewed_cross_checks.get(code, "")).strip()
        return assumptions.status != "final" or not rationale

    # --- Integrity: model must not be relied upon until these are resolved. ---
    if not base.valid or base.implied_equity <= 0:
        _add(items, "non_positive_equity", "integrity", "high", "Equity bridge",
             "The base case produces non-positive implied equity.",
             "Reconcile enterprise value, net debt, minority interest, and preferred equity.")

    if base.terminal_wacc <= base.perpetuity_growth:
        _add(items, "wacc_below_growth", "integrity", "high", "Terminal value",
             f"Terminal WACC {base.terminal_wacc:.1%} must exceed perpetual growth "
             f"{base.perpetuity_growth:.1%}.",
             "Lower stable growth or revise the terminal discount rate.")

    rr = base.terminal_reinvestment_rate
    if rr is None or not np.isfinite(rr) or rr < 0 or rr > 1:
        _add(items, "invalid_reinvestment", "integrity", "high", "Stable reinvestment",
             "Terminal reinvestment is outside 0-100%; the Gordon Growth value is invalid.",
             "Set terminal ROIC above perpetual growth and verify terminal NOPAT.")

    component_low = min(wacc.cost_of_equity, wacc.cost_of_debt_aftertax)
    component_high = max(wacc.cost_of_equity, wacc.cost_of_debt_aftertax)
    if not (component_low - 1e-8 <= wacc.wacc <= component_high + 1e-8):
        _add(items, "wacc_outside_components", "integrity", "high", "WACC build",
             f"WACC {wacc.wacc:.1%} is outside its component-cost range "
             f"({component_low:.1%}-{component_high:.1%}).",
             "Check market-value weights and any WACC override.")

    scenario = assumptions.scenarios["base"]
    if any(g <= -1.0 or g > 1.0 for g in scenario.revenue_growth):
        _add(items, "growth_out_of_bounds", "integrity", "high", "Revenue forecast",
             "At least one revenue growth assumption is outside -100% to +100%.",
             "Correct the scenario glidepath in the assumptions file.")
    if any(m <= -0.5 or m > 1.0 for m in scenario.ebitda_margin):
        _add(items, "margin_out_of_bounds", "integrity", "high", "Margin forecast",
             "At least one EBITDA margin assumption is outside the model's economic bounds.",
             "Correct the margin glidepath in the assumptions file.")
    if any(v < 0 for v in scenario.d_and_a_pct + scenario.capex_pct):
        _add(items, "negative_reinvestment_driver", "integrity", "high", "Reinvestment",
             "D&A and capex intensity must be non-negative.",
             "Correct D&A or capex assumptions before using the case.")
    if not 0 <= scenario.tax_rate <= 0.60:
        _add(items, "tax_out_of_bounds", "integrity", "high", "Tax rate",
             f"The modeled tax rate of {scenario.tax_rate:.1%} is outside 0-60%.",
             "Use a normalized cash tax rate appropriate for the company and jurisdiction.")

    terminal_gap = abs(float(base.forecast["revenue_growth"].iloc[-1]) - base.perpetuity_growth)
    if terminal_gap > 0.02:
        _add(items, "abrupt_terminal_growth", "integrity", "medium", "Stable-state transition",
             f"Final explicit growth is {base.forecast['revenue_growth'].iloc[-1]:.1%} versus "
             f"{base.perpetuity_growth:.1%} in perpetuity.",
             "Add transition years so growth reaches a sustainable steady state gradually.")

    # --- Assumption governance: valid mechanically, pending human judgment. ---
    if not assumptions.from_file:
        _add(items, "no_analyst_file", "assumption", "medium", "Manual assumptions review",
             "No company-specific assumptions file exists; drivers are mechanically anchored.",
             "Use the Assumption Workbench to review the automatic defaults and save manual overrides.")
    elif assumptions.status != "final":
        _add(items, "assumptions_not_final", "assumption", "medium", "Manual assumptions review",
             f"The company assumptions are marked {assumptions.status}, not final.",
             "Refresh the operating case and record manual sign-off.")

    if wacc.beta_source == "default":
        _add(items, "default_beta", "assumption", "medium", "Beta",
             "Beta is the transparent 1.0 fallback because neither company nor peer beta passed validation.",
             "Refresh Capital IQ beta fields or provide a bottom-up peer beta override.")

    if any("no interest/debt data" in note for note in wacc.notes):
        _add(items, "fallback_cost_of_debt", "assumption", "medium", "Cost of debt",
             "Pre-tax cost of debt uses the reference-rate-plus-spread fallback.",
             "Refresh interest expense and average debt or enter a manual borrowing-cost assumption.")

    assessment = case.assessment
    if assessment.peer_warning:
        _add(items, "peer_warning", "assumption", "high", "Comparable companies",
             assessment.peer_warning,
             "Review the peer set and data coverage on Peer Benchmarking.")
    elif not assessment.peer_reviewed:
        source = str(assessment.peer_source).replace("_", " ")
        _add(items, "peers_unreviewed", "assumption", "medium", "Comparable companies",
             f"The {source} peer set has not been manually approved.",
             "Approve, reject, or manually adjust peers before relying on relative valuation.")

    anchor_notes = " | ".join(str(n) for n in assumptions.anchors.get("notes", []))
    if "assuming zero NWC change" in anchor_notes:
        _add(items, "fallback_nwc", "assumption", "medium", "Working capital",
             "Working-capital data is unavailable, so the automatic forecast assumes no NWC investment.",
             "Populate operating NWC or DSO/DIH/DPO before finalizing free cash flow.")
    if "defaulted to" in anchor_notes:
        _add(items, "generic_operating_fallback", "assumption", "medium", "Operating anchors",
             "One or more operating drivers use a generic fallback rather than company data.",
             "Review the Assumptions & Provenance table and replace generic inputs.")

    # --- Cross-checks: findings to interpret, not evidence that code is wrong. ---
    tv_pct = base.terminal_pct_of_ev
    if pd.notna(tv_pct) and tv_pct > 1.0:
        _add(items, "terminal_value_over_100", "cross_check", "high", "Value concentration",
             f"Terminal value is {tv_pct:.0%} of enterprise value because the explicit period destroys value.",
             "Explain the turnaround path or extend the explicit forecast.")
    elif pd.notna(tv_pct) and tv_pct > 0.90:
        _add(items, "terminal_value_concentration", "cross_check", "medium", "Value concentration",
             f"Terminal value represents {tv_pct:.0%} of enterprise value.",
             "Treat WACC, stable growth, and terminal ROIC as the primary valuation sensitivities.")

    implied_g = base.implied_terminal_growth
    if implied_g is not None and implied_g >= base.terminal_wacc - 0.015:
        _add(items, "implied_growth_near_wacc", "cross_check", "high", "Exit multiple",
             f"The exit multiple implies {implied_g:+.1%} perpetual growth, within 150bps of "
             f"terminal WACC {base.terminal_wacc:.1%}.",
             "Reduce the exit multiple or support a lower-risk, higher-return steady state.")

    if case.market_reference_multiple is not None and case.exit_multiple > 0:
        market_gap = case.market_reference_multiple / case.exit_multiple - 1.0
        if abs(market_gap) > 0.25 and _pending_cross_check("market_fundamental_gap"):
            direction = "above" if market_gap > 0 else "below"
            _add(items, "market_fundamental_gap", "cross_check", "medium", "Market expectations",
                 f"The market reference multiple is {abs(market_gap):.0%} {direction} the "
                 "fundamental terminal multiple.",
                 "Decide whether the gap reflects mispricing or operating assumptions the DCF has missed.")

    if base.terminal_roic < base.terminal_wacc:
        _add(items, "negative_terminal_spread", "cross_check", "medium", "Terminal economics",
             f"Terminal ROIC {base.terminal_roic:.1%} is below WACC {base.terminal_wacc:.1%}; "
             "growth destroys value in steady state.",
             "Retain only if permanent negative excess returns are an explicit manual view.")

    if (base.upside is not None and abs(base.upside) > 1.0
            and assumptions.status != "auto"):
        _add(items, "extreme_upside", "cross_check", "medium", "Equity value",
             f"Base-case upside is {base.upside:+.0%}.",
             "Reconcile units, the EV-to-equity bridge, WACC, terminal assumptions, and current market data.")

    if (not np.isnan(base.terminal_value_perp) and base.pv_terminal_exit > 0):
        gap = base.pv_terminal_perp / base.pv_terminal_exit - 1.0
        if abs(gap) > 0.25:
            direction = "above" if gap > 0 else "below"
            _add(items, "terminal_method_gap", "cross_check", "medium", "Terminal methods",
                 f"Perpetuity terminal value is {abs(gap):.0%} {direction} the exit-multiple result.",
                 "Reconcile growth, ROIC, WACC, and exit multiple before selecting a primary value.")

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: (item.category, order.get(item.severity, 3), item.code))


def diagnostics_for(case, category: str) -> list[ValuationDiagnostic]:
    return [d for d in diagnose_case(case) if d.category == category]


def integrity_status(case) -> tuple[str, str]:
    """Return a terse status and explanation for the UI/readiness gate."""
    findings = diagnostics_for(case, "integrity")
    if any(d.severity == "high" for d in findings):
        return "BLOCKED", "Resolve high-severity integrity findings"
    if findings:
        return "REVIEW", "Model runs, but transition mechanics need review"
    return "PASS", "No mathematical or economic integrity exceptions"
