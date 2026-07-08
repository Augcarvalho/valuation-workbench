"""Operating forecast: driver-based projection to unlevered free cash flow.

Tier-1 model: single-segment percentage drivers —

    revenue_t = revenue_{t-1} * (1 + g_t)
    EBITDA_t  = revenue_t * margin_t
    D&A_t     = revenue_t * da_pct_t
    EBIT_t    = EBITDA_t - D&A_t
    taxes_t   = max(EBIT_t, 0) * tax_rate
    NOPAT_t   = EBIT_t - taxes_t
    capex_t   = revenue_t * capex_pct_t
    UFCF_t    = NOPAT_t + D&A_t - capex_t - dNWC_t

Tier-2 model (Grupo Mateus style): revenue built from PHYSICAL drivers per
segment — units x revenue/unit (stores x revenue/store, reps x revenue/rep) —
declared in the assumptions YAML. Margins, capex, and working capital still
come from the percentage drivers; only the revenue line switches source.

Anchored on the company's TTM revenue; every driver comes from the
assumptions layer (analyst YAML or derived anchors).
"""

from __future__ import annotations

import pandas as pd

from src.modeling.valuation_assumptions import ScenarioAssumptions
from src.modeling.working_capital import project_nwc


def _per_year(value, horizon: int, scenario_name: str) -> list[float]:
    """Resolve a segment driver: scalar, per-year list, or {bear/base/bull} map."""
    if isinstance(value, dict):
        value = value.get(scenario_name, value.get("base", 0.0))
    if isinstance(value, (int, float)):
        return [float(value)] * horizon
    out = [float(v) for v in value]
    if len(out) < horizon:                      # pad with the last value
        out = out + [out[-1]] * (horizon - len(out))
    return out[:horizon]


def segment_revenue_path(
    segments: list[dict],
    horizon: int,
    scenario_name: str = "base",
) -> list[float]:
    """Total revenue per year from units x revenue-per-unit segment builds.

    Each segment: ``{name, units, revenue_per_unit, unit_adds, rpu_growth}``.
    ``unit_adds`` / ``rpu_growth`` accept a scalar, a per-year list, or a
    ``{bear:, base:, bull:}`` map (Grupo Mateus: 10/25/50 new stores a year).
    """
    totals = [0.0] * horizon
    for seg in segments:
        units = float(seg["units"])
        rpu = float(seg["revenue_per_unit"])
        adds = _per_year(seg.get("unit_adds", 0.0), horizon, scenario_name)
        growth = _per_year(seg.get("rpu_growth", 0.0), horizon, scenario_name)
        for t in range(horizon):
            units += adds[t]
            rpu *= (1.0 + growth[t])
            totals[t] += units * rpu
    return totals


def build_forecast(
    revenue_ttm: float,
    scenario: ScenarioAssumptions,
    cogs_pct: float | None,
    nwc_now: float | None,
    segments: list[dict] | None = None,
) -> pd.DataFrame:
    """Project the P&L-to-UFCF waterfall for one scenario."""
    if revenue_ttm is None or pd.isna(revenue_ttm) or revenue_ttm <= 0:
        raise ValueError("Forecast requires a positive TTM revenue anchor.")

    n = len(scenario.revenue_growth)
    if segments:
        revenue = segment_revenue_path(segments, n, scenario.name)
        growth_path = [revenue[0] / float(revenue_ttm) - 1.0] + [
            revenue[t] / revenue[t - 1] - 1.0 for t in range(1, n)
        ]
    else:
        revenue = []
        level = float(revenue_ttm)
        for t in range(n):
            level = level * (1.0 + scenario.revenue_growth[t])
            revenue.append(level)
        growth_path = list(scenario.revenue_growth)

    nwc = project_nwc(revenue, scenario, cogs_pct, nwc_now)

    rows = []
    for t in range(n):
        rev = revenue[t]
        ebitda = rev * scenario.ebitda_margin[t]
        d_and_a = rev * scenario.d_and_a_pct[t]
        ebit = ebitda - d_and_a
        taxes = max(ebit, 0.0) * scenario.tax_rate
        nopat = ebit - taxes
        capex = rev * scenario.capex_pct[t]
        delta_nwc = float(nwc.loc[t, "delta_nwc"])
        ufcf = nopat + d_and_a - capex - delta_nwc
        rows.append({
            "year": t + 1,
            "revenue": rev,
            "revenue_growth": growth_path[t],
            "ebitda": ebitda,
            "ebitda_margin": scenario.ebitda_margin[t],
            "d_and_a": d_and_a,
            "ebit": ebit,
            "taxes": taxes,
            "nopat": nopat,
            "capex": capex,
            "nwc": float(nwc.loc[t, "nwc"]),
            "delta_nwc": delta_nwc,
            "ufcf": ufcf,
        })
    return pd.DataFrame(rows)
