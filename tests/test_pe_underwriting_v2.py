"""Regression tests for the governed PE underwriting workflow."""

import pandas as pd
import pytest

from src.modeling.capital_structure import build_capital_structure
from src.modeling.lbo import run_lbo
from src.modeling.metrics import prepare_monitoring_dataset
from src.modeling.readiness import evaluate_readiness


def _raw_financials(periods: list[str]) -> dict[str, pd.DataFrame]:
    n = len(periods)
    return {
        "companies": pd.DataFrame([{
            "company_id": "TEST", "ticker": "TST", "company_name": "Test Co",
            "sector": "Services", "currency": "USD", "exchange": "NYSE",
        }]),
        "financials": pd.DataFrame({
            "company_id": ["TEST"] * n,
            "period": periods,
            "revenue": [100.0 + i * 5 for i in range(n)],
            "gross_profit": [60.0] * n,
            "ebitda": [20.0] * n,
            "ebit": [17.0] * n,
            "net_income": [10.0] * n,
            "cfo": [18.0] * n,
            "capex": [5.0] * n,
            "cash": [25.0] * n,
            "total_debt": [40.0] * n,
            "source": ["test"] * n,
        }),
        "market_data": pd.DataFrame(),
        "estimates": pd.DataFrame(),
    }


def _forecast(years: int = 10, ufcf: float = 25.0) -> pd.DataFrame:
    return pd.DataFrame({
        "ebitda": [100.0 + i * 5 for i in range(years)],
        "ebit": [85.0 + i * 4 for i in range(years)],
        "ufcf": [ufcf] * years,
    })


def test_fiscal_period_end_is_not_collapsed_to_calendar_quarter() -> None:
    raw = _raw_financials(["2025-01-31", "2025-04-30", "2025-07-31", "2025-10-31"])
    dataset = prepare_monitoring_dataset(raw)
    assert dataset["period"].dt.strftime("%Y-%m-%d").tolist() == [
        "2025-01-31", "2025-04-30", "2025-07-31", "2025-10-31",
    ]
    assert dataset["fiscal_period_id"].is_unique
    assert bool(dataset.iloc[-1]["ttm_complete"])


def test_duplicate_canonical_financial_observation_is_rejected() -> None:
    raw = _raw_financials(["2025-03-31", "2025-03-31"])
    with pytest.raises(ValueError, match="duplicate canonical"):
        prepare_monitoring_dataset(raw)


def test_lbo_hold_period_is_independent_of_dcf_forecast_horizon() -> None:
    result = run_lbo(
        _forecast(10), entry_ebitda=100.0, entry_multiple=10.0,
        exit_multiple=9.0, entry_leverage=4.0, hold_period_years=5,
    )
    assert result.horizon == 5
    assert len(result.schedule) == 5
    assert result.exit_ebitda == pytest.approx(120.0)


def test_sources_and_uses_reconcile_exactly() -> None:
    result = run_lbo(
        _forecast(5), entry_ebitda=100.0, entry_multiple=10.0,
        entry_leverage=4.0, minimum_cash=20.0, acquired_cash=10.0,
        existing_debt_refinanced=75.0, financing_fees_pct_debt=0.02,
        management_rollover=25.0, hold_period_years=5,
    )
    uses = result.sources_uses.loc[result.sources_uses["section"] == "Use", "amount"].sum()
    sources = result.sources_uses.loc[result.sources_uses["section"] == "Source", "amount"].sum()
    assert sources == pytest.approx(uses)
    assert result.sponsor_ownership < 1.0


def test_cash_deficit_draws_revolver_then_flags_shortfall() -> None:
    result = run_lbo(
        _forecast(3, ufcf=-80.0), entry_ebitda=100.0, entry_multiple=8.0,
        entry_leverage=4.0, hold_period_years=3, minimum_cash=10.0,
        revolver_capacity=30.0,
    )
    assert result.schedule["revolver_draw"].sum() > 0
    assert result.liquidity_shortfall > 0
    assert not result.valid


def test_debt_capacity_uses_lower_of_leverage_and_coverage() -> None:
    row = pd.Series({
        "business_model": "operating", "revenue_ttm": 1000.0,
        "ebitda_ttm": 100.0, "total_debt": 300.0, "cash": 50.0,
        "interest_expense_ttm": 60.0, "enterprise_value": 1000.0,
    })
    result = build_capital_structure(row)
    assert result.coverage_capacity == pytest.approx(100 / (2.0 * 0.2))
    assert result.underwritten_capacity[4.0] == pytest.approx(250.0)
    assert result.limiting_constraint[4.0] == "interest coverage"
    assert result.underwritten_incremental[4.0] == 0.0


def test_readiness_requires_data_then_manual_governance() -> None:
    blocked = evaluate_readiness(pd.Series({"company_id": "X", "ttm_complete": False}))
    assert blocked.status == "DATA_BLOCKED"
    screen = evaluate_readiness(pd.Series({
        "company_id": "X", "fiscal_period_id": "X|2025-12-31|quarterly",
        "ttm_complete": True,
    }))
    assert screen.status == "SCREENING_ONLY"
    ready = evaluate_readiness(
        pd.Series({
            "company_id": "X", "fiscal_period_id": "X|2025-12-31|quarterly",
            "ttm_complete": True,
        }),
        assumptions_final=True, peers_reviewed=True,
    )
    assert ready.status == "IC_READY"
    assert ready.can_export_final


def test_ic_memo_reuses_canonical_case_sponsor_scenarios() -> None:
    from src.ingestion.public_demo_loader import load_public_demo
    from src.ingestion.store import load_store
    from src.modeling.valuation_case import build_valuation_case
    from src.reporting.ic_memo import build_memo_context

    dataset = prepare_monitoring_dataset(load_public_demo())
    store = load_store(True)
    case = build_valuation_case(dataset, "GOOGL", store=store)
    context = build_memo_context(dataset, "GOOGL", store)
    base = case.lbo_scenarios["base"]
    memo_base = next(item for item in context["scenario_rows"] if item["name"] == "Base")
    assert context["case_id"] == case.case_id
    assert context["readiness"] == case.readiness.status
    assert memo_base["moic"] == f"{base.moic:.2f}x"
    assert f"{base.irr:+.1%}" in memo_base["irr"]


def test_financials_model_exposes_bank_specific_metrics_when_exported() -> None:
    from src.modeling.financials_valuation import build_financials_valuation

    result = build_financials_valuation(pd.Series({
        "business_model": "financial", "market_cap": 1500.0,
        "net_income_ttm": 120.0, "tangible_common_equity": 1000.0,
        "net_interest_income_ttm": 200.0, "average_earning_assets": 5000.0,
        "provision_expense_ttm": 30.0, "average_loans": 3000.0,
        "noninterest_income_ttm": 100.0, "noninterest_expense_ttm": 180.0,
        "cet1_capital": 600.0, "risk_weighted_assets": 5000.0,
        "nonperforming_loans": 90.0, "loans": 3000.0,
        "loan_loss_reserves": 120.0,
    }), cost_of_equity=0.12, growth=0.04)
    assert result.net_interest_margin == pytest.approx(0.04)
    assert result.credit_loss_ratio == pytest.approx(0.01)
    assert result.efficiency_ratio == pytest.approx(0.60)
    assert result.cet1_ratio == pytest.approx(0.12)
    assert result.npl_ratio == pytest.approx(0.03)
    assert result.reserve_coverage == pytest.approx(4 / 3)
