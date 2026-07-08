"""Working-capital schedule: DSO / DIH / DPO days -> NWC -> change in NWC.

Mechanics mirror the Grupo Mateus "Working Cap." tab:

    AR_t        = DSO_t * revenue_t / 365
    Inventory_t = DIH_t * COGS_t   / 365
    AP_t        = DPO_t * COGS_t   / 365
    NWC_t       = AR_t + Inventory_t - AP_t
    dNWC_t      = NWC_t - NWC_{t-1}     (year 1 vs the current actual NWC)

When receivables/inventory/payables data is not available (public demo), the
schedule degrades to NWC as a % of revenue — same delta logic, cruder anchor.
"""

from __future__ import annotations

import pandas as pd

from src.modeling.valuation_assumptions import ScenarioAssumptions


def nwc_from_days(revenue: float, cogs: float, dso: float, dih: float, dpo: float) -> float:
    ar = dso * revenue / 365.0
    inventory = dih * cogs / 365.0
    ap = dpo * cogs / 365.0
    return ar + inventory - ap


def project_nwc(
    revenue: list[float],
    scenario: ScenarioAssumptions,
    cogs_pct: float | None,
    nwc_now: float | None,
) -> pd.DataFrame:
    """Per-year NWC and delta-NWC for a projected revenue path.

    ``nwc_now`` is the company's current NWC level (the year-0 base for the
    first delta). If unknown, year-1 NWC level is used as the base, i.e. the
    first-year delta is zero — disclosed by the caller.
    """
    n = len(revenue)
    rows = []
    if scenario.nwc_mode == "days" and cogs_pct is not None:
        for t in range(n):
            cogs = revenue[t] * cogs_pct
            level = nwc_from_days(revenue[t], cogs, scenario.dso[t], scenario.dih[t], scenario.dpo[t])
            rows.append(level)
    else:
        pct_path = scenario.nwc_pct_revenue or [0.0] * n
        for t in range(n):
            rows.append(revenue[t] * pct_path[t])

    base = nwc_now if nwc_now is not None else rows[0]
    deltas = []
    prev = base
    for level in rows:
        deltas.append(level - prev)
        prev = level

    return pd.DataFrame({"nwc": rows, "delta_nwc": deltas})
