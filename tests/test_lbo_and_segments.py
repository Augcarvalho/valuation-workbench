"""LBO engine and Tier-2 segment build: hand-checked math."""

import pandas as pd
import pytest

from src.modeling.forecast import segment_revenue_path
from src.modeling.lbo import run_lbo


def _flat_forecast(ebitda: float, ufcf: float, years: int = 5) -> pd.DataFrame:
    return pd.DataFrame({"year": range(1, years + 1),
                         "ebitda": [ebitda] * years, "ufcf": [ufcf] * years})


def test_lbo_hand_math_flat_no_growth():
    """Entry 100 EBITDA at 8x, 50% debt, kd 10%, UFCF 60/yr, exit 8x flat EBITDA.

    Year 1: interest 40, tax shield 10, sweep 30 -> debt 370. The after-tax
    interest schedule is checked
    at the endpoints; bridge must sum exactly."""
    fc = _flat_forecast(ebitda=100.0, ufcf=60.0, years=5)
    lbo = run_lbo(fc, entry_ebitda=100.0, entry_multiple=8.0, exit_multiple=8.0,
                  debt_pct=0.5, cost_of_debt=0.10, fees_pct_ev=0.0)
    assert lbo.entry_ev == pytest.approx(800.0)
    assert lbo.entry_debt == pytest.approx(400.0)
    assert lbo.equity_check == pytest.approx(400.0)

    # After-tax interest is 7.5% of opening debt: d' = 1.075*d - 60.
    expected = [370.0, 337.75, 303.081, 265.812, 225.748]
    assert list(lbo.schedule["debt_end"].round(3)) == expected
    assert lbo.exit_ev == pytest.approx(800.0)
    assert lbo.exit_equity == pytest.approx(800.0 - 225.748, abs=1e-3)
    assert lbo.moic == pytest.approx(574.252 / 400.0, abs=1e-4)
    assert lbo.irr == pytest.approx((574.252 / 400.0) ** 0.2 - 1.0, abs=1e-6)

    # Bridge reconciles exactly: check + parts = exit equity.
    b = lbo.bridge
    total = (b["equity_check"] + b["ebitda_growth"] + b["multiple_change"]
             + b["deleveraging"] + b["excess_cash"] + b["fees"])
    assert total == pytest.approx(b["exit_equity"], abs=1e-6)
    assert b["ebitda_growth"] == pytest.approx(0.0)      # flat EBITDA
    assert b["multiple_change"] == pytest.approx(0.0)    # exit at entry
    assert b["deleveraging"] == pytest.approx(400.0 - 225.748, abs=1e-3)


def test_lbo_retains_cash_after_debt_is_repaid():
    fc = _flat_forecast(100.0, 300.0, 2)
    lbo = run_lbo(fc, entry_ebitda=100.0, entry_multiple=4.0, exit_multiple=4.0,
                  debt_pct=0.25, cost_of_debt=0.0, fees_pct_ev=0.0)
    assert lbo.exit_debt == 0.0
    assert lbo.excess_cash == pytest.approx(500.0)
    assert lbo.exit_equity == pytest.approx(900.0)


def test_lbo_can_size_entry_debt_on_ebitda():
    fc = _flat_forecast(100.0, 50.0, 5)
    lbo = run_lbo(fc, entry_ebitda=100.0, entry_multiple=20.0,
                  entry_leverage=3.0, debt_pct=0.5, cost_of_debt=0.08)
    assert lbo.entry_ev == pytest.approx(2_000.0)
    assert lbo.entry_debt == pytest.approx(300.0)
    assert lbo.debt_pct == pytest.approx(0.15)
    assert lbo.equity_check == pytest.approx(1_740.0)  # EV - debt + 2% fees


def test_lbo_guards():
    fc = _flat_forecast(10.0, -50.0, 5)
    heavy = run_lbo(fc, entry_ebitda=10.0, entry_multiple=8.0, debt_pct=0.8,
                    cost_of_debt=0.12)
    # Negative FCF: no paydown ever, debt stays at entry.
    assert (heavy.schedule["debt_paydown"] == 0).all()
    bad = run_lbo(fc, entry_ebitda=-5.0, entry_multiple=8.0)
    assert not bad.valid and bad.moic is None


def test_segment_revenue_path_hand_math():
    """One segment: 10 units +2/yr, RPU 100 growing 10%/yr.
    Y1: 12 x 110 = 1320; Y2: 14 x 121 = 1694."""
    segs = [{"name": "Stores", "units": 10, "revenue_per_unit": 100,
             "unit_adds": 2, "rpu_growth": 0.10}]
    path = segment_revenue_path(segs, 2)
    assert path[0] == pytest.approx(1320.0)
    assert path[1] == pytest.approx(1694.0)


def test_segment_scenario_map_and_padding():
    segs = [{"name": "S", "units": 10, "revenue_per_unit": 100,
             "unit_adds": {"bear": 0, "base": 2, "bull": 5},
             "rpu_growth": [0.10]}]           # 1-element list pads to horizon
    bear = segment_revenue_path(segs, 2, "bear")
    bull = segment_revenue_path(segs, 2, "bull")
    assert bear[0] == pytest.approx(10 * 110.0)
    assert bull[0] == pytest.approx(15 * 110.0)
    assert bear[1] == pytest.approx(10 * 121.0)   # rpu_growth padded to year 2


def test_segments_flow_through_forecast():
    from src.modeling.forecast import build_forecast
    from src.modeling.valuation_assumptions import ScenarioAssumptions

    scn = ScenarioAssumptions(
        name="base", revenue_growth=[0.05] * 3, ebitda_margin=[0.20] * 3,
        d_and_a_pct=[0.03] * 3, capex_pct=[0.04] * 3, tax_rate=0.30,
        dso=None, dih=None, dpo=None, nwc_pct_revenue=[0.10] * 3, nwc_mode="pct")
    segs = [{"name": "S", "units": 10, "revenue_per_unit": 100,
             "unit_adds": 2, "rpu_growth": 0.0}]
    fc = build_forecast(1000.0, scn, cogs_pct=0.6, nwc_now=100.0, segments=segs)
    assert fc["revenue"].iloc[0] == pytest.approx(1200.0)   # 12 x 100
    assert fc["revenue"].iloc[1] == pytest.approx(1400.0)   # 14 x 100
    assert fc["revenue_growth"].iloc[0] == pytest.approx(0.2)  # vs TTM 1000
    assert fc["ebitda"].iloc[0] == pytest.approx(1200.0 * 0.20)


def test_segment_forecast_accepts_growth_sensitivity_delta():
    from src.modeling.forecast import build_forecast
    from src.modeling.valuation_assumptions import ScenarioAssumptions

    scn = ScenarioAssumptions(
        name="base", revenue_growth=[0.05] * 2, ebitda_margin=[0.20] * 2,
        d_and_a_pct=[0.03] * 2, capex_pct=[0.04] * 2, tax_rate=0.30,
        dso=None, dih=None, dpo=None, nwc_pct_revenue=[0.10] * 2, nwc_mode="pct")
    segs = [{"name": "S", "units": 10, "revenue_per_unit": 100,
             "rpu_growth": 0.05}]
    base = build_forecast(1_000.0, scn, 0.6, 100.0, segments=segs)
    flexed = build_forecast(
        1_000.0, scn, 0.6, 100.0, segments=segs,
        segment_growth_delta=[0.02, 0.02],
    )
    assert flexed["revenue"].iloc[0] > base["revenue"].iloc[0]
    assert flexed["revenue"].iloc[1] > base["revenue"].iloc[1]
