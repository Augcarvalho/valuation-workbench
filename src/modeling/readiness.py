"""Case-readiness gates separating a screen from an IC-ready underwrite."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


READINESS_ORDER = {
    "DATA_BLOCKED": 0,
    "SCREENING_ONLY": 1,
    "MODEL_READY": 2,
    "MANUALLY_REVIEWED": 3,
    "IC_READY": 4,
}


@dataclass
class ReadinessResult:
    status: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def can_export_final(self) -> bool:
        return self.status == "IC_READY"


def evaluate_readiness(
    row: pd.Series,
    *,
    audit_issues: pd.DataFrame | None = None,
    assumptions_final: bool = False,
    peers_reviewed: bool = False,
    uses_fallback_beta: bool = False,
    uses_fallback_cost_of_debt: bool = False,
) -> ReadinessResult:
    blockers: list[str] = []
    warnings: list[str] = []
    checks = {
        "unique_fiscal_observation": bool(row.get("fiscal_period_id")),
        "ttm_complete": bool(row.get("ttm_complete", False)),
        "assumptions_final": assumptions_final,
        "peers_reviewed": peers_reviewed,
        "wacc_underwritten": not (uses_fallback_beta or uses_fallback_cost_of_debt),
    }
    if not checks["unique_fiscal_observation"]:
        blockers.append("missing canonical fiscal-period identity")
    if not checks["ttm_complete"]:
        blockers.append("incomplete trailing-twelve-month financials")
    if audit_issues is not None and not audit_issues.empty:
        cid = str(row.get("company_id"))
        mine = audit_issues[audit_issues["company_id"].astype(str).isin([cid, "UNIVERSE"])]
        high = mine[mine["severity"] == "high"]
        if not high.empty:
            blockers.append(f"{len(high)} unresolved high-severity data audit finding(s)")
        medium = mine[mine["severity"] == "medium"]
        if not medium.empty:
            warnings.append(f"{len(medium)} unresolved medium-severity data audit finding(s)")
    if blockers:
        status = "DATA_BLOCKED"
    elif not assumptions_final and not peers_reviewed:
        status = "SCREENING_ONLY"
    elif not assumptions_final or not peers_reviewed or not checks["wacc_underwritten"]:
        status = "MODEL_READY"
    elif warnings:
        status = "MANUALLY_REVIEWED"
    else:
        status = "IC_READY"
    if not assumptions_final:
        warnings.append("valuation assumptions are not final")
    if not peers_reviewed:
        warnings.append("peer set is not manually approved")
    if uses_fallback_beta:
        warnings.append("WACC uses fallback beta")
    if uses_fallback_cost_of_debt:
        warnings.append("WACC uses fallback cost of debt")
    return ReadinessResult(status=status, blockers=blockers, warnings=warnings, checks=checks)
