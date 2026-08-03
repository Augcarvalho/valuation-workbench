"""Sponsor underwriting: sources & uses, debt schedule, liquidity and returns."""

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
    excess_cash: float = 0.0
    minimum_cash: float = 0.0
    revolver_capacity: float = 0.0
    sponsor_ownership: float = 1.0
    schedule: pd.DataFrame = field(default_factory=pd.DataFrame)
    sources_uses: pd.DataFrame = field(default_factory=pd.DataFrame)
    bridge: dict = field(default_factory=dict)
    covenant_breaches: list[str] = field(default_factory=list)
    liquidity_shortfall: float = 0.0
    notes: list[str] = field(default_factory=list)
    valid: bool = True


def _invalid(
    entry_multiple: float,
    exit_multiple: float | None,
    entry_ebitda: float | None,
    debt_pct: float,
    cost_of_debt: float,
    note: str,
) -> LboResult:
    return LboResult(
        entry_multiple, exit_multiple or entry_multiple, entry_ebitda or 0.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, None,
        debt_pct, cost_of_debt, 0, notes=[note], valid=False,
    )


def run_lbo(
    forecast: pd.DataFrame,
    entry_ebitda: float,
    entry_multiple: float,
    exit_multiple: float | None = None,
    debt_pct: float = 0.5,
    entry_leverage: float | None = None,
    cost_of_debt: float = 0.08,
    tax_rate: float = 0.25,
    fees_pct_ev: float = 0.02,
    min_cash_sweep: float = 1.0,
    *,
    hold_period_years: int | None = None,
    minimum_cash: float = 0.0,
    revolver_capacity: float | None = None,
    revolver_rate: float | None = None,
    mandatory_amortization_pct: float = 0.0,
    financing_fees_pct_debt: float = 0.0,
    oid_pct_debt: float = 0.0,
    management_rollover: float = 0.0,
    acquired_cash: float = 0.0,
    existing_debt_refinanced: float = 0.0,
    interest_deduction_cap_pct_ebitda: float = 1.0,
    max_net_leverage: float = 6.0,
    min_interest_coverage: float = 1.5,
) -> LboResult:
    """Run a compact but lender-aware LBO on an existing operating forecast.

    ``ufcf`` is pre-financing cash flow. The selected hold period is independent
    of the DCF horizon. Cash deficits draw the revolver before a liquidity
    shortfall is recorded; positive cash first funds mandatory amortization and
    then sweeps term debt.
    """
    notes: list[str] = []
    if entry_ebitda is None or entry_ebitda <= 0:
        return _invalid(entry_multiple, exit_multiple, entry_ebitda, debt_pct,
                        cost_of_debt, "entry EBITDA not positive - LBO not applicable")
    if hold_period_years is None:
        hold_period_years = min(5, len(forecast))
    if hold_period_years < 1:
        return _invalid(entry_multiple, exit_multiple, entry_ebitda, debt_pct,
                        cost_of_debt, "hold period must be at least one year")
    if len(forecast) < hold_period_years:
        return _invalid(
            entry_multiple, exit_multiple, entry_ebitda, debt_pct, cost_of_debt,
            f"forecast has {len(forecast)} years but the LBO hold is {hold_period_years}",
        )
    forecast = forecast.iloc[:hold_period_years].reset_index(drop=True)
    if exit_multiple is None:
        exit_multiple = entry_multiple
        notes.append("exit at entry multiple (no re-rating assumed)")
    revolver_rate = float(revolver_rate if revolver_rate is not None else cost_of_debt + 0.02)

    entry_ev = float(entry_multiple) * float(entry_ebitda)
    if entry_leverage is not None:
        entry_debt = min(max(float(entry_leverage), 0.0) * float(entry_ebitda), entry_ev)
        debt_pct = entry_debt / entry_ev if entry_ev > 0 else 0.0
    else:
        entry_debt = max(float(debt_pct), 0.0) * entry_ev
    revolver_capacity = float(
        revolver_capacity if revolver_capacity is not None else 0.5 * entry_ebitda
    )
    transaction_fees = max(float(fees_pct_ev), 0.0) * entry_ev
    financing_fees = max(float(financing_fees_pct_debt), 0.0) * entry_debt
    oid = max(float(oid_pct_debt), 0.0) * entry_debt
    purchase_equity = entry_ev - existing_debt_refinanced + acquired_cash
    total_uses = (
        purchase_equity + existing_debt_refinanced + minimum_cash
        + transaction_fees + financing_fees + oid
    )
    rollover = min(max(float(management_rollover), 0.0), total_uses)
    acquired_cash_source = max(float(acquired_cash), 0.0)
    equity_check = total_uses - entry_debt - rollover - acquired_cash_source
    if equity_check <= 0:
        return _invalid(entry_multiple, exit_multiple, entry_ebitda, debt_pct,
                        cost_of_debt, "sources exceed uses; sponsor equity is non-positive")
    sponsor_ownership = equity_check / (equity_check + rollover) if rollover > 0 else 1.0
    sources_uses = pd.DataFrame([
        {"section": "Use", "line_item": "Purchase equity value", "amount": purchase_equity},
        {"section": "Use", "line_item": "Refinance existing debt", "amount": existing_debt_refinanced},
        {"section": "Use", "line_item": "Minimum cash funded", "amount": minimum_cash},
        {"section": "Use", "line_item": "Transaction fees", "amount": transaction_fees},
        {"section": "Use", "line_item": "Financing fees and OID", "amount": financing_fees + oid},
        {"section": "Source", "line_item": "Term debt", "amount": entry_debt},
        {"section": "Source", "line_item": "Cash acquired", "amount": acquired_cash_source},
        {"section": "Source", "line_item": "Management rollover", "amount": rollover},
        {"section": "Source", "line_item": "Sponsor equity", "amount": equity_check},
    ])

    term_debt = entry_debt
    revolver = 0.0
    cash = float(minimum_cash)
    initial_term = entry_debt
    rows: list[dict] = []
    breaches: list[str] = []
    liquidity_shortfall = 0.0
    for t, operating in forecast.iterrows():
        ebitda = float(operating["ebitda"])
        ufcf = float(operating["ufcf"])
        ebit = float(operating.get("ebit", ebitda))
        opening_term = term_debt
        opening_revolver = revolver
        cash_interest = opening_term * cost_of_debt + opening_revolver * revolver_rate
        deductible_interest = min(
            cash_interest,
            max(ebit, 0.0),
            max(ebitda * interest_deduction_cap_pct_ebitda, 0.0),
        )
        interest_tax_shield = deductible_interest * tax_rate
        fcf_after_interest = ufcf - cash_interest + interest_tax_shield

        mandatory = min(initial_term * max(mandatory_amortization_pct, 0.0), term_debt)
        available = cash + fcf_after_interest - minimum_cash
        mandatory_paid = min(max(available, 0.0), mandatory)
        term_debt -= mandatory_paid
        available -= mandatory_paid
        if available < 0:
            draw = min(-available, max(revolver_capacity - revolver, 0.0))
            revolver += draw
            available += draw
        else:
            draw = 0.0
        if available < 0:
            liquidity_shortfall += -available
            cash = minimum_cash
            available = 0.0
        else:
            cash = minimum_cash + available

        revolver_repay = min(max(cash - minimum_cash, 0.0), revolver)
        revolver -= revolver_repay
        cash -= revolver_repay
        sweep_cash = max(cash - minimum_cash, 0.0) * max(min(min_cash_sweep, 1.0), 0.0)
        sweep = min(sweep_cash, term_debt)
        term_debt -= sweep
        cash -= sweep

        total_debt = term_debt + revolver
        leverage = (total_debt - max(cash - minimum_cash, 0.0)) / ebitda if ebitda > 0 else np.nan
        coverage = ebitda / cash_interest if cash_interest > 0 else np.inf
        if pd.notna(leverage) and leverage > max_net_leverage:
            breaches.append(f"Y{t + 1}: net leverage {leverage:.1f}x > {max_net_leverage:.1f}x")
        if coverage < min_interest_coverage:
            breaches.append(f"Y{t + 1}: interest coverage {coverage:.1f}x < {min_interest_coverage:.1f}x")
        rows.append({
            "year": t + 1,
            "ebitda": ebitda,
            "ufcf": ufcf,
            "term_debt_open": opening_term,
            "revolver_open": opening_revolver,
            "cash_interest": cash_interest,
            "deductible_interest": deductible_interest,
            "interest_tax_shield": interest_tax_shield,
            "fcf_after_interest": fcf_after_interest,
            "mandatory_amortization": mandatory_paid,
            "revolver_draw": draw,
            "revolver_repayment": revolver_repay,
            "cash_sweep": sweep,
            "debt_paydown": mandatory_paid + sweep,
            "term_debt_end": term_debt,
            "revolver_end": revolver,
            "debt_end": total_debt,
            "cash_end": cash,
            "excess_cash": max(cash - minimum_cash, 0.0),
            "leverage": leverage,
            "interest_coverage": coverage,
        })
    schedule = pd.DataFrame(rows)

    exit_ebitda = float(forecast["ebitda"].iloc[-1])
    exit_ev = float(exit_multiple) * exit_ebitda
    exit_debt = term_debt + revolver
    enterprise_to_equity = exit_ev - exit_debt + cash
    exit_equity = enterprise_to_equity * sponsor_ownership
    moic = exit_equity / equity_check if equity_check > 0 and exit_equity > 0 else None
    irr = moic ** (1.0 / hold_period_years) - 1.0 if moic is not None else None
    if exit_equity <= 0:
        notes.append("exit equity non-positive: debt exceeds exit EV under these assumptions")
    if liquidity_shortfall > 0:
        notes.append(f"liquidity shortfall of {liquidity_shortfall:,.1f} after exhausting revolver")
    if breaches:
        notes.append(f"{len(breaches)} covenant breach(es) under the selected case")

    fees_total = transaction_fees + financing_fees + oid
    raw_bridge = {
        "equity_check": equity_check,
        "ebitda_growth": (exit_ebitda - entry_ebitda) * entry_multiple,
        "multiple_change": (exit_multiple - entry_multiple) * exit_ebitda,
        "deleveraging": entry_debt - exit_debt,
        "excess_cash": max(cash - minimum_cash, 0.0),
        "fees": -fees_total,
    }
    explained_exit = equity_check + sum(v for k, v in raw_bridge.items() if k != "equity_check")
    raw_bridge["other_and_ownership"] = exit_equity - explained_exit
    raw_bridge["exit_equity"] = exit_equity

    return LboResult(
        entry_multiple=float(entry_multiple),
        exit_multiple=float(exit_multiple),
        entry_ebitda=float(entry_ebitda),
        exit_ebitda=exit_ebitda,
        entry_ev=entry_ev,
        exit_ev=exit_ev,
        entry_debt=entry_debt,
        exit_debt=exit_debt,
        equity_check=equity_check,
        exit_equity=exit_equity,
        moic=moic,
        irr=irr,
        debt_pct=debt_pct,
        cost_of_debt=cost_of_debt,
        horizon=hold_period_years,
        excess_cash=max(cash - minimum_cash, 0.0),
        minimum_cash=minimum_cash,
        revolver_capacity=revolver_capacity,
        sponsor_ownership=sponsor_ownership,
        schedule=schedule,
        sources_uses=sources_uses,
        bridge=raw_bridge,
        covenant_breaches=breaches,
        liquidity_shortfall=liquidity_shortfall,
        notes=notes,
        valid=liquidity_shortfall <= 0 and exit_equity > 0,
    )


def lbo_from_case(
    case,
    entry_multiple: float | None = None,
    exit_multiple: float | None = None,
    debt_pct: float = 0.5,
    entry_leverage: float | None = None,
    cost_of_debt: float | None = None,
    hold_period_years: int = 5,
    **kwargs,
) -> LboResult:
    """Build a sponsor case from the canonical valuation forecast."""
    row = case.assessment.row
    entry_ebitda = row.get("ebitda_ttm")
    entry_ebitda = float(entry_ebitda) if pd.notna(entry_ebitda) else None
    if entry_multiple is None:
        own = row.get("ev_to_ebitda_ttm")
        entry_multiple = float(own) if pd.notna(own) and own > 0 else case.exit_multiple
    if exit_multiple is None:
        exit_multiple = float(getattr(case, "sponsor_exit_multiple", case.exit_multiple))
    if cost_of_debt is None:
        kd = getattr(case.wacc, "cost_of_debt_pretax", None)
        cost_of_debt = float(kd) if kd else 0.08
    existing_debt = row.get("total_debt")
    existing_debt = float(existing_debt) if pd.notna(existing_debt) else 0.0
    acquired_cash = row.get("cash_st_invest")
    if pd.isna(acquired_cash):
        acquired_cash = row.get("cash")
    acquired_cash = float(acquired_cash) if pd.notna(acquired_cash) else 0.0
    if "minimum_cash" not in kwargs:
        restricted_cash = row.get("restricted_cash")
        restricted_cash = float(restricted_cash) if pd.notna(restricted_cash) else 0.0
        revenue = row.get("revenue_ttm")
        revenue = float(revenue) if pd.notna(revenue) else 0.0
        kwargs["minimum_cash"] = max(restricted_cash, revenue * 0.02)
    kwargs.setdefault("existing_debt_refinanced", existing_debt)
    kwargs.setdefault("acquired_cash", acquired_cash)
    return run_lbo(
        forecast=case.base.forecast,
        entry_ebitda=entry_ebitda,
        entry_multiple=entry_multiple,
        exit_multiple=exit_multiple,
        debt_pct=debt_pct,
        entry_leverage=entry_leverage,
        cost_of_debt=cost_of_debt,
        tax_rate=case.assumptions.scenarios["base"].tax_rate,
        hold_period_years=hold_period_years,
        **kwargs,
    )
