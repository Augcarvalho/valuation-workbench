"""Tests for the valuation MVP: assumptions, WACC, forecast, NWC, DCF, recommendation."""

import numpy as np
import pandas as pd
import pytest

from src.modeling.dcf import (
    run_dcf,
    sensitivity_growth_margin,
    sensitivity_wacc_multiple,
)
from src.modeling.forecast import build_forecast
from src.modeling.recommendation import recommend
from src.modeling.valuation_assumptions import (
    ScenarioAssumptions,
    load_valuation_assumptions,
    load_wacc_params,
    resolve_glidepath,
)
from src.modeling.wacc import build_terminal_wacc, build_wacc, relever_beta, unlever_beta
from src.modeling.working_capital import nwc_from_days, project_nwc


# --- fixtures ---------------------------------------------------------------------

def _row(**overrides) -> pd.Series:
    base = {
        "company_id": "X:TEST",
        "currency": "USD",
        "revenue_ttm": 1000.0,
        "ebitda_ttm": 250.0,
        "ebit_ttm": 220.0,
        "ebitda_margin_ttm": 0.25,
        "gross_margin_ttm": 0.45,
        "revenue_yoy_growth": 0.10,
        "capex_intensity_ttm": 0.04,
        "market_cap": 2000.0,
        "share_price": 20.0,
        "net_debt": 500.0,
        "total_debt": 600.0,
        "cash": 100.0,
        "interest_expense_ttm": 48.0,
        "working_capital": 150.0,
        "dso": 40.0,
        "dio": 80.0,
        "dpo": 50.0,
    }
    base.update(overrides)
    return pd.Series(base)


def _flat_scenario(n=5, growth=0.10, margin=0.25, da=0.03, capex=0.04, tax=0.25,
                   mode="days") -> ScenarioAssumptions:
    return ScenarioAssumptions(
        name="base",
        revenue_growth=[growth] * n,
        ebitda_margin=[margin] * n,
        d_and_a_pct=[da] * n,
        capex_pct=[capex] * n,
        tax_rate=tax,
        dso=[40.0] * n if mode == "days" else None,
        dih=[80.0] * n if mode == "days" else None,
        dpo=[50.0] * n if mode == "days" else None,
        nwc_pct_revenue=[0.15] * n if mode == "pct" else None,
        nwc_mode=mode,
    )


# --- glidepaths & assumptions --------------------------------------------------------

def test_glidepath_resolver_variants():
    assert resolve_glidepath("auto", 3, 0.1) == [0.1, 0.1, 0.1]
    assert resolve_glidepath(0.05, 3, 0.1) == [0.05, 0.05, 0.05]
    assert resolve_glidepath([0.1, 0.2], 4, None) == [0.1, 0.2, 0.2, 0.2]
    fade = resolve_glidepath({"start": 0.12, "end": 0.04}, 5, None)
    assert fade[0] == pytest.approx(0.12) and fade[-1] == pytest.approx(0.04)
    assert fade[2] == pytest.approx(0.08)
    auto_start = resolve_glidepath({"start": "auto", "end": 0.02}, 3, 0.10)
    assert auto_start[0] == pytest.approx(0.10) and auto_start[-1] == pytest.approx(0.02)


def test_assumptions_yaml_and_auto_scenarios(tmp_path):
    (tmp_path / "X_TEST.yaml").write_text(
        "horizon_years: 4\n"
        "scenarios:\n"
        "  base: { revenue_growth: {start: 0.2, end: 0.05}, ebitda_margin: 0.30 }\n"
        "wacc: { beta: 0.8 }\n"
        "terminal: { exit_multiple: 9.0, perpetuity_growth: 0.03, roic: 0.14, wacc: 0.09 }\n",
        encoding="utf-8",
    )
    row = _row()
    a = load_valuation_assumptions(row, tmp_path)
    assert a.from_file and a.horizon_years == 4
    assert a.exit_multiple == 9.0 and a.perpetuity_growth == 0.03 and a.beta == 0.8
    assert a.terminal_roic == pytest.approx(0.14)
    assert a.terminal_wacc == pytest.approx(0.09)
    assert a.terminal_roic_source == "analyst"
    assert a.scenarios["base"].source == "analyst"
    assert a.scenarios["base"].ebitda_margin == [0.30] * 4
    # bear/bull not in the file -> auto-derived around anchors
    assert a.scenarios["bear"].source == "derived"
    assert a.scenarios["bear"].revenue_growth[0] < a.scenarios["base"].revenue_growth[0]

    # No file at all -> everything derived, anchored on the row.
    b = load_valuation_assumptions(row, tmp_path / "nowhere")
    assert not b.from_file
    assert b.scenarios["base"].revenue_growth[0] == pytest.approx(0.10)  # clipped anchor
    assert b.anchors["nwc_mode"] == "days"

    high_growth = load_valuation_assumptions(
        _row(revenue_yoy_growth=0.18), tmp_path / "nowhere"
    )
    assert high_growth.horizon_years == 10
    assert any("extended to 10 years" in n for n in high_growth.anchors["notes"])


def test_reported_d_and_a_is_preferred_over_ebitda_minus_ebit(tmp_path):
    row = _row(d_and_a_ttm=50.0, ebitda_ttm=300.0, ebit_ttm=200.0)
    assumptions = load_valuation_assumptions(row, tmp_path / "none")
    assert assumptions.anchors["d_and_a_pct"] == pytest.approx(0.05)
    assert any("reported TTM" in note for note in assumptions.anchors["notes"])


def test_implausible_reported_d_and_a_falls_back_to_ebitda_minus_ebit(tmp_path):
    row = _row(
        revenue_ttm=1_000.0,
        d_and_a_ttm=2.0,
        ebitda_ttm=300.0,
        ebit_ttm=200.0,
    )
    assumptions = load_valuation_assumptions(row, tmp_path / "none")
    assert assumptions.anchors["d_and_a_pct"] == pytest.approx(0.10)
    assert any("consistency check" in note for note in assumptions.anchors["notes"])


def test_wacc_params_currency_fallback():
    usd = load_wacc_params("USD")
    brl = load_wacc_params("BRL")
    unknown = load_wacc_params("XXX")
    assert brl["risk_free_rate"] > usd["risk_free_rate"]
    assert brl["default_perpetuity_growth"] == pytest.approx(0.04)
    assert unknown["risk_free_rate"] == usd["risk_free_rate"]  # falls back to USD


# --- WACC -------------------------------------------------------------------------------

def test_unlever_relever_round_trip():
    beta_u = unlever_beta(1.2, debt_to_equity=0.5, tax_rate=0.25)
    assert beta_u == pytest.approx(1.2 / 1.375)
    assert relever_beta(beta_u, 0.5, 0.25) == pytest.approx(1.2)


def test_wacc_components_and_default_beta():
    row = _row()
    params = load_wacc_params("USD")
    w = build_wacc(row, params)
    assert w.beta == 1.0 and w.beta_source == "default"
    assert w.cost_of_equity == pytest.approx(params["risk_free_rate"] + params["equity_risk_premium"])
    # Kd derived: 48 / 600 = 8%
    assert w.cost_of_debt_pretax == pytest.approx(0.08)
    assert w.equity_weight == pytest.approx(2000 / 2600)
    expected = w.equity_weight * w.cost_of_equity + w.debt_weight * 0.08 * 0.75
    assert w.wacc == pytest.approx(expected)


def test_wacc_override_and_analyst_beta():
    row = _row()
    params = load_wacc_params("USD")
    w = build_wacc(row, params, beta_override=0.9, wacc_override=0.10)
    assert w.beta == 0.9 and w.beta_source == "analyst"
    assert w.wacc == 0.10 and w.overridden


def test_extreme_two_year_beta_falls_back_instead_of_driving_wacc():
    params = load_wacc_params("USD")
    w = build_wacc(_row(beta_2y=0.30), params)
    assert w.beta == 1.0
    assert w.beta_source == "default"
    assert any("outside 0.50-2.00" in note for note in w.notes)


def test_terminal_wacc_converges_to_stable_beta_and_peer_leverage():
    params = load_wacc_params("USD")
    current = build_wacc(_row(beta_2y=1.8), params)
    peers = pd.DataFrame({
        "market_cap": [900.0, 800.0, 700.0],
        "total_debt": [100.0, 200.0, 300.0],
    })
    terminal, source = build_terminal_wacc(current, params, peers=peers)
    assert "stable beta 1.0" in source
    assert terminal < current.wacc
    assert terminal > params["risk_free_rate"]


# --- working capital ----------------------------------------------------------------------

def test_nwc_from_days_hand_math():
    # revenue 1000, cogs 550: AR = 40*1000/365, INV = 80*550/365, AP = 50*550/365
    nwc = nwc_from_days(1000.0, 550.0, 40.0, 80.0, 50.0)
    assert nwc == pytest.approx(40 * 1000 / 365 + 80 * 550 / 365 - 50 * 550 / 365)


def test_project_nwc_days_and_pct_modes():
    scen = _flat_scenario(n=3)
    days = project_nwc([1000, 1100, 1210], scen, cogs_pct=0.55, nwc_now=150.0)
    assert days.loc[0, "delta_nwc"] == pytest.approx(days.loc[0, "nwc"] - 150.0)
    assert days.loc[1, "delta_nwc"] == pytest.approx(days.loc[1, "nwc"] - days.loc[0, "nwc"])

    pct = project_nwc([1000, 1100, 1210], _flat_scenario(n=3, mode="pct"), None, nwc_now=150.0)
    assert pct.loc[0, "nwc"] == pytest.approx(150.0)
    assert pct.loc[0, "delta_nwc"] == pytest.approx(0.0)
    assert pct.loc[1, "delta_nwc"] == pytest.approx(0.15 * 100)


# --- forecast -------------------------------------------------------------------------------

def test_forecast_waterfall_hand_math():
    scen = _flat_scenario(n=2, growth=0.10, margin=0.25, da=0.03, capex=0.04, tax=0.25, mode="pct")
    f = build_forecast(1000.0, scen, cogs_pct=None, nwc_now=0.15 * 1000)
    assert f.loc[0, "revenue"] == pytest.approx(1100.0)
    assert f.loc[1, "revenue"] == pytest.approx(1210.0)
    assert f.loc[0, "ebitda"] == pytest.approx(275.0)
    ebit = 275.0 - 33.0
    assert f.loc[0, "ebit"] == pytest.approx(ebit)
    nopat = ebit * 0.75
    delta_nwc = 0.15 * 1100 - 150.0
    ufcf = nopat + 33.0 - 44.0 - delta_nwc
    assert f.loc[0, "ufcf"] == pytest.approx(ufcf)


def test_forecast_negative_ebit_pays_no_tax():
    scen = _flat_scenario(n=1, margin=0.02, da=0.05, mode="pct")
    f = build_forecast(1000.0, scen, None, 150.0)
    assert f.loc[0, "ebit"] < 0
    assert f.loc[0, "taxes"] == 0.0


# --- DCF -------------------------------------------------------------------------------------

def _assumptions_for(row, tmp_path):
    return load_valuation_assumptions(row, tmp_path / "none")


def test_dcf_hand_checked_present_values(tmp_path):
    row = _row()
    a = _assumptions_for(row, tmp_path)
    scen = _flat_scenario(n=2, mode="pct")
    res = run_dcf(row, scen, a, wacc=0.10, exit_multiple=8.0)

    f = res.forecast
    df1, df2 = 1.1 ** -0.5, 1.1 ** -1.5
    expected_pv = f.loc[0, "ufcf"] * df1 + f.loc[1, "ufcf"] * df2
    assert res.pv_explicit == pytest.approx(expected_pv)

    tv = f.loc[1, "ebitda"] * 8.0
    assert res.terminal_value_exit == pytest.approx(tv)
    assert res.pv_terminal_exit == pytest.approx(tv * 1.1 ** -2)
    assert res.enterprise_value == pytest.approx(expected_pv + tv * 1.1 ** -2)

    # Bridge: equity = EV - net debt; upside vs market cap; target from price.
    assert res.implied_equity == pytest.approx(res.enterprise_value - 500.0)
    assert res.upside == pytest.approx(res.implied_equity / 2000.0 - 1)
    assert res.target_price == pytest.approx(20.0 * (1 + res.upside))


def test_dual_terminal_value_cross_checks(tmp_path):
    row = _row()
    a = _assumptions_for(row, tmp_path)
    scen = _flat_scenario(n=5, mode="pct")
    res = run_dcf(row, scen, a, wacc=0.10, exit_multiple=8.0)

    # Stable reinvestment is paid for: g = reinvestment rate x terminal ROIC.
    assert res.terminal_reinvestment_rate == pytest.approx(
        res.perpetuity_growth / res.terminal_roic
    )
    assert res.terminal_ufcf == pytest.approx(
        res.terminal_nopat * (1 - res.terminal_reinvestment_rate)
    )
    assert res.terminal_value_perp == pytest.approx(
        res.terminal_ufcf / (res.terminal_wacc - res.perpetuity_growth)
    )
    # With ROIC = WACC the fundamental TV is growth-neutral; an incompatible
    # market multiple therefore has no economically valid implied g.
    assert res.implied_terminal_growth is None
    # Implied multiple from perpetuity TV = TV_perp / terminal EBITDA.
    assert res.implied_exit_multiple == pytest.approx(res.terminal_value_perp / res.forecast["ebitda"].iloc[-1])


def test_perpetuity_guard_when_wacc_below_growth(tmp_path):
    row = _row()
    a = _assumptions_for(row, tmp_path)
    res = run_dcf(row, _flat_scenario(n=3, mode="pct"), a, wacc=0.02, exit_multiple=8.0)
    assert np.isnan(res.terminal_value_perp)
    assert any("perpetuity invalid" in n for n in res.notes)


def test_sensitivity_grids_shape_and_monotonicity(tmp_path):
    row = _row()
    a = _assumptions_for(row, tmp_path)
    scen = _flat_scenario(n=3, mode="pct")
    grid = sensitivity_wacc_multiple(row, scen, a, wacc=0.10, exit_multiple=8.0)
    assert grid.shape == (5, 5)
    # Higher multiple -> higher target (rows fixed); higher WACC -> lower target.
    assert (grid.iloc[0].diff().dropna() > 0).all()
    assert (grid.iloc[:, 0].diff().dropna() < 0).all()

    gm = sensitivity_growth_margin(row, scen, a, wacc=0.10, exit_multiple=8.0)
    assert gm.shape == (5, 5)
    assert (gm.iloc[0].diff().dropna() > 0).all()   # higher margin -> higher upside


# --- comps ------------------------------------------------------------------------------------

def test_comps_spread_forwards_and_quartiles():
    from src.modeling.comps import comps_spread, exit_multiple_from_comps, quartile_stats

    peers = pd.DataFrame([
        {"company_id": f"P{i}", "ticker": f"P{i}", "company_name": f"Peer {i}",
         "market_cap": 1000.0 * i, "enterprise_value": 1200.0 * i,
         "revenue_yoy_growth": 0.05 * i, "ebitda_margin_ttm": 0.10 + 0.02 * i,
         "ev_to_revenue_ttm": 1.0 * i, "ev_to_ebitda_ttm": 4.0 + i, "pe_ttm": 10.0 + i}
        for i in range(1, 6)
    ])
    estimates = pd.DataFrame([
        {"company_id": f"P{i}", "period": "2026-03-31",
         "revenue_est_ntm": 1000.0 * i, "ebitda_est_ntm": 200.0 * i}
        for i in range(1, 5)  # P5 has no estimates -> NTM NaN, LTM intact
    ])
    spread = comps_spread(peers, estimates)
    p1 = spread[spread["company_id"] == "P1"].iloc[0]
    assert p1["ev_to_ebitda_ntm"] == pytest.approx(1200.0 / 200.0)
    assert spread[spread["company_id"] == "P5"]["ev_to_ebitda_ntm"].isna().all()

    stats = quartile_stats(spread)
    assert stats.loc["ev_to_ebitda_ttm", "median"] == pytest.approx(7.0)
    assert stats.loc["ev_to_ebitda_ttm", "q1"] < stats.loc["ev_to_ebitda_ttm", "q3"]

    mult, label = exit_multiple_from_comps(spread, anchor_company_id="P1")
    assert mult is not None and "NTM" in label
    # Anchor excluded: median of P2..P4 NTM multiples (P5 NaN) = 6.0
    assert mult == pytest.approx(6.0)


# --- demo-mode end-to-end -----------------------------------------------------------------------

def test_full_valuation_case_on_demo_data(tmp_path):
    """The whole MVP path runs on public demo data with no Capital IQ fields."""
    from src.ingestion.store import load_store
    from src.modeling.valuation_case import build_valuation_case
    from src.reporting.valuation_case import generate_valuation_case

    store = load_store(demo=True)
    df = pd.read_csv(store.dataset_path, parse_dates=["period"])
    case = build_valuation_case(df, "GOOGL", store=store)

    assert case.assumptions.from_file            # demo sample YAML picked up
    assert case.recommendation.stance == "INDICATIVE"
    assert case.base.enterprise_value > 0
    assert case.base.upside is not None
    assert case.sens_wacc_multiple.shape == (5, 5)
    assert {"bear", "base", "bull"} == set(case.scenarios)

    # A company with no assumptions file still produces a full case (Tier-1).
    auto = build_valuation_case(df, "PRNR3.SA", store=store)
    assert not auto.assumptions.from_file
    assert auto.base.enterprise_value > 0
    assert any("no analyst assumptions file" in n for n in auto.notes)
    assert auto.market_reference_multiple is not None
    # Auto cases express stable-growth economics as a multiple; the independent
    # peer multiple remains a separate market cross-check.
    assert "Gordon-consistent" in auto.exit_multiple_source
    assert auto.exit_multiple == pytest.approx(auto.base.implied_exit_multiple)
    assert auto.base.enterprise_value == pytest.approx(auto.base.enterprise_value_perp)

    # HTML export renders to a custom directory (keeps repo outputs untouched).
    path = generate_valuation_case(demo=True, company_id="GOOGL", output_dir=tmp_path)
    html = path.read_text(encoding="utf-8")
    assert len(html) > 10_000
    for section in ["WACC Build", "Equity Value Bridge", "Sensitivity", "Methodology Appendix"]:
        assert section in html


# --- recommendation ---------------------------------------------------------------------------

def test_recommendation_bands_and_reconciliation():
    buy = recommend(upside=0.34, bear_upside=-0.08, bull_upside=0.95, verdict_key="do_work")
    assert buy.stance == "BUY"
    assert "34" in buy.headline
    hold = recommend(upside=0.05, bear_upside=-0.2, bull_upside=0.3, verdict_key="constructive")
    assert hold.stance == "HOLD"
    sell = recommend(upside=-0.35, bear_upside=-0.6, bull_upside=0.0, verdict_key="avoid")
    assert sell.stance == "SELL"
    assert recommend(upside=None, bear_upside=None, bull_upside=None, verdict_key="watch").stance == "N/A"
    # Disagreement between DCF and watchlist verdict is surfaced, not hidden.
    conflicted = recommend(upside=0.40, bear_upside=0.1, bull_upside=0.8, verdict_key="avoid")
    assert "verdict" in conflicted.reconciliation.lower()


def test_implied_growth_grid_and_tornado():
    """New sensitivity outputs: implied-g grid brackets the anchor; tornado is
    sorted by impact and brackets the base target."""
    import numpy as np
    import pandas as pd

    from src.ingestion.store import load_store
    from src.modeling.valuation_case import build_valuation_case

    store = load_store(demo=True)
    df = pd.read_csv(store.dataset_path, parse_dates=["period"])
    case = build_valuation_case(df, "GOOGL", store=store)
    ig = case.sens_implied_growth
    assert not ig.empty and ig.shape[0] >= 3
    center = ig.iloc[len(ig.index) // 2, len(ig.columns) // 2]
    # Grid steps are display-rounded (WACC 4dp, multiple 2dp), so the center
    # matches the base implied growth only approximately.
    assert center == pytest.approx(case.base.implied_terminal_growth, abs=5e-3)
    # Higher multiple (same WACC row) must imply higher growth-forever.
    mid = len(ig.index) // 2
    row_vals = ig.iloc[mid].dropna().to_numpy(dtype=float)
    assert (np.diff(row_vals) > 0).all()
    # At a fixed exit multiple, a higher terminal WACC requires a higher
    # implied perpetual growth rate to reconcile to the same terminal value.
    col_vals = ig.iloc[:, len(ig.columns) // 2].dropna().to_numpy(dtype=float)
    assert (np.diff(col_vals) > 0).all()

    t = case.tornado
    assert not t.empty
    assert (t["low_price"] <= t["base_price"] + 1e-9).all()
    assert (t["high_price"] >= t["base_price"] - 1e-9).all()
    spans = (t["high_price"] - t["low_price"]).to_numpy()
    assert (np.diff(spans) <= 1e-9).all()          # sorted widest first
