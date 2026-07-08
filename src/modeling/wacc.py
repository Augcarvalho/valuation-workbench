"""WACC build — CAPM cost of equity, cost of debt, capital-structure weights.

Design goal: *show your work*. The result carries every component and a notes
list recording each fallback (e.g. "beta: default 1.0 — no beta data yet"),
so the dashboard panel and the case appendix can disclose exactly how the
discount rate was assembled — the way the Grupo Mateus WACC tab does.

Beta: uses ``beta_2y`` from the market data when present (export v3 field),
else the median of peer betas, else a flagged default of 1.0. Unlever/relever
helpers are provided (and tested) for the peer-beta workflow once beta data
is exported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Sanity bounds for a derived pre-tax cost of debt.
KD_BOUNDS = (0.02, 0.20)
DEFAULT_BETA = 1.0


@dataclass
class WaccResult:
    wacc: float
    cost_of_equity: float
    cost_of_debt_pretax: float
    cost_of_debt_aftertax: float
    beta: float
    beta_source: str                   # market_data | peers | default | analyst
    risk_free_rate: float
    equity_risk_premium: float
    country_risk_premium: float
    tax_rate: float
    equity_value: float
    debt_value: float
    equity_weight: float
    debt_weight: float
    overridden: bool = False
    notes: list[str] = field(default_factory=list)


def unlever_beta(levered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada: beta_u = beta_l / (1 + (1 - t) * D/E)."""
    return levered_beta / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def relever_beta(unlevered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada inverse: beta_l = beta_u * (1 + (1 - t) * D/E)."""
    return unlevered_beta * (1.0 + (1.0 - tax_rate) * debt_to_equity)


def _clean(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _resolve_beta(row: pd.Series, peers: pd.DataFrame | None, analyst_beta: float | None,
                  tax_rate: float, notes: list[str]) -> tuple[float, str]:
    if analyst_beta is not None:
        return analyst_beta, "analyst"

    own = _clean(row.get("beta_2y"))
    if own is not None and own > 0:
        return own, "market_data"

    # Peer-median unlever/relever when peer betas exist (post export-v3).
    if peers is not None and "beta_2y" in getattr(peers, "columns", []):
        usable = peers.dropna(subset=["beta_2y"])
        usable = usable[(usable["beta_2y"] > 0)]
        if len(usable) >= 3 and {"total_debt", "market_cap"} <= set(usable.columns):
            de = (usable["total_debt"].fillna(0) / usable["market_cap"]).replace([np.inf, -np.inf], np.nan)
            unlevered = [
                unlever_beta(float(b), float(d), tax_rate)
                for b, d in zip(usable["beta_2y"], de)
                if pd.notna(d) and d >= 0
            ]
            if unlevered:
                target_de = 0.0
                own_debt, own_equity = _clean(row.get("total_debt")), _clean(row.get("market_cap"))
                if own_debt is not None and own_equity and own_equity > 0:
                    target_de = own_debt / own_equity
                beta = relever_beta(float(np.median(unlevered)), target_de, tax_rate)
                notes.append(f"beta relevered from {len(unlevered)} peer betas at D/E {target_de:.2f}")
                return beta, "peers"

    notes.append("beta: default 1.0 — no beta data exported yet (export v3 adds IQ_BETA_2YR)")
    return DEFAULT_BETA, "default"


def _resolve_cost_of_debt(row: pd.Series, params: dict, analyst_kd: float | None,
                          notes: list[str]) -> float:
    if analyst_kd is not None:
        return analyst_kd
    interest = _clean(row.get("interest_expense_ttm"))
    debt = _clean(row.get("total_debt"))
    if interest is not None and debt and debt > 0 and interest > 0:
        kd = interest / debt
        bounded = float(np.clip(kd, *KD_BOUNDS))
        if bounded != kd:
            notes.append(f"derived Kd {kd:.1%} outside sanity bounds; clipped to {bounded:.1%}")
        return bounded
    fallback = params["risk_free_rate"] + params["country_risk_premium"] + 0.02
    notes.append(f"no interest/debt data for Kd; using rf + country premium + 200bps = {fallback:.1%}")
    return fallback


def build_wacc(
    row: pd.Series,
    params: dict,
    peers: pd.DataFrame | None = None,
    beta_override: float | None = None,
    kd_override: float | None = None,
    wacc_override: float | None = None,
) -> WaccResult:
    notes: list[str] = []
    tax = params["tax_rate"]

    beta, beta_source = _resolve_beta(row, peers, beta_override, tax, notes)
    ke = params["risk_free_rate"] + beta * params["equity_risk_premium"] + params["country_risk_premium"]
    kd_pre = _resolve_cost_of_debt(row, params, kd_override, notes)
    kd_post = kd_pre * (1.0 - tax)

    equity = _clean(row.get("market_cap")) or 0.0
    debt = _clean(row.get("total_debt")) or 0.0
    if equity <= 0:
        notes.append("market cap missing; weighting 100% equity")
        equity, debt = 1.0, 0.0
    total = equity + debt
    we, wd = equity / total, debt / total

    wacc = we * ke + wd * kd_post
    overridden = False
    if wacc_override is not None:
        notes.append(f"analyst WACC override applied: {wacc_override:.1%} (computed {wacc:.1%})")
        wacc = wacc_override
        overridden = True

    return WaccResult(
        wacc=wacc,
        cost_of_equity=ke,
        cost_of_debt_pretax=kd_pre,
        cost_of_debt_aftertax=kd_post,
        beta=beta,
        beta_source=beta_source,
        risk_free_rate=params["risk_free_rate"],
        equity_risk_premium=params["equity_risk_premium"],
        country_risk_premium=params["country_risk_premium"],
        tax_rate=tax,
        equity_value=equity,
        debt_value=debt,
        equity_weight=we,
        debt_weight=wd,
        overridden=overridden,
        notes=notes,
    )
