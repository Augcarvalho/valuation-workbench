"""LBO engine: sponsor returns on top of the operating forecast.

PE does not buy screen-price upside - it buys levered IRR and MOIC. This module
reuses the same driver-based forecast that powers the DCF and answers the
sponsor questions:

- **Entry**: EV = entry multiple x LTM EBITDA (negotiated, not market price),
  funded with ``debt_pct`` leverage; sponsor equity check = EV - debt
  (+ transaction fees on EV).
- **Debt schedule**: each year, free cash flow after cash interest sweeps
  outstanding debt (100% cash sweep, floor at zero) - the simple-LBO standard.
- **Exit**: exit multiple x year-N EBITDA -> equity to sponsor = exit EV -
  remaining net debt.
- **Returns**: MOIC and IRR on the equity check.
- **Value-creation bridge**: equity gain split into EBITDA growth, multiple
  change, and deleveraging (cash-flow paydown), the standard PE attribution.

Defaults are deliberately conservative and disclosed: entry at the CURRENT
EV/EBITDA (no discount negotiated), exit at entry (no re-rating), 50% debt,
cost of debt from the WACC build. Every input is overridable in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LboResult:
    entry_multiple: float
    exit_multiple: float
    entry_ebitda: float
    exit_ebitda: float
    entry_ev: float
    exit_ev: float
    entry_debt: float
    exit_debt: float
    equity_check: float
    exit_equity: float
    moic: float | None
    irr: float | None
    debt_pct: float
    cost_of_debt: float
    horizon: int
    schedule: pd.DataFrame = field(default_factory=pd.DataFrame)
    bridge: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    valid: bool = True


def run_lbo(
    forecast: pd.DataFrame,
    entry_ebitda: float,
    entry_multiple: float,
    exit_multiple: float | None = None,
    debt_pct: float = 0.5,
    cost_of_debt: float = 0.08,
    fees_pct_ev: float = 0.02,
    min_cash_sweep: float = 1.0,
) -> LboResult:
    """Simple-LBO on an existing operating forecast (base scenario, usually).

    ``forecast`` must carry ``ebitda`` and ``ufcf`` columns (the DCF forecast).
    UFCF proxies pre-interest free cash flow; cash interest is deducted here.
    """
    notes: list[str] = []
    if entry_ebitda is None or entry_ebitda <= 0:
        return LboResult(entry_multiple, exit_multiple or entry_multiple, entry_ebitda or 0.0,
                         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, None,
                         debt_pct, cost_of_debt, 0, notes=["entry EBITDA not positive - LBO not applicable"],
                         valid=False)
    if exit_multiple is None:
        exit_multiple = entry_multiple
        notes.append("exit at entry multiple (no re-rating assumed)")

    n = len(forecast)
    entry_ev = entry_multiple * float(entry_ebitda)
    entry_debt = debt_pct * entry_ev
    fees = fees_pct_ev * entry_ev
    equity_check = entry_ev - entry_debt + fees

    debt = entry_debt
    rows = []
    for t in range(n):
        ebitda = float(forecast["ebitda"].iloc[t])
        ufcf = float(forecast["ufcf"].iloc[t])
        interest = debt * cost_of_debt
        fcf_after_interest = ufcf - interest
        paydown = max(min(fcf_after_interest * min_cash_sweep, debt), 0.0)
        debt = debt - paydown
        rows.append({
            "year": t + 1, "ebitda": ebitda, "ufcf": ufcf, "cash_interest": interest,
            "fcf_after_interest": fcf_after_interest, "debt_paydown": paydown,
            "debt_end": debt, "leverage": debt / ebitda if ebitda > 0 else np.nan,
        })
    schedule = pd.DataFrame(rows)

    exit_ebitda = float(forecast["ebitda"].iloc[-1])
    exit_ev = exit_multiple * exit_ebitda
    exit_equity = exit_ev - debt

    moic = exit_equity / equity_check if equity_check > 0 and exit_equity > 0 else None
    # 100% cash sweep means no interim distributions -> IRR is the exact CAGR
    # of the single equity outflow into the single exit inflow.
    irr = (moic ** (1.0 / n) - 1.0) if moic is not None and n > 0 else None
    if exit_equity <= 0:
        notes.append("exit equity non-positive: debt exceeds exit EV under these assumptions")

    # Value-creation bridge (standard PE attribution):
    #   EBITDA growth  = (exit EBITDA - entry EBITDA) x entry multiple
    #   Multiple change = (exit mult - entry mult) x exit EBITDA
    #   Deleveraging    = entry debt - exit debt (cash-flow paydown)
    #   minus fees (entry friction). Sums exactly to (exit equity - equity check).
    bridge = {
        "equity_check": equity_check,
        "ebitda_growth": (exit_ebitda - entry_ebitda) * entry_multiple,
        "multiple_change": (exit_multiple - entry_multiple) * exit_ebitda,
        "deleveraging": entry_debt - debt,
        "fees": -fees,
        "exit_equity": exit_equity,
    }

    return LboResult(
        entry_multiple=entry_multiple, exit_multiple=exit_multiple,
        entry_ebitda=float(entry_ebitda), exit_ebitda=exit_ebitda,
        entry_ev=entry_ev, exit_ev=exit_ev,
        entry_debt=entry_debt, exit_debt=debt,
        equity_check=equity_check, exit_equity=exit_equity,
        moic=moic, irr=irr, debt_pct=debt_pct, cost_of_debt=cost_of_debt,
        horizon=n, schedule=schedule, bridge=bridge, notes=notes,
    )


def lbo_from_case(case, entry_multiple: float | None = None,
                  exit_multiple: float | None = None,
                  debt_pct: float = 0.5,
                  cost_of_debt: float | None = None) -> LboResult:
    """Build the LBO off a valuation case's base forecast + market anchors."""
    row = case.assessment.row
    entry_ebitda = row.get("ebitda_ttm")
    entry_ebitda = float(entry_ebitda) if pd.notna(entry_ebitda) else None
    if entry_multiple is None:
        own = row.get("ev_to_ebitda_ttm")
        entry_multiple = float(own) if pd.notna(own) and own > 0 else case.exit_multiple
    if cost_of_debt is None:
        kd = getattr(case.wacc, "cost_of_debt_pretax", None)
        cost_of_debt = float(kd) if kd else 0.08
    return run_lbo(
        forecast=case.base.forecast,
        entry_ebitda=entry_ebitda,
        entry_multiple=entry_multiple,
        exit_multiple=exit_multiple,
        debt_pct=debt_pct,
        cost_of_debt=cost_of_debt,
    )
