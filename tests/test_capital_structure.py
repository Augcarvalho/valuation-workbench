"""Capital structure / debt capacity: hand-checked math + gates."""

import pandas as pd
import pytest

from src.modeling.capital_structure import build_capital_structure


def _row(**kw):
    base = {"company_id": "X", "business_model": "operating",
            "total_debt": 300.0, "cash": 100.0, "net_debt": 200.0,
            "ebitda_ttm": 100.0, "interest_expense_ttm": 20.0,
            "market_cap": 1000.0, "enterprise_value": 1200.0}
    base.update(kw)
    return pd.Series(base)


def test_debt_capacity_hand_math():
    cs = build_capital_structure(_row())
    assert cs.applicable
    assert cs.net_leverage == pytest.approx(2.0)          # 200/100
    assert cs.gross_leverage == pytest.approx(3.0)
    assert cs.interest_coverage == pytest.approx(5.0)     # 100/20
    assert cs.capacity[3.0] == pytest.approx(300.0)
    assert cs.incremental[3.0] == pytest.approx(100.0)    # 300 - 200
    assert cs.incremental[2.0] == pytest.approx(0.0)
    assert cs.leverage_headroom == pytest.approx(2.0)     # 4.0x covenant - 2.0x
    assert cs.coverage_headroom == pytest.approx(3.0)     # 5.0 - 2.0 floor
    assert cs.sponsor_capacity == pytest.approx(200.0)    # 4x100 - 200
    assert cs.ltv == pytest.approx(200.0 / 1200.0)


def test_financial_company_not_meaningful():
    cs = build_capital_structure(_row(business_model="financial"))
    assert not cs.applicable
    assert any("not meaningful" in w for w in cs.warnings)


def test_negative_ebitda_and_net_cash_warnings():
    cs = build_capital_structure(_row(ebitda_ttm=-10.0))
    assert cs.applicable and cs.net_leverage is None
    assert any("negative" in w.lower() for w in cs.warnings)

    net_cash = build_capital_structure(_row(total_debt=50.0, cash=300.0, net_debt=-250.0))
    assert any("Net cash" in w for w in net_cash.warnings)
    assert net_cash.incremental[2.0] == pytest.approx(450.0)   # 200 - (-250)


def test_missing_interest_flagged():
    cs = build_capital_structure(_row(interest_expense_ttm=None))
    assert cs.interest_coverage is None
    assert any("Interest expense" in w for w in cs.warnings)


def test_ev_bridge_prefers_cash_st_invest_basis():
    """CapIQ TEV subtracts cash & ST investments; the bridge must match."""
    import pandas as pd

    from src.modeling.capital_structure import ev_bridge

    row = pd.Series({"market_cap": 1000.0, "total_debt": 200.0, "cash": 50.0,
                     "cash_st_invest": 180.0, "minority_interest": 10.0,
                     "preferred_equity": 5.0, "enterprise_value": 1035.0})
    b = ev_bridge(row)
    assert b["cash"] == 180.0
    assert b["cash_basis"] == "cash & ST investments"
    assert b["calculated_ev"] == pytest.approx(1035.0)
    assert not b["mismatch"] and not b["partial"]

    fallback = ev_bridge(row.drop("cash_st_invest"))
    assert fallback["cash"] == 50.0
    assert "equivalents" in fallback["cash_basis"]
