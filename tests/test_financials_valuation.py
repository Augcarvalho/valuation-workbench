"""Financials-specific valuation: justified P/B and residual income, hand-checked."""

import pandas as pd
import pytest

from src.modeling.financials_valuation import (
    build_financials_valuation,
    excess_return_value,
    justified_pb,
)


def _row(**kw):
    base = {"company_id": "X", "business_model": "financial",
            "market_cap": 1200.0, "net_income_ttm": 120.0, "total_equity": 1000.0}
    base.update(kw)
    return pd.Series(base)


def test_justified_pb_hand_math():
    # ROE 12%, COE 10%, g 4%: (0.12-0.04)/(0.10-0.04) = 1.333x
    assert justified_pb(0.12, 0.10, 0.04) == pytest.approx(4.0 / 3.0)
    assert justified_pb(0.12, 0.04, 0.04) is None          # COE <= g


def test_excess_return_value_hand_math():
    # ROE == COE -> zero excess returns -> value == book.
    v = excess_return_value(book=1000.0, roe=0.10, coe=0.10, growth=0.03)
    assert v == pytest.approx(1000.0)
    # ROE > COE -> value above book; ROE < COE -> below.
    assert excess_return_value(1000.0, 0.14, 0.10, 0.03) > 1000.0
    assert excess_return_value(1000.0, 0.06, 0.10, 0.03) < 1000.0
    assert excess_return_value(1000.0, 0.12, 0.04, 0.04) is None


def test_build_uses_equity_fallback_and_labels_pb():
    out = build_financials_valuation(_row(), cost_of_equity=0.10, growth=0.03)
    assert out.applicable and out.valid
    assert out.book_source == "total_equity"
    assert out.pb_label == "P/B"
    assert any("P/B, not P/TBV" in w for w in out.warnings)
    assert out.roe == pytest.approx(0.12)
    assert out.pe == pytest.approx(10.0)
    assert out.pb == pytest.approx(1.2)
    assert out.justified_pb == pytest.approx((0.12 - 0.03) / (0.10 - 0.03))
    assert out.excess_return_value > 1000.0
    assert out.excess_return_upside is not None


def test_tangible_equity_preferred_and_guardrails():
    out = build_financials_valuation(_row(tangible_common_equity=800.0),
                                     cost_of_equity=0.10, growth=0.03)
    assert out.book_source == "tangible_common_equity" and out.pb_label == "P/TBV"

    neg_book = build_financials_valuation(_row(total_equity=-50.0),
                                          cost_of_equity=0.10, growth=0.03)
    assert not neg_book.valid
    assert any("Negative book" in w for w in neg_book.warnings)

    neg_ni = build_financials_valuation(_row(net_income_ttm=-30.0),
                                        cost_of_equity=0.10, growth=0.03)
    assert neg_ni.pe is None and not neg_ni.valid

    coe_le_g = build_financials_valuation(_row(), cost_of_equity=0.03, growth=0.03)
    assert coe_le_g.justified_pb is None
    assert any("COE <= growth" in w for w in coe_le_g.warnings)


def test_operating_company_not_applicable():
    out = build_financials_valuation(_row(business_model="operating"), cost_of_equity=0.10)
    assert not out.applicable
