"""Capital structure and debt capacity - the credit-side read on every name.

Answers the sponsor/lender questions: how levered is it today, how much MORE
debt does the business support at standard leverage multiples, and how much
covenant headroom exists. Financial institutions are excluded from EBITDA-based
capacity math (not meaningful) and routed to their own metric set.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CAPACITY_TURNS = (2.0, 3.0, 4.0)
COVENANT_LEVERAGE = 4.0        # standard senior-leverage covenant proxy
COVENANT_COVERAGE = 2.0        # minimum EBITDA / interest


@dataclass
class CapitalStructure:
    applicable: bool
    gross_debt: float | None = None
    cash: float | None = None
    net_debt: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    ebitda_ttm: float | None = None
    interest_expense: float | None = None
    net_leverage: float | None = None
    gross_leverage: float | None = None
    interest_coverage: float | None = None
    cash_pct_debt: float | None = None
    net_debt_pct_ev: float | None = None
    capacity: dict = field(default_factory=dict)      # turns -> net debt supported
    incremental: dict = field(default_factory=dict)   # turns -> incremental vs today
    leverage_headroom: float | None = None            # turns to covenant
    coverage_headroom: float | None = None            # x above coverage floor
    sponsor_capacity: float | None = None             # debt at 4.0x, floored at 0 incr
    ltv: float | None = None                          # net debt / EV
    warnings: list[str] = field(default_factory=list)


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


def build_capital_structure(row: pd.Series) -> CapitalStructure:
    warnings: list[str] = []
    if str(row.get("business_model")) in ("financial", "insurer"):
        return CapitalStructure(
            applicable=False,
            warnings=["Financial institution: EBITDA debt capacity is not meaningful - "
                      "read funding on deposits/loans, equity ratios, and coverage of "
                      "provisions instead (see Financials Valuation)."])

    debt = _clean(row.get("total_debt"))
    cash = _clean(row.get("cash_st_invest"))
    if cash is None:
        cash = _clean(row.get("cash"))
    net_debt = _clean(row.get("net_debt"))
    if net_debt is None and debt is not None and cash is not None:
        net_debt = debt - cash
    ebitda = _clean(row.get("ebitda_ttm"))
    interest = _clean(row.get("interest_expense_ttm", row.get("interest_expense")))
    mcap = _clean(row.get("market_cap"))
    ev = _clean(row.get("enterprise_value"))

    cs = CapitalStructure(
        applicable=True, gross_debt=debt, cash=cash, net_debt=net_debt,
        market_cap=mcap, enterprise_value=ev, ebitda_ttm=ebitda,
        interest_expense=interest, warnings=warnings)

    if ebitda is None or ebitda <= 0:
        warnings.append("EBITDA missing or negative - leverage and capacity not meaningful.")
        return cs

    if net_debt is not None:
        cs.net_leverage = net_debt / ebitda
    if debt is not None:
        cs.gross_leverage = debt / ebitda
        if cash is not None and debt > 0:
            cs.cash_pct_debt = cash / debt
    if interest is not None and interest > 0:
        cs.interest_coverage = ebitda / interest
        cs.coverage_headroom = cs.interest_coverage - COVENANT_COVERAGE
    else:
        warnings.append("Interest expense missing/zero - coverage headroom not computable.")
    if ev and ev > 0 and net_debt is not None:
        cs.net_debt_pct_ev = net_debt / ev
        cs.ltv = net_debt / ev

    for turns in CAPACITY_TURNS:
        total = turns * ebitda
        cs.capacity[turns] = total
        cs.incremental[turns] = total - (net_debt if net_debt is not None else 0.0)
    if cs.net_leverage is not None:
        cs.leverage_headroom = COVENANT_LEVERAGE - cs.net_leverage
    cs.sponsor_capacity = max(cs.incremental.get(4.0, 0.0), 0.0)

    if net_debt is not None and net_debt < 0:
        warnings.append("Net cash position - 'debt capacity' is the full amount at each multiple.")
    return cs


def ev_bridge(row: pd.Series) -> dict:
    """Current EV bridge: market cap + debt + minority + preferred - cash.

    ``IQ_TOTAL_DEBT`` already includes finance/capital lease obligations in the
    current export, so adding the separately exported lease field would double
    count them.

    Cash basis: CapIQ TEV subtracts total cash & short-term investments, so
    ``cash_st_invest`` is preferred when exported; plain cash & equivalents is
    the fallback (and understates the subtraction for big ST-portfolio names).

    Returns components (None-safe), calculated/reported EV, gap %, and whether
    the bridge is partial (minority/preferred not exported)."""
    def g(k):
        return _clean(row.get(k))

    mcap, debt = g("market_cap"), g("total_debt")
    cash_sti, cash_only = g("cash_st_invest"), g("cash")
    cash = cash_sti if cash_sti is not None else cash_only
    minority, preferred = g("minority_interest"), g("preferred_equity")
    reported = g("enterprise_value")
    partial = minority is None or preferred is None
    if mcap is None or debt is None or cash is None:
        return {"available": False, "partial": True}
    calc = mcap + debt + (minority or 0.0) + (preferred or 0.0) - cash
    gap = (calc / reported - 1.0) if reported and reported > 0 else None
    return {
        "available": True, "partial": partial,
        "market_cap": mcap, "total_debt": debt, "cash": cash,
        "cash_basis": "cash & ST investments" if cash_sti is not None else "cash & equivalents only",
        "minority_interest": minority or 0.0, "preferred_equity": preferred or 0.0,
        "lease_liabilities": None,
        "calculated_ev": calc, "reported_ev": reported, "gap": gap,
        "mismatch": gap is not None and abs(gap) > 0.05,
    }


def leverage_history(df: pd.DataFrame, company_id: str) -> pd.DataFrame:
    """Net debt and leverage per quarter (for trend charts)."""
    hist = df[df["company_id"] == company_id].sort_values("period")
    cols = ["period", "net_debt", "net_debt_to_ebitda_ttm", "interest_coverage_ttm"]
    keep = [c for c in cols if c in hist.columns]
    return hist[keep].copy()
