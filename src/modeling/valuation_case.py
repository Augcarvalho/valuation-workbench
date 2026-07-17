"""Valuation case orchestrator: one call assembles the full IB-style case.

Pulls together the assessment (peer group, verdict), assumptions (YAML or
anchored defaults), WACC build, three DCF scenarios, sensitivity grids,
comps spread, and the recommendation — the single object the Streamlit page
and the HTML export both consume, keeping every surface consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.modeling.assessment import Assessment, build_assessment
from src.modeling.comps import comps_spread, exit_multiple_from_comps, quartile_stats
from src.modeling.dcf import (
    DcfResult,
    driver_tornado,
    run_dcf,
    run_all_scenarios,
    sensitivity_growth_margin,
    sensitivity_implied_growth,
    sensitivity_wacc_multiple,
)
from src.modeling.outliers import multiple_outlier_reason
from src.modeling.recommendation import Recommendation, recommend
from src.modeling.valuation_assumptions import (
    ValuationAssumptions,
    load_valuation_assumptions,
    load_wacc_params,
)
from src.modeling.wacc import WaccResult, build_terminal_wacc, build_wacc


class CaseNotApplicableError(Exception):
    """Raised when a standard operating-company DCF is not a valid model for
    this name (financial institutions) or required anchors are missing.
    Callers render a graceful not-applicable state instead of a case."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


def dcf_applicability(row: pd.Series) -> tuple[bool, str, str]:
    """(applicable, reason, detail). Standard DCF requires an operating model
    and positive revenue/EBITDA anchors."""
    business_model = str(row.get("business_model", "operating")).lower()
    if business_model in ("financial", "insurer"):
        return (False, "Financial institution - EBITDA DCF not applicable",
                "Lenders and banks are funded by their balance sheet; an enterprise-value DCF on "
                "EBITDA is not meaningful. A dividend-discount / excess-return model is the right "
                "tool. Use the Financials Valuation framework and P/E / P/TBV comps instead.")
    revenue = row.get("revenue_ttm")
    if revenue is None or pd.isna(revenue) or revenue <= 0:
        return (False, "Missing revenue anchor",
                "The trailing-twelve-month revenue anchor is missing or non-positive in the latest "
                "export, so no forecast can be built. Check field coverage on Data & Refresh.")
    ebitda = row.get("ebitda_ttm")
    if ebitda is None or pd.isna(ebitda) or ebitda <= 0:
        return (False, "Non-positive EBITDA anchor",
                "Terminal value on an exit EV/EBITDA multiple is not meaningful with non-positive "
                "TTM EBITDA. Revisit once profitability data normalizes.")
    return True, "", ""


def case_warnings(case: "ValuationCase") -> list[dict]:
    """Model-quality warnings, strongest first. Each: {severity, text}."""
    warnings: list[dict] = []
    base = case.base
    w = case.wacc

    tv_pct = base.terminal_pct_of_ev
    if pd.notna(tv_pct):
        if tv_pct > 1.0:
            warnings.append({"severity": "high",
                             "text": f"Terminal value is {tv_pct:.0%} of EV - the explicit period destroys value; "
                                     f"the case is entirely an exit-multiple bet."})
        elif tv_pct > 0.85:
            warnings.append({"severity": "medium",
                             "text": f"Terminal value is {tv_pct:.0%} of EV - the DCF adds little beyond the exit multiple."})

    if (base.implied_terminal_growth is not None
            and base.implied_terminal_growth >= base.terminal_wacc - 0.015):
        warnings.append({"severity": "high",
                         "text": f"Exit multiple implies {base.implied_terminal_growth:+.1%} perpetual growth, within "
                                 f"150bps of the {base.terminal_wacc:.1%} terminal WACC - it embeds "
                                 f"near-perpetual value creation."})

    terminal_growth_gap = abs(base.forecast["revenue_growth"].iloc[-1] - base.perpetuity_growth)
    if terminal_growth_gap > 0.02:
        warnings.append({"severity": "medium",
                         "text": f"Year-{len(base.forecast)} revenue growth is "
                                 f"{base.forecast['revenue_growth'].iloc[-1]:.1%} versus "
                                 f"{base.perpetuity_growth:.1%} in perpetuity. Terminal FCFF is normalized, "
                                 f"but the explicit fade should be reviewed."})

    rr = base.terminal_reinvestment_rate
    if rr is None or rr < 0 or rr > 1:
        warnings.append({"severity": "high",
                         "text": "Terminal reinvestment is outside 0-100%; Gordon Growth is not "
                                 "economically valid until terminal ROIC and growth are reconciled."})
    elif base.terminal_roic < base.terminal_wacc:
        warnings.append({"severity": "medium",
                         "text": f"Terminal ROIC {base.terminal_roic:.1%} is below terminal WACC "
                                 f"{base.terminal_wacc:.1%}; perpetual growth destroys value."})

    if abs(base.terminal_wacc - w.wacc) > 0.02:
        warnings.append({"severity": "low",
                         "text": f"WACC converges from {w.wacc:.1%} during the explicit period to "
                                 f"{base.terminal_wacc:.1%} in stable growth."})

    if w.wacc <= w.risk_free_rate + 0.005:
        warnings.append({"severity": "high",
                         "text": f"WACC {w.wacc:.1%} is within 50bps of or below the risk-free rate "
                                 f"{w.risk_free_rate:.1%}; check beta, leverage, and tax-shield assumptions."})

    if w.beta_source == "default":
        warnings.append({"severity": "medium",
                         "text": "Beta is the default 1.0 (no beta data exported yet) - cost of equity is generic."})
    elif w.beta < 0.4 or w.beta > 2.5:
        warnings.append({"severity": "low",
                         "text": f"Levered beta of {w.beta:.2f} is extreme - thin trading can depress measured "
                                 f"beta; consider a peer-relevered beta via the assumptions file."})

    if ("LTM" in case.exit_multiple_source or "fallback" in case.exit_multiple_source
            or "own" in case.exit_multiple_source or "default" in case.exit_multiple_source):
        warnings.append({"severity": "medium",
                         "text": f"Exit multiple comes from {case.exit_multiple_source} - forward comps preferred."})

    if case.market_reference_multiple is not None and case.exit_multiple > 0:
        market_gap = case.market_reference_multiple / case.exit_multiple - 1.0
        if abs(market_gap) > 0.25:
            direction = "above" if market_gap > 0 else "below"
            warnings.append({"severity": "medium",
                             "text": f"Market reference {case.market_reference_multiple:.1f}x is "
                                     f"{abs(market_gap):.0%} {direction} the fundamental terminal "
                                     f"multiple {case.exit_multiple:.1f}x. This is an expectations "
                                     f"gap, not an automatic DCF input."})

    if base.upside is not None and abs(base.upside) > 1.0:
        warnings.append({"severity": "medium",
                         "text": f"Base-case upside of {base.upside:+.0%} is beyond +/-100% - treat as calibration, "
                                 f"not a target."})

    if str(case.assessment.business_model) == "insurer":
        warnings.append({"severity": "medium",
                         "text": "Managed care / insurer: EBITDA DCF is a rough fit (MLR-driven economics); an "
                                 "earnings-based model is preferred for a final view."})

    order = {"high": 0, "medium": 1}
    return sorted(warnings, key=lambda x: order.get(x["severity"], 2))


@dataclass
class ValuationCase:
    company_id: str
    assessment: Assessment
    assumptions: ValuationAssumptions
    wacc: WaccResult
    exit_multiple: float
    exit_multiple_source: str
    market_reference_multiple: float | None
    market_reference_source: str
    scenarios: dict[str, DcfResult]
    sens_wacc_multiple: pd.DataFrame
    sens_growth_margin: pd.DataFrame
    sens_implied_growth: pd.DataFrame
    tornado: pd.DataFrame
    spread: pd.DataFrame
    spread_stats: pd.DataFrame
    recommendation: Recommendation
    notes: list[str] = field(default_factory=list)

    @property
    def base(self) -> DcfResult:
        return self.scenarios["base"]


def build_valuation_case(df: pd.DataFrame, company_id: str, store=None) -> ValuationCase:
    assessment = build_assessment(df, company_id, store=store)
    row = assessment.row

    applicable, reason, detail = dcf_applicability(row)
    if not applicable:
        raise CaseNotApplicableError(reason, detail)

    notes: list[str] = []

    params = load_wacc_params(str(row.get("currency", "USD")))
    assumptions = load_valuation_assumptions(
        row,
        getattr(store, "assumptions_dir", None),
        params,
    )
    if assumptions.terminal_roic_source == "anchored" and "roic_ttm" in assessment.peers.columns:
        peer_roic = pd.to_numeric(
            assessment.peers.loc[
                assessment.peers["company_id"].astype(str) != str(company_id),
                "roic_ttm",
            ],
            errors="coerce",
        )
        peer_roic = peer_roic[(peer_roic > 0.02) & (peer_roic < 0.60)].dropna()
        if len(peer_roic) >= 3:
            assumptions.terminal_roic = float(
                max(
                    assumptions.perpetuity_growth + 0.02,
                    min(peer_roic.median(), 0.30),
                )
            )
            assumptions.terminal_roic_source = f"peer median ({len(peer_roic)} names)"
            assumptions.anchors.setdefault("notes", []).append(
                f"terminal ROIC converges to peer median {assumptions.terminal_roic:.1%}"
            )
    notes.extend(assumptions.anchors.get("notes", []))
    if not assumptions.from_file:
        notes.append(
            "no analyst assumptions file; all drivers anchored on TTM data "
            "(copy data/templates/valuation_assumptions_template.yaml to refine)"
        )

    wacc = build_wacc(
        row,
        params,
        peers=assessment.peers,
        beta_override=assumptions.beta,
        kd_override=assumptions.pretax_cost_of_debt,
        wacc_override=assumptions.wacc_override,
    )
    assumptions.terminal_wacc, assumptions.terminal_wacc_source = build_terminal_wacc(
        wacc,
        params,
        peers=assessment.peers,
        override=assumptions.terminal_wacc,
        company_id=company_id,
    )

    estimates = getattr(store, "estimates", None)
    spread = comps_spread(assessment.peers, estimates)
    peer_spread = spread.loc[spread["company_id"].astype(str) != str(company_id)]
    stats = quartile_stats(peer_spread if not peer_spread.empty else spread)

    peer_mult, peer_label = exit_multiple_from_comps(spread, anchor_company_id=company_id)
    own = row.get("ev_to_ebitda_ttm")
    own_ok = pd.notna(own) and own > 0
    own_outlier = multiple_outlier_reason("ev_to_ebitda_ttm", own) if own_ok else None
    if own_outlier:
        own_ok = False
        notes.append(f"own LTM EV/EBITDA {float(own):.1f}x is {own_outlier}; "
                     "not used as a market reference")
    if peer_mult is not None:
        market_reference_multiple, market_reference_source = peer_mult, peer_label
    elif own_ok:
        market_reference_multiple = float(own)
        market_reference_source = "own LTM multiple (peer multiples unavailable)"
    else:
        market_reference_multiple, market_reference_source = None, "market reference unavailable"

    if assumptions.exit_multiple is not None:
        exit_multiple, exit_source = assumptions.exit_multiple, "analyst assumption"
    else:
        # Automatic DCFs must not silently turn a current peer multiple into a
        # year-N terminal assumption. First calculate the stable-growth value,
        # then express those SAME economics as an EV/EBITDA multiple. The
        # independent peer multiple remains a disclosed market cross-check.
        probe_multiple = market_reference_multiple or 8.0
        probe = run_dcf(
            row,
            assumptions.scenarios["base"],
            assumptions,
            wacc.wacc,
            probe_multiple,
        )
        if probe.implied_exit_multiple is not None and probe.implied_exit_multiple > 0:
            exit_multiple = float(probe.implied_exit_multiple)
            exit_source = "fundamental terminal multiple (Gordon-consistent)"
            if market_reference_multiple is not None:
                notes.append(
                    f"market reference {market_reference_source}: {market_reference_multiple:.1f}x; "
                    f"automatic DCF uses {exit_multiple:.1f}x from stable-growth fundamentals"
                )
        elif market_reference_multiple is not None:
            exit_multiple, exit_source = market_reference_multiple, market_reference_source
            notes.append("fundamental terminal multiple unavailable; market reference used as fallback")
        else:
            exit_multiple, exit_source = 8.0, "default 8.0x"
            notes.append("fundamental and market terminal multiples unavailable; default 8.0x fallback")

    scenarios = run_all_scenarios(row, assumptions, wacc.wacc, exit_multiple)
    base = scenarios["base"]

    sens_wm = sensitivity_wacc_multiple(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    sens_gm = sensitivity_growth_margin(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    sens_ig = sensitivity_implied_growth(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    tornado = driver_tornado(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)

    formal_reasons = []
    if not assumptions.from_file:
        formal_reasons.append("No analyst assumptions file exists")
    elif assumptions.status != "final":
        formal_reasons.append(f"Assumptions status is {assumptions.status}, not final")
    if not assessment.peer_reviewed:
        formal_reasons.append("Peer set is not analyst-approved")
    recommendation = recommend(
        upside=base.upside,
        bear_upside=scenarios["bear"].upside,
        bull_upside=scenarios["bull"].upside,
        verdict_key=assessment.verdict_key,
        formal=not formal_reasons,
        formal_reason="; ".join(formal_reasons),
    )

    return ValuationCase(
        company_id=company_id,
        assessment=assessment,
        assumptions=assumptions,
        wacc=wacc,
        exit_multiple=exit_multiple,
        exit_multiple_source=exit_source,
        market_reference_multiple=market_reference_multiple,
        market_reference_source=market_reference_source,
        scenarios=scenarios,
        sens_wacc_multiple=sens_wm,
        sens_growth_margin=sens_gm,
        sens_implied_growth=sens_ig,
        tornado=tornado,
        spread=spread,
        spread_stats=stats,
        recommendation=recommendation,
        notes=notes,
    )
