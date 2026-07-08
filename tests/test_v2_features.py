"""V2 feature tests: expanded loader, expectations, scenarios, thesis, attention."""

import numpy as np
import pandas as pd
import pytest

from src.ingestion.capiq_loader import load_capiq_exports
from src.ingestion.store import load_store
from src.modeling.attention import compute_attention
from src.modeling.expectations import revision_momentum, valuation_vs_history
from src.modeling.scenarios import (
    ScenarioCase,
    derive_default_cases,
    implied_expectations,
    run_case,
    sensitivity_grid,
)
from src.modeling.thesis import load_thesis, thesis_filename


# --- expanded CapIQ loader -----------------------------------------------------

def _write_min_exports(tmp_path, with_optional=False, with_valuation=False):
    companies = "company_id,ticker,company_name,sector,exchange,currency,source\nX:A,A,Alpha,Theme,NYSE,USD,test\n"
    fin_base = "company_id,period,revenue,gross_profit,ebitda,ebit,net_income,cfo,capex,fcf,cash,total_debt,net_debt,working_capital,interest_expense,source"
    fin_row = "X:A,2026-03-31,100,55,25,20,12,18,4,14,50,120,70,35,4,test"
    if with_optional:
        fin_base += ",sbc,total_equity,ar,inventory,ap"
        fin_row += ",6,300,40,20,25"
    market = "company_id,period,share_price,shares_outstanding,market_cap,enterprise_value,source\nX:A,2026-03-31,10,1000,1000,1070,test\n"
    (tmp_path / "companies.csv").write_text(companies, encoding="utf-8")
    (tmp_path / "financials_quarterly.csv").write_text(fin_base + "\n" + fin_row + "\n", encoding="utf-8")
    (tmp_path / "market_data.csv").write_text(market, encoding="utf-8")
    if with_valuation:
        vh = "company_id,date,share_price,market_cap,enterprise_value,ev_to_ebitda_ltm,ev_to_revenue_ltm,pe_ltm,source\n" \
             "X:A,2026-01-31,10,1000,1070,10.7,2.7,20,test\n"
        (tmp_path / "valuation_history.csv").write_text(vh, encoding="utf-8")


def test_capiq_loader_keeps_optional_columns(tmp_path):
    _write_min_exports(tmp_path, with_optional=True)
    loaded = load_capiq_exports(tmp_path)
    assert "sbc" in loaded["financials"].columns
    assert "total_equity" in loaded["financials"].columns


def test_capiq_loader_tolerates_missing_optional_tables(tmp_path):
    _write_min_exports(tmp_path, with_optional=False, with_valuation=False)
    loaded = load_capiq_exports(tmp_path)
    assert loaded["valuation_history"].empty      # optional table absent -> empty frame
    assert "sbc" not in loaded["financials"].columns


def test_capiq_loader_reads_valuation_history(tmp_path):
    _write_min_exports(tmp_path, with_valuation=True)
    loaded = load_capiq_exports(tmp_path)
    assert len(loaded["valuation_history"]) == 1


# --- valuation vs history --------------------------------------------------------

def _history_frame(values, company_id="X:A"):
    return pd.DataFrame({
        "company_id": company_id,
        "date": pd.date_range("2023-01-31", periods=len(values), freq="ME"),
        "ev_to_ebitda_ltm": values,
    })


def test_valuation_vs_history_percentile_and_zscore():
    history = _history_frame(list(range(10, 30)))       # 20 obs: 10..29
    ctx = valuation_vs_history(history, "X:A", current_value=12.0)
    assert ctx["available"]
    assert ctx["n_obs"] == 20
    assert ctx["percentile"] == pytest.approx(0.10)     # 2 of 20 below 12
    assert ctx["z_score"] < 0                           # below the mean
    assert ctx["median"] == pytest.approx(19.5)


def test_valuation_vs_history_requires_min_obs():
    ctx = valuation_vs_history(_history_frame([10, 11, 12]), "X:A", 11.0)
    assert not ctx["available"]
    ctx = valuation_vs_history(pd.DataFrame(), "X:A", 11.0)
    assert not ctx["available"]


# --- revision momentum -------------------------------------------------------------

def test_revision_momentum_directions():
    est = pd.DataFrame([{
        "company_id": "X:A", "period": "2026-03-31",
        "revenue_est_ntm": 95.0, "revenue_est_ntm_30d_ago": 100.0,
        "eps_est_ntm": 4.5, "eps_est_ntm_30d_ago": 5.0,
        "revenue_est_ntm_90d_ago": 102.0, "eps_est_ntm_90d_ago": 5.2,
        "num_analysts": 9, "next_earnings_date": "2026-08-01",
    }])
    rev = revision_momentum(est, "X:A")
    assert rev["available"]
    assert rev["direction"] == "cutting"
    assert rev["revenue_30d"] == pytest.approx(-0.05)
    assert rev["num_analysts"] == 9
    assert rev["next_earnings_date"] == "2026-08-01"

    rev_empty = revision_momentum(pd.DataFrame(), "X:A")
    assert not rev_empty["available"]


# --- scenarios ------------------------------------------------------------------------

def _op_row(**overrides):
    row = {
        "business_model": "operating",
        "revenue_ttm": 1000.0,
        "ebitda_ttm": 250.0,
        "ebitda_margin_ttm": 0.25,
        "net_income_ttm": 120.0,
        "revenue_yoy_growth": 0.10,
        "market_cap": 2000.0,
        "enterprise_value": 2500.0,
        "net_debt": 500.0,
        "share_price": 20.0,
        "ev_to_ebitda_ttm": 10.0,
        "pe_ttm": 16.7,
    }
    row.update(overrides)
    return pd.Series(row)


def test_scenario_irr_math_operating():
    row = _op_row()
    case = ScenarioCase("base", revenue_cagr=0.10, exit_margin=0.25, exit_multiple=10.0, horizon_years=3)
    res = run_case(row, case)
    assert res.valid
    # exit revenue = 1000*1.1^3 = 1331; ebitda = 332.75; EV = 3327.5; equity = 2827.5
    assert res.exit_equity == pytest.approx(2827.5, rel=1e-4)
    assert res.moic == pytest.approx(1.41375, rel=1e-4)
    assert res.irr == pytest.approx(1.41375 ** (1 / 3) - 1, rel=1e-6)


def test_scenario_financial_uses_pe_not_ev():
    row = _op_row(business_model="financial", net_income_margin_ttm=0.12)
    case = ScenarioCase("base", revenue_cagr=0.0, exit_margin=0.12, exit_multiple=10.0, horizon_years=3)
    res = run_case(row, case)
    # exit NI = 1000*0.12 = 120; equity = 120*10 = 1200 (no net-debt bridge)
    assert res.valid
    assert res.exit_equity == pytest.approx(1200.0)


def test_scenario_handles_equity_wipeout():
    row = _op_row(net_debt=5000.0)
    case = ScenarioCase("bear", revenue_cagr=-0.10, exit_margin=0.10, exit_multiple=5.0, horizon_years=3)
    res = run_case(row, case)
    assert not res.valid
    assert "wiped out" in res.note


def test_sensitivity_grid_shape_and_defaults():
    row = _op_row()
    base = derive_default_cases(row)[1]
    grid = sensitivity_grid(row, base)
    assert grid.shape == (5, 5)
    assert grid.notna().all().all()


def test_implied_expectations_solves_growth():
    row = _op_row()
    ie = implied_expectations(row, fair_exit_multiple=10.0, horizon_years=3, required_returns=(0.10,))
    assert ie["available"]
    implied = ie["required"][0]["implied_profit_cagr"]
    # EV grows to 2500*1.1^3=3327.5 -> exit EBITDA 332.75 vs 250 now -> CAGR 10%
    assert implied == pytest.approx(0.10, rel=1e-3)


# --- thesis YAML -------------------------------------------------------------------------

def test_thesis_loading_and_sanitized_filename(tmp_path):
    company_id = "BOVESPA:TOTS3"
    fname = thesis_filename(company_id)
    assert ":" not in fname
    (tmp_path / fname).write_text(
        "stage: work\nthesis: Test thesis.\nvariant_perception: The edge.\n"
        "catalysts:\n  - date: 2026-08-01\n    event: Earnings\nrisks:\n  - Risk one.\n"
        "scenarios:\n  base: { revenue_cagr: 0.12, exit_margin: 0.3, exit_multiple: 12 }\n"
        "journal:\n  - date: 2026-07-01\n    note: Entry.\n",
        encoding="utf-8",
    )
    t = load_thesis(company_id, tmp_path)
    assert t.exists and t.stage == "work"
    assert t.variant_perception == "The edge."
    assert len(t.catalysts) == 1 and len(t.risks) == 1
    assert "base" in t.scenarios

    missing = load_thesis("NASDAQ:NONE", tmp_path)
    assert not missing.exists and missing.stage == "watch"


# --- attention score ----------------------------------------------------------------------

def test_attention_score_components():
    row = _op_row(ebitda_margin_ttm=0.20)
    prior = _op_row(ebitda_margin_ttm=0.28, revenue_yoy_growth=0.12)
    revisions = {"available": True, "revenue_30d": -0.06, "eps_30d": -0.04, "direction": "cutting"}
    score, comps = compute_attention(row, prior, premium=-0.30, history_percentile=0.05,
                                     revisions=revisions, flags_count=3)
    assert 0 < score <= 100
    assert comps["valuation"] > 0.5          # deep discount + cheap vs history
    assert comps["revisions"] == 1.0         # cuts beyond saturation
    assert comps["inflection"] > 0           # 800bps margin move
    assert comps["flags"] == 0.75

    quiet, _ = compute_attention(row, None, premium=0.10, history_percentile=None,
                                 revisions=None, flags_count=0)
    assert quiet < score


# --- demo startup path -----------------------------------------------------------------------

def test_demo_store_and_side_tables_populated():
    store = load_store(demo=True)
    assert store.mode == "demo"
    assert store.has_valuation_history
    assert store.has_estimates
    assert store.theses_dir is not None and store.theses_dir.exists()
