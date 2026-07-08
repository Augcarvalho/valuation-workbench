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
    run_all_scenarios,
    sensitivity_growth_margin,
    sensitivity_implied_growth,
    sensitivity_wacc_multiple,
)
from src.modeling.recommendation import Recommendation, recommend
from src.modeling.valuation_assumptions import (
    ValuationAssumptions,
    load_valuation_assumptions,
    load_wacc_params,
)
from src.modeling.wacc import WaccResult, build_wacc


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
    if business_model == "financial":
        return (False, "Financial institution - EBITDA DCF not applicable",
                "Lenders and banks are funded by their balance sheet; an enterprise-value DCF on "
                "EBITDA is not meaningful. A dividend-discount / excess-return model is the right "
                "tool and is on the roadmap. Use the P/E and P/TBV comps on the Valuation & "
                "Expectations page in the meantime.")
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

    if base.implied_terminal_growth is not None and base.implied_terminal_growth >= w.wacc - 0.015:
        warnings.append({"severity": "high",
                         "text": f"Exit multiple implies {base.implied_terminal_growth:+.1%} perpetual growth, within "
                                 f"150bps of the {w.wacc:.1%} WACC - it embeds near-perpetual value creation."})

    if w.wacc <= w.risk_free_rate + 0.005:
        warnings.append({"severity": "high",
                         "text": f"WACC {w.wacc:.1%} is at or below the risk-free rate {w.risk_free_rate:.1%} - "
                                 f"discounting is effectively free; check capital-structure inputs."})

    if w.beta_source == "default":
        warnings.append({"severity": "medium",
                         "text": "Beta is the default 1.0 (no beta data exported yet) - cost of equity is generic."})
    elif w.beta < 0.4 or w.beta > 2.5:
        warnings.append({"severity": "low",
                         "text": f"Levered beta of {w.beta:.2f} is extreme - thin trading can depress measured "
                                 f"beta; consider a peer-relevered beta via the assumptions file."})

    if "no re-rating assumed" in case.exit_multiple_source:
        warnings.append({"severity": "low",
                         "text": "Exit at the company's own multiple (deliberate: re-rating to the peer median "
                                 "is an analyst call, set via the assumptions file)."})
    elif ("LTM" in case.exit_multiple_source or "fallback" in case.exit_multiple_source
            or "own" in case.exit_multiple_source or "default" in case.exit_multiple_source):
        warnings.append({"severity": "medium",
                         "text": f"Exit multiple comes from {case.exit_multiple_source} - forward comps preferred."})

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

    estimates = getattr(store, "estimates", None)
    spread = comps_spread(assessment.peers, estimates)
    stats = quartile_stats(spread)

    if assumptions.exit_multiple is not None:
        exit_multiple, exit_source = assumptions.exit_multiple, "analyst assumption"
    else:
        peer_mult, peer_label = exit_multiple_from_comps(spread, anchor_company_id=company_id)
        own = row.get("ev_to_ebitda_ttm")
        own_ok = pd.notna(own) and own > 0
        if not assumptions.from_file and own_ok:
            # Auto-anchored cases exit at the company's OWN multiple: embedding a
            # re-rating to the peer median is an analyst call, not a default.
            # (Root cause of the old >100%-upside and TV-divergence warnings.)
            exit_multiple, exit_source = float(own), "own LTM multiple (no re-rating assumed)"
            if peer_mult is not None:
                notes.append(f"peer reference: {peer_label} {peer_mult:.1f}x vs own "
                             f"{float(own):.1f}x - re-rate only via the assumptions file")
        elif peer_mult is not None:
            exit_multiple, exit_source = peer_mult, peer_label
        elif own_ok:
            exit_multiple, exit_source = float(own), "own LTM multiple (peer multiples unavailable)"
            notes.append(f"exit multiple fallback: {exit_source}")
        else:
            exit_multiple, exit_source = 8.0, "default 8.0x"
            notes.append("exit multiple fallback: default 8.0x")

    scenarios = run_all_scenarios(row, assumptions, wacc.wacc, exit_multiple)
    base = scenarios["base"]

    sens_wm = sensitivity_wacc_multiple(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    sens_gm = sensitivity_growth_margin(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    sens_ig = sensitivity_implied_growth(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)
    tornado = driver_tornado(row, assumptions.scenarios["base"], assumptions, wacc.wacc, exit_multiple)

    recommendation = recommend(
        upside=base.upside,
        bear_upside=scenarios["bear"].upside,
        bull_upside=scenarios["bull"].upside,
        verdict_key=assessment.verdict_key,
        # No analyst assumptions file -> never a formal BUY/HOLD/SELL.
        formal=assumptions.from_file,
    )

    return ValuationCase(
        company_id=company_id,
        assessment=assessment,
        assumptions=assumptions,
        wacc=wacc,
        exit_multiple=exit_multiple,
        exit_multiple_source=exit_source,
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
