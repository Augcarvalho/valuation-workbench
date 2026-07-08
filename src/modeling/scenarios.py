"""Scenario engine: bear / base / bull cases, IRR/MOIC, and implied expectations.

Model (deliberately simple and stated, sponsor-style):

- Operating companies: exit EV = exit-year EBITDA x exit multiple, where exit
  EBITDA = revenue_ttm x (1+CAGR)^t x exit margin. Exit equity = exit EV minus
  today's net debt (held constant; interim FCF is ignored, which is
  conservative for cash-generative names).
- Financial institutions: the EBITDA/EV framework is not meaningful, so the
  case runs on earnings — exit equity = exit-year net income x exit P/E.

Returns are measured against today's market cap:
MOIC = exit equity / market cap; IRR = MOIC^(1/t) - 1.

Cases come from the thesis YAML when present; otherwise defensible defaults
are derived from the company's own current growth, margin, and multiple.

Implied expectations inverts the same math: given today's EV, a fair exit
multiple (peer median), and a required return, what growth must the company
deliver? That is "what is priced in".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ScenarioCase:
    name: str                      # bear | base | bull
    revenue_cagr: float
    exit_margin: float             # EBITDA margin (operating) or NI margin (financial)
    exit_multiple: float           # EV/EBITDA (operating) or P/E (financial)
    horizon_years: int = 3
    source: str = "derived"        # derived | thesis


@dataclass
class ScenarioResult:
    case: ScenarioCase
    exit_revenue: float | None = None
    exit_profit: float | None = None
    exit_value: float | None = None       # exit EV (operating) or exit equity (financial)
    exit_equity: float | None = None
    moic: float | None = None
    irr: float | None = None
    implied_share_price: float | None = None
    valid: bool = False
    note: str = ""


def _is_financial(row: pd.Series) -> bool:
    return str(row.get("business_model", "operating")).lower() == "financial"


def _current_margin(row: pd.Series) -> float | None:
    metric = "net_income_margin_ttm" if _is_financial(row) else "ebitda_margin_ttm"
    value = row.get(metric)
    return None if pd.isna(value) else float(value)


def _current_multiple(row: pd.Series) -> float | None:
    metric = "pe_ttm" if _is_financial(row) else "ev_to_ebitda_ttm"
    value = row.get(metric)
    return None if pd.isna(value) or value <= 0 else float(value)


def derive_default_cases(row: pd.Series, horizon_years: int = 3) -> list[ScenarioCase]:
    """Defensible default cases anchored on the company's own current profile."""
    growth = row.get("revenue_yoy_growth")
    growth = 0.04 if pd.isna(growth) else float(np.clip(growth, -0.10, 0.25))
    margin = _current_margin(row)
    margin = 0.15 if margin is None else float(np.clip(margin, 0.02, 0.70))
    multiple = _current_multiple(row)
    multiple = 10.0 if multiple is None else float(np.clip(multiple, 4.0, 30.0))

    return [
        ScenarioCase("bear", round(max(growth - 0.08, -0.10), 3), round(max(margin - 0.03, 0.01), 3),
                     round(multiple * 0.75, 1), horizon_years),
        ScenarioCase("base", round(growth, 3), round(margin, 3), round(multiple, 1), horizon_years),
        ScenarioCase("bull", round(min(growth + 0.06, 0.35), 3), round(min(margin + 0.02, 0.75), 3),
                     round(multiple * 1.2, 1), horizon_years),
    ]


def cases_from_thesis(row: pd.Series, thesis_scenarios: dict | None, horizon_years: int = 3) -> list[ScenarioCase]:
    """Thesis-YAML cases where present, defaults for whichever are missing."""
    defaults = {c.name: c for c in derive_default_cases(row, horizon_years)}
    if not thesis_scenarios:
        return list(defaults.values())
    out = []
    for name in ("bear", "base", "bull"):
        raw = thesis_scenarios.get(name)
        if isinstance(raw, dict):
            base = defaults[name]
            out.append(ScenarioCase(
                name=name,
                revenue_cagr=float(raw.get("revenue_cagr", base.revenue_cagr)),
                exit_margin=float(raw.get("exit_margin", raw.get("exit_ebitda_margin", base.exit_margin))),
                exit_multiple=float(raw.get("exit_multiple", base.exit_multiple)),
                horizon_years=int(raw.get("horizon_years", base.horizon_years)),
                source="thesis",
            ))
        else:
            out.append(defaults[name])
    return out


def run_case(row: pd.Series, case: ScenarioCase) -> ScenarioResult:
    result = ScenarioResult(case=case)
    revenue = row.get("revenue_ttm")
    market_cap = row.get("market_cap")
    if pd.isna(revenue) or revenue <= 0 or pd.isna(market_cap) or market_cap <= 0:
        result.note = "Missing revenue or market cap."
        return result

    t = max(int(case.horizon_years), 1)
    exit_revenue = float(revenue) * (1 + case.revenue_cagr) ** t
    exit_profit = exit_revenue * case.exit_margin
    if exit_profit <= 0:
        result.note = "Exit profit non-positive under this case."
        result.exit_revenue = exit_revenue
        result.exit_profit = exit_profit
        return result

    if _is_financial(row):
        exit_equity = exit_profit * case.exit_multiple
        exit_value = exit_equity
    else:
        net_debt = row.get("net_debt")
        net_debt = 0.0 if pd.isna(net_debt) else float(net_debt)
        exit_value = exit_profit * case.exit_multiple
        exit_equity = exit_value - net_debt

    if exit_equity <= 0:
        result.note = "Exit equity wiped out by net debt under this case."
        result.exit_revenue = exit_revenue
        result.exit_profit = exit_profit
        result.exit_value = exit_value
        result.exit_equity = exit_equity
        return result

    moic = exit_equity / float(market_cap)
    irr = moic ** (1 / t) - 1
    price = row.get("share_price")

    result.exit_revenue = exit_revenue
    result.exit_profit = exit_profit
    result.exit_value = exit_value
    result.exit_equity = exit_equity
    result.moic = moic
    result.irr = irr
    result.implied_share_price = float(price) * moic if pd.notna(price) and price > 0 else None
    result.valid = True
    return result


def run_cases(row: pd.Series, thesis_scenarios: dict | None = None, horizon_years: int = 3) -> list[ScenarioResult]:
    return [run_case(row, case) for case in cases_from_thesis(row, thesis_scenarios, horizon_years)]


def sensitivity_grid(
    row: pd.Series,
    base_case: ScenarioCase,
    growth_steps: list[float] | None = None,
    multiple_steps: list[float] | None = None,
) -> pd.DataFrame:
    """IRR grid over revenue CAGR (rows) x exit multiple (columns)."""
    if growth_steps is None:
        g = base_case.revenue_cagr
        growth_steps = [round(g + d, 3) for d in (-0.08, -0.04, 0.0, 0.04, 0.08)]
    if multiple_steps is None:
        m = base_case.exit_multiple
        multiple_steps = [round(m * f, 1) for f in (0.7, 0.85, 1.0, 1.15, 1.3)]

    grid = {}
    for mult in multiple_steps:
        column = []
        for growth in growth_steps:
            case = ScenarioCase("grid", growth, base_case.exit_margin, mult, base_case.horizon_years)
            res = run_case(row, case)
            column.append(res.irr if res.valid else np.nan)
        grid[f"{mult:g}x"] = column
    index = [f"{g:+.0%}" for g in growth_steps]
    return pd.DataFrame(grid, index=index)


def margin_sensitivity_grid(
    row: pd.Series,
    base_case: ScenarioCase,
    margin_steps: list[float] | None = None,
    multiple_steps: list[float] | None = None,
) -> pd.DataFrame:
    """IRR grid over exit margin (rows) x exit multiple (columns)."""
    if margin_steps is None:
        m = base_case.exit_margin
        margin_steps = [round(max(m + d, 0.01), 3) for d in (-0.04, -0.02, 0.0, 0.02, 0.04)]
    if multiple_steps is None:
        x = base_case.exit_multiple
        multiple_steps = [round(x * f, 1) for f in (0.7, 0.85, 1.0, 1.15, 1.3)]

    grid = {}
    for mult in multiple_steps:
        column = []
        for margin in margin_steps:
            case = ScenarioCase("grid", base_case.revenue_cagr, margin, mult, base_case.horizon_years)
            res = run_case(row, case)
            column.append(res.irr if res.valid else np.nan)
        grid[f"{mult:g}x"] = column
    index = [f"{m:.0%}" for m in margin_steps]
    return pd.DataFrame(grid, index=index)


def implied_expectations(
    row: pd.Series,
    fair_exit_multiple: float | None,
    horizon_years: int = 3,
    required_returns: tuple[float, ...] = (0.08, 0.12, 0.15),
) -> dict:
    """What growth is priced in?

    Solves, for each required return r: today's value compounding at r must be
    met by exit-year profit x fair multiple. Reported as the implied profit
    CAGR (EBITDA for operating companies, net income for financials).
    """
    financial = _is_financial(row)
    profit_now = row.get("net_income_ttm" if financial else "ebitda_ttm")
    value_now = row.get("market_cap" if financial else "enterprise_value")
    out = {
        "available": False,
        "metric": "net income" if financial else "EBITDA",
        "multiple_name": "P/E" if financial else "EV/EBITDA",
        "fair_exit_multiple": fair_exit_multiple,
        "horizon_years": horizon_years,
        "required": [],
    }
    if (
        fair_exit_multiple is None or pd.isna(fair_exit_multiple) or fair_exit_multiple <= 0
        or pd.isna(profit_now) or profit_now <= 0 or pd.isna(value_now) or value_now <= 0
    ):
        return out

    for r in required_returns:
        target_value = float(value_now) * (1 + r) ** horizon_years
        required_exit_profit = target_value / float(fair_exit_multiple)
        implied_cagr = (required_exit_profit / float(profit_now)) ** (1 / horizon_years) - 1
        out["required"].append({"return": r, "implied_profit_cagr": implied_cagr})
    out["available"] = True
    return out
