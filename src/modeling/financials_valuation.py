"""Financial-institution valuation: the model banks actually get valued on.

EBITDA DCF is correctly blocked for ``business_model == financial``. This
module provides the replacement: P/E and P/B (or P/TBV when tangible common
equity is exported), the justified P/B anchor, and a residual-income (excess
return) valuation:

    justified P/B = (ROE - g) / (COE - g)
    equity value  = book value + sum PV[(ROE - COE) x BV_{t-1}]
                    + PV of terminal excess-return perpetuity

Guardrails everywhere: negative book value, negative earnings, COE <= g, and
missing tangible equity (P/B on total equity is labeled as such, never sold
as P/TBV).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HORIZON_YEARS = 5


@dataclass
class FinancialsValuation:
    applicable: bool
    market_cap: float | None = None
    net_income_ttm: float | None = None
    book_value: float | None = None
    book_source: str = ""              # tangible_common_equity | book_value | total_equity
    roe: float | None = None
    cost_of_equity: float | None = None
    growth: float | None = None
    pe: float | None = None
    pb: float | None = None
    pb_label: str = "P/B"              # P/TBV when tangible equity available
    justified_pb: float | None = None
    excess_return_value: float | None = None
    excess_return_upside: float | None = None
    valid: bool = True
    warnings: list[str] = field(default_factory=list)


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


def justified_pb(roe: float, coe: float, growth: float) -> float | None:
    if coe <= growth:
        return None
    return (roe - growth) / (coe - growth)


def excess_return_value(book: float, roe: float, coe: float, growth: float,
                        horizon: int = HORIZON_YEARS) -> float | None:
    """Book value + PV of excess returns over an explicit horizon + terminal.

    Excess return_t = (ROE - COE) x BV_{t-1}; book compounds at the retention-
    implied growth g. Terminal = perpetuity of the year-N excess return grown
    at g, valid only when COE > g."""
    if coe <= growth or book <= 0:
        return None
    value = book
    bv = book
    for t in range(1, horizon + 1):
        er = (roe - coe) * bv
        value += er / (1.0 + coe) ** t
        bv *= (1.0 + growth)
    terminal_er = (roe - coe) * bv * (1.0 + growth)
    terminal = terminal_er / (coe - growth)
    value += terminal / (1.0 + coe) ** horizon
    return value


def build_financials_valuation(row: pd.Series, cost_of_equity: float,
                               growth: float | None = None) -> FinancialsValuation:
    if str(row.get("business_model")) != "financial":
        return FinancialsValuation(applicable=False,
                                   warnings=["Not a financial-business-model company."])

    warnings: list[str] = []
    mcap = _clean(row.get("market_cap"))
    ni = _clean(row.get("net_income_ttm"))

    book, source = None, ""
    for candidate, label in [("tangible_common_equity", "tangible_common_equity"),
                             ("book_value", "book_value"),
                             ("total_equity", "total_equity")]:
        v = _clean(row.get(candidate))
        if v is not None:
            book, source = v, label
            break
    if source == "total_equity":
        warnings.append("Tangible common equity not exported - using TOTAL equity; "
                        "multiple below is P/B, not P/TBV.")
    elif source == "":
        warnings.append("No book value available - P/B framework not computable.")

    if growth is None:
        growth = min(max(cost_of_equity - 0.06, 0.02), 0.05)   # conservative anchored g
        warnings.append(f"Growth defaulted to {growth:.1%} (COE-anchored); set via assumptions "
                        f"file for a formal view.")

    out = FinancialsValuation(
        applicable=True, market_cap=mcap, net_income_ttm=ni,
        book_value=book, book_source=source, cost_of_equity=cost_of_equity,
        growth=growth, warnings=warnings,
        pb_label="P/TBV" if source == "tangible_common_equity" else "P/B")

    if ni is not None and mcap and mcap > 0:
        out.pe = mcap / ni if ni > 0 else None
        if ni <= 0:
            warnings.append("Negative TTM earnings - P/E and ROE not meaningful.")
    if book is not None and book <= 0:
        warnings.append("Negative book value - P/B framework breaks down; equity-value work "
                        "requires a recapitalization lens.")
        out.valid = False
        return out
    if book and mcap and mcap > 0:
        out.pb = mcap / book
    if book and ni is not None and ni > 0:
        out.roe = ni / book
        if out.roe > 0.40:
            warnings.append(f"ROE {out.roe:.0%} is extreme - check equity base (buybacks can "
                            f"shrink book and inflate ROE).")

    if out.roe is not None and out.roe > 0:
        if cost_of_equity <= growth:
            warnings.append("COE <= growth - justified P/B and residual income undefined.")
        else:
            out.justified_pb = justified_pb(out.roe, cost_of_equity, growth)
            erv = excess_return_value(book, out.roe, cost_of_equity, growth)
            out.excess_return_value = erv
            if erv is not None and mcap and mcap > 0:
                out.excess_return_upside = erv / mcap - 1.0
    else:
        out.valid = out.valid and False
    return out
