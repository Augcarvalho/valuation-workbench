"""Valuation case orchestrator: one call assembles the full IB-style case.

Pulls together the assessment (peer group, verdict), assumptions (YAML or
anchored defaults), WACC build, three DCF scenarios, sensitivity grids,
comps spread, and the recommendation — the single object the Streamlit page
and the HTML export both consume, keeping every surface consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json

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
from src.modeling.readiness import ReadinessResult, evaluate_readiness
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
    """Backward-compatible integrity-only warning payload.

    Assumption governance and valuation cross-checks are intentionally exposed
    through :mod:`valuation_diagnostics`; they are not model failures.
    """
    from src.modeling.valuation_diagnostics import diagnostics_for

    return [
        {"severity": item.severity, "text": item.text}
        for item in diagnostics_for(case, "integrity")
    ]


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
    sponsor_exit_multiple: float
    sponsor_exit_multiple_source: str
    scenarios: dict[str, DcfResult]
    sens_wacc_multiple: pd.DataFrame
    sens_growth_margin: pd.DataFrame
    sens_implied_growth: pd.DataFrame
    tornado: pd.DataFrame
    spread: pd.DataFrame
    spread_stats: pd.DataFrame
    recommendation: Recommendation
    notes: list[str] = field(default_factory=list)
    case_id: str = ""
    built_at: str = ""
    data_vintage: dict = field(default_factory=dict)
    readiness: ReadinessResult | None = None
    lbo: object | None = None
    lbo_scenarios: dict = field(default_factory=dict)
    underwriting_terms: dict = field(default_factory=dict)
    methodology_version: str = "pe-underwriting-v2"

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
        operating_kpis=getattr(store, "operating_kpis", pd.DataFrame()),
        company_segments=getattr(store, "company_segments", pd.DataFrame()),
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
            "no manual-input assumptions file; all drivers anchored on TTM data "
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
    # A mechanical case should not assume value-destructive growth forever.
    # Competitive steady state (ROIC = WACC) is the neutral default; analysts
    # can explicitly underwrite a premium or discount through the YAML.
    if (assumptions.terminal_roic_source != "analyst"
            and assumptions.terminal_roic < assumptions.terminal_wacc):
        prior_roic = assumptions.terminal_roic
        prior_source = assumptions.terminal_roic_source
        assumptions.terminal_roic = float(assumptions.terminal_wacc)
        assumptions.terminal_roic_source = "stable-state WACC normalization"
        note = (
            f"terminal ROIC normalized from {prior_roic:.1%} ({prior_source}) to "
            f"terminal WACC {assumptions.terminal_wacc:.1%}; automatic cases assume "
            "zero excess return in competitive steady state"
        )
        assumptions.anchors.setdefault("notes", []).append(note)
        notes.append(note)

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
        formal_reasons.append("No manual-input assumptions file exists")
    elif assumptions.status != "final":
        formal_reasons.append(f"Assumptions status is {assumptions.status}, not final")
    if not assessment.peer_reviewed:
        formal_reasons.append("Peer set is not manually approved")
    recommendation = recommend(
        upside=base.upside,
        bear_upside=scenarios["bear"].upside,
        bull_upside=scenarios["bull"].upside,
        verdict_key=assessment.verdict_key,
        formal=not formal_reasons,
        formal_reason="; ".join(formal_reasons),
        calibration_label=(
            "Auto-anchored calibration"
            if not assumptions.from_file
            else f"{assumptions.status.title()} manual calibration"
        ),
    )

    if assumptions.exit_multiple is not None:
        sponsor_exit_multiple = float(assumptions.exit_multiple)
        sponsor_exit_source = "manual transaction assumption"
    else:
        own_multiple = row.get("ev_to_ebitda_ttm")
        own_multiple = float(own_multiple) if pd.notna(own_multiple) and own_multiple > 0 else None
        candidates = [value for value in (own_multiple, market_reference_multiple, exit_multiple)
                      if value is not None and value > 0]
        sponsor_exit_multiple = float(min(candidates)) if candidates else float(exit_multiple)
        sponsor_exit_source = "conservative no-expansion screen"

    case = ValuationCase(
        company_id=company_id,
        assessment=assessment,
        assumptions=assumptions,
        wacc=wacc,
        exit_multiple=exit_multiple,
        exit_multiple_source=exit_source,
        market_reference_multiple=market_reference_multiple,
        market_reference_source=market_reference_source,
        sponsor_exit_multiple=sponsor_exit_multiple,
        sponsor_exit_multiple_source=sponsor_exit_source,
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
    case.built_at = datetime.now(timezone.utc).isoformat()
    case.data_vintage = {
        "financial_period": str(pd.to_datetime(row.get("fiscal_period_end", row.get("period"))).date()),
        "market_period": str(pd.to_datetime(row.get("market_period"), errors="coerce").date())
        if pd.notna(pd.to_datetime(row.get("market_period"), errors="coerce")) else None,
        "estimate_period": str(pd.to_datetime(row.get("estimate_period"), errors="coerce").date())
        if pd.notna(pd.to_datetime(row.get("estimate_period"), errors="coerce")) else None,
        "peer_set": assessment.peer_set_name,
        "peer_reviewed": assessment.peer_reviewed,
    }
    debt = row.get("total_debt")
    debt = float(debt) if pd.notna(debt) else 0.0
    cash = row.get("cash_st_invest")
    if pd.isna(cash):
        cash = row.get("cash")
    cash = float(cash) if pd.notna(cash) else 0.0
    restricted_cash = row.get("restricted_cash")
    restricted_cash = float(restricted_cash) if pd.notna(restricted_cash) else 0.0
    revenue = row.get("revenue_ttm")
    revenue = float(revenue) if pd.notna(revenue) else 0.0
    case.underwriting_terms = {
        "entry_leverage": 3.0,
        "hold_period_years": 5,
        "minimum_cash": max(restricted_cash, revenue * 0.02),
        "revolver_capacity": float(row.get("ebitda_ttm")) * 0.5,
        "mandatory_amortization_pct": 0.01,
        "financing_fees_pct_debt": 0.015,
        "interest_deduction_cap_pct_ebitda": 0.30,
        "max_net_leverage": 6.0,
        "min_interest_coverage": 1.5,
        "existing_debt_refinanced": debt,
        "acquired_cash": cash,
    }
    payload = {
        "company_id": company_id,
        "fiscal_period_id": row.get("fiscal_period_id"),
        "assumption_status": assumptions.status,
        "scenario_drivers": {
            name: {
                "growth": scenario.revenue_growth,
                "margin": scenario.ebitda_margin,
                "capex": scenario.capex_pct,
                "tax": scenario.tax_rate,
                "exit_multiple": scenario.exit_multiple,
            }
            for name, scenario in assumptions.scenarios.items()
        },
        "wacc": wacc.wacc,
        "exit_multiple": exit_multiple,
        "sponsor_exit_multiple": sponsor_exit_multiple,
        "underwriting_terms": case.underwriting_terms,
        "peers": sorted(assessment.peers["company_id"].astype(str).tolist()),
        "methodology": case.methodology_version,
    }
    from src.modeling.operating_drivers import operating_driver_payload

    payload["operating_driver"] = operating_driver_payload(
        assumptions.operating_driver_build
    )
    case.case_id = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    fallback_kd = wacc.cost_of_debt_source == "fallback"
    from src.modeling.data_audit import run_audit
    from src.modeling.metrics import latest_rows

    audit_issues = run_audit(
        df,
        latest_rows(df),
        exports={},
        refresh_log=getattr(store, "refresh_log", None),
    )
    case.readiness = evaluate_readiness(
        row,
        audit_issues=audit_issues,
        assumptions_final=assumptions.status == "final",
        peers_reviewed=assessment.peer_reviewed,
        uses_fallback_beta=wacc.beta_source not in {"peers", "analyst"},
        uses_fallback_cost_of_debt=fallback_kd,
    )
    from src.modeling.lbo import lbo_from_case, run_lbo

    case.lbo = lbo_from_case(case, **case.underwriting_terms)
    entry_ebitda = float(row.get("ebitda_ttm"))
    own_multiple = row.get("ev_to_ebitda_ttm")
    entry_multiple = (
        float(own_multiple)
        if pd.notna(own_multiple) and float(own_multiple) > 0
        else case.sponsor_exit_multiple
    )
    for name, dcf_result in case.scenarios.items():
        scenario_assumption = assumptions.scenarios[name]
        if scenario_assumption.exit_multiple is not None:
            scenario_exit = scenario_assumption.exit_multiple
        elif name == "bear":
            scenario_exit = max(case.sponsor_exit_multiple - 1.0, 2.0)
        else:
            scenario_exit = case.sponsor_exit_multiple
        case.lbo_scenarios[name] = run_lbo(
            dcf_result.forecast,
            entry_ebitda=entry_ebitda,
            entry_multiple=entry_multiple,
            exit_multiple=scenario_exit,
            cost_of_debt=wacc.cost_of_debt_pretax,
            tax_rate=scenario_assumption.tax_rate,
            **case.underwriting_terms,
        )
    return case
