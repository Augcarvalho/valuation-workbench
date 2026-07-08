"""DCF engine: UFCF discounting, dual terminal value, equity bridge, target price.

Conventions (stated, sponsor/IB-style — mirrors the Grupo Mateus model):

- **Mid-year discounting** of interim cash flows: DF_t = (1+w)^-(t-0.5).
- **Terminal value both ways**: exit multiple (terminal EBITDA x multiple) and
  Gordon perpetuity (UFCF_N x (1+g) / (w-g)); both discounted at (1+w)^-N.
  Cross-checks reported: the perpetuity growth implied by the exit multiple,
  and the exit multiple implied by the perpetuity — the two methods should
  tell the same story or the gap is itself a finding.
- **Primary EV** = exit-multiple method (comps-anchored), perpetuity shown
  alongside.
- **Equity bridge**: EV - net debt - minority interest - preferred = implied
  equity. Upside = implied equity / market cap - 1; target price = current
  price x (1 + upside). Working through equity value rather than dividing by
  a share count keeps the math unit-safe across data sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.modeling.forecast import build_forecast
from src.modeling.valuation_assumptions import ScenarioAssumptions, ValuationAssumptions


@dataclass
class DcfResult:
    scenario: str
    forecast: pd.DataFrame
    wacc: float
    exit_multiple: float
    perpetuity_growth: float
    pv_explicit: float
    terminal_value_exit: float
    terminal_value_perp: float
    pv_terminal_exit: float
    pv_terminal_perp: float
    enterprise_value: float            # primary: exit-multiple method
    enterprise_value_perp: float
    implied_terminal_growth: float | None   # implied by the exit multiple
    implied_exit_multiple: float | None     # implied by the perpetuity
    terminal_pct_of_ev: float
    net_debt: float
    minority_interest: float
    preferred_equity: float
    implied_equity: float
    market_cap: float | None
    upside: float | None
    current_price: float | None
    target_price: float | None
    valid: bool = True
    notes: list[str] = field(default_factory=list)


def _clean(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _discount_factors(wacc: float, n: int) -> np.ndarray:
    periods = np.arange(1, n + 1) - 0.5
    return (1.0 + wacc) ** (-periods)


def implied_perpetuity_growth(tv: float, ufcf_n: float, wacc: float) -> float | None:
    """Solve TV = UFCF_N (1+g)/(w-g) for g."""
    if tv <= 0 or ufcf_n <= 0:
        return None
    return (wacc * tv - ufcf_n) / (tv + ufcf_n)


def run_dcf(
    row: pd.Series,
    scenario: ScenarioAssumptions,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
) -> DcfResult:
    notes: list[str] = []
    anchors = assumptions.anchors

    forecast = build_forecast(
        revenue_ttm=_clean(row.get("revenue_ttm")),
        scenario=scenario,
        cogs_pct=anchors.get("cogs_pct"),
        nwc_now=_clean(row.get("working_capital")),
        segments=getattr(assumptions, "segments", None),
    )
    if getattr(assumptions, "segments", None):
        notes.append(f"revenue built from {len(assumptions.segments)} operational "
                     f"segment(s): units x revenue/unit")
    if _clean(row.get("working_capital")) is None:
        notes.append("current NWC unknown; first-year working-capital delta assumed zero")

    n = len(forecast)
    ufcf = forecast["ufcf"].to_numpy(dtype=float)
    dfs = _discount_factors(wacc, n)
    pv_explicit = float((ufcf * dfs).sum())

    terminal_ebitda = float(forecast["ebitda"].iloc[-1])
    ufcf_n = float(ufcf[-1])
    g = assumptions.perpetuity_growth

    tv_exit = terminal_ebitda * exit_multiple
    if wacc <= g:
        tv_perp = float("nan")
        notes.append(f"perpetuity invalid: WACC {wacc:.1%} <= growth {g:.1%}")
    else:
        tv_perp = ufcf_n * (1.0 + g) / (wacc - g) if ufcf_n > 0 else float("nan")
        if ufcf_n <= 0:
            notes.append("terminal-year UFCF non-positive; perpetuity method not meaningful")

    df_n = (1.0 + wacc) ** (-n)
    pv_tv_exit = tv_exit * df_n
    pv_tv_perp = tv_perp * df_n if not np.isnan(tv_perp) else float("nan")

    ev_exit = pv_explicit + pv_tv_exit
    ev_perp = pv_explicit + pv_tv_perp if not np.isnan(pv_tv_perp) else float("nan")

    implied_g = implied_perpetuity_growth(tv_exit, ufcf_n, wacc)
    implied_mult = (tv_perp / terminal_ebitda) if (not np.isnan(tv_perp) and terminal_ebitda > 0) else None

    # Equity bridge.
    net_debt = _clean(row.get("net_debt"))
    if net_debt is None:
        debt, cash = _clean(row.get("total_debt")), _clean(row.get("cash"))
        net_debt = (debt or 0.0) - (cash or 0.0)
        notes.append("net debt derived from total debt minus cash")
    minority = _clean(row.get("minority_interest")) or 0.0
    preferred = _clean(row.get("preferred_equity")) or 0.0
    implied_equity = ev_exit - net_debt - minority - preferred

    market_cap = _clean(row.get("market_cap"))
    price = _clean(row.get("share_price"))
    upside = None
    target = None
    valid = implied_equity > 0
    if not valid:
        notes.append("implied equity non-positive under this scenario")
    if market_cap and market_cap > 0 and valid:
        upside = implied_equity / market_cap - 1.0
        if price and price > 0:
            target = price * (1.0 + upside)
    elif market_cap is None:
        notes.append("market cap missing; upside not computable")

    terminal_pct = pv_tv_exit / ev_exit if ev_exit > 0 else float("nan")

    return DcfResult(
        scenario=scenario.name,
        forecast=forecast,
        wacc=wacc,
        exit_multiple=exit_multiple,
        perpetuity_growth=g,
        pv_explicit=pv_explicit,
        terminal_value_exit=tv_exit,
        terminal_value_perp=tv_perp,
        pv_terminal_exit=pv_tv_exit,
        pv_terminal_perp=pv_tv_perp,
        enterprise_value=ev_exit,
        enterprise_value_perp=ev_perp,
        implied_terminal_growth=implied_g,
        implied_exit_multiple=implied_mult,
        terminal_pct_of_ev=terminal_pct,
        net_debt=net_debt,
        minority_interest=minority,
        preferred_equity=preferred,
        implied_equity=implied_equity,
        market_cap=market_cap,
        upside=upside,
        current_price=price,
        target_price=target,
        valid=valid,
        notes=notes,
    )


def run_all_scenarios(
    row: pd.Series,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
) -> dict[str, DcfResult]:
    return {
        name: run_dcf(row, scenario, assumptions, wacc, exit_multiple)
        for name, scenario in assumptions.scenarios.items()
    }


# --- sensitivity grids -----------------------------------------------------------

def _upside_for(row: pd.Series, scenario: ScenarioAssumptions, assumptions: ValuationAssumptions,
                wacc: float, multiple: float) -> float | None:
    res = run_dcf(row, scenario, assumptions, wacc, multiple)
    return res.upside


def sensitivity_wacc_multiple(
    row: pd.Series,
    scenario: ScenarioAssumptions,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
    wacc_steps: list[float] | None = None,
    multiple_steps: list[float] | None = None,
    output: str = "target_price",
) -> pd.DataFrame:
    """Grid of target price (or upside) over WACC x exit multiple."""
    if wacc_steps is None:
        wacc_steps = [round(wacc + d, 4) for d in (-0.015, -0.0075, 0.0, 0.0075, 0.015)]
    if multiple_steps is None:
        multiple_steps = [round(exit_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
        multiple_steps = [m for m in multiple_steps if m > 0] or [exit_multiple]

    grid = {}
    for mult in multiple_steps:
        column = []
        for w in wacc_steps:
            res = run_dcf(row, scenario, assumptions, w, mult)
            value = res.target_price if output == "target_price" else res.upside
            column.append(value if value is not None else np.nan)
        grid[f"{mult:g}x"] = column
    index = [f"{w:.2%}" for w in wacc_steps]
    return pd.DataFrame(grid, index=index)


def sensitivity_implied_growth(
    row: pd.Series,
    scenario: ScenarioAssumptions,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
    wacc_steps: list[float] | None = None,
    multiple_steps: list[float] | None = None,
) -> pd.DataFrame:
    """Grid of the perpetuity growth IMPLIED by each WACC x exit multiple.

    The reasonableness check on the exit multiple (Grupo Mateus style): every
    cell answers "what growth-forever does this multiple embed?" - benchmark
    against the long-run inflation/GDP anchor before trusting the target.
    """
    if wacc_steps is None:
        wacc_steps = [round(wacc + d, 4) for d in (-0.015, -0.0075, 0.0, 0.0075, 0.015)]
    if multiple_steps is None:
        multiple_steps = [round(exit_multiple + d, 2) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
        multiple_steps = [m for m in multiple_steps if m > 0] or [exit_multiple]

    grid = {}
    for mult in multiple_steps:
        column = []
        for w in wacc_steps:
            res = run_dcf(row, scenario, assumptions, w, mult)
            g = res.implied_terminal_growth
            column.append(g if g is not None else np.nan)
        grid[f"{mult:g}x"] = column
    index = [f"{w:.2%}" for w in wacc_steps]
    return pd.DataFrame(grid, index=index)


def driver_tornado(
    row: pd.Series,
    scenario: ScenarioAssumptions,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
) -> pd.DataFrame:
    """One-way driver sensitivity of the target price (IB tornado chart).

    Each driver is flexed one at a time around the base case; everything else
    held constant. Rows sorted by impact (price span), widest first.
    """
    from dataclasses import replace

    base = run_dcf(row, scenario, assumptions, wacc, exit_multiple)
    if base.target_price is None:
        return pd.DataFrame(columns=["driver", "low_price", "high_price",
                                     "low_label", "high_label", "base_price"])

    def price(scn=scenario, w=wacc, m=exit_multiple):
        res = run_dcf(row, scn, assumptions, w, m)
        return res.target_price if res.target_price is not None else np.nan

    flexes = [
        ("Exit multiple +/-1.0x",
         price(m=max(exit_multiple - 1.0, 0.5)), price(m=exit_multiple + 1.0),
         f"{max(exit_multiple - 1.0, 0.5):g}x", f"{exit_multiple + 1.0:g}x"),
        ("WACC +/-150bps",
         price(w=wacc + 0.015), price(w=max(wacc - 0.015, 0.01)),
         f"{wacc + 0.015:.1%}", f"{max(wacc - 0.015, 0.01):.1%}"),
        ("Revenue growth +/-200bps",
         price(scn=replace(scenario, revenue_growth=[g - 0.02 for g in scenario.revenue_growth])),
         price(scn=replace(scenario, revenue_growth=[g + 0.02 for g in scenario.revenue_growth])),
         "-200bps", "+200bps"),
        ("EBITDA margin +/-150bps",
         price(scn=replace(scenario, ebitda_margin=[max(m - 0.015, 0.001) for m in scenario.ebitda_margin])),
         price(scn=replace(scenario, ebitda_margin=[m + 0.015 for m in scenario.ebitda_margin])),
         "-150bps", "+150bps"),
        ("Capex intensity +/-100bps",
         price(scn=replace(scenario, capex_pct=[c + 0.01 for c in scenario.capex_pct])),
         price(scn=replace(scenario, capex_pct=[max(c - 0.01, 0.0) for c in scenario.capex_pct])),
         "+100bps", "-100bps"),
    ]
    rows = []
    for driver, low, high, low_label, high_label in flexes:
        if np.isnan(low) or np.isnan(high):
            continue
        lo, hi = (low, high) if low <= high else (high, low)
        lo_lab, hi_lab = (low_label, high_label) if low <= high else (high_label, low_label)
        rows.append({"driver": driver, "low_price": lo, "high_price": hi,
                     "low_label": lo_lab, "high_label": hi_lab,
                     "base_price": base.target_price})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["span"] = out["high_price"] - out["low_price"]
        out = out.sort_values("span", ascending=False).drop(columns="span").reset_index(drop=True)
    return out


def sensitivity_growth_margin(
    row: pd.Series,
    scenario: ScenarioAssumptions,
    assumptions: ValuationAssumptions,
    wacc: float,
    exit_multiple: float,
    growth_deltas: tuple = (-0.04, -0.02, 0.0, 0.02, 0.04),
    margin_deltas: tuple = (-0.02, -0.01, 0.0, 0.01, 0.02),
) -> pd.DataFrame:
    """Grid of upside over revenue-growth shift x terminal-margin shift."""
    from dataclasses import replace

    grid = {}
    for md in margin_deltas:
        column = []
        for gd in growth_deltas:
            shifted = replace(
                scenario,
                revenue_growth=[g + gd for g in scenario.revenue_growth],
                ebitda_margin=[max(m + md, 0.001) for m in scenario.ebitda_margin],
            )
            res = run_dcf(row, shifted, assumptions, wacc, exit_multiple)
            column.append(res.upside if res.upside is not None else np.nan)
        grid[f"{md:+.0%} mgn"] = column
    index = [f"{gd:+.0%} g" for gd in growth_deltas]
    return pd.DataFrame(grid, index=index)
