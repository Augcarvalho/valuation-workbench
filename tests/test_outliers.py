"""Outlier rules and adjusted-median math."""

import pandas as pd
import pytest

from src.modeling.comps import comps_spread, quartile_stats
from src.modeling.outliers import adjusted_stats, multiple_outlier_reason


def test_multiple_outlier_rules():
    assert multiple_outlier_reason("ev_to_ebitda_ttm", -3.0) == "negative EBITDA"
    assert "extreme" in multiple_outlier_reason("ev_to_ebitda_ttm", 120.0)
    assert multiple_outlier_reason("ev_to_ebitda_ttm", 12.0) is None
    assert multiple_outlier_reason("pe_ttm", -5.0) == "negative earnings"
    assert "extreme" in multiple_outlier_reason("pe_ttm", 150.0)
    assert "extreme" in multiple_outlier_reason("ev_to_revenue_ttm", 80.0)


def test_adjusted_median_excludes_and_reports():
    spread = pd.DataFrame({
        "ticker": ["A", "B", "C", "D", "E"],
        "ev_to_ebitda_ttm": [8.0, 10.0, 12.0, 300.0, -6.0],
    })
    s = adjusted_stats(spread, "ev_to_ebitda_ttm")
    assert s["raw_median"] == pytest.approx(10.0)       # all five
    assert s["adjusted_median"] == pytest.approx(10.0)  # A/B/C only
    assert s["n_valid"] == 5 and s["n_excluded"] == 2
    reasons = dict(s["excluded"])
    assert "extreme" in reasons["D"] and reasons["E"] == "negative EBITDA"


def test_quartile_stats_carries_adjusted_median():
    peers = pd.DataFrame({
        "company_id": ["A", "B", "C", "D"],
        "ticker": ["A", "B", "C", "D"],
        "company_name": ["A", "B", "C", "D"],
        "market_cap": [100.0] * 4,
        "enterprise_value": [120.0] * 4,
        "revenue_yoy_growth": [0.1] * 4,
        "ebitda_margin_ttm": [0.2] * 4,
        "ev_to_revenue_ttm": [2.0] * 4,
        "ev_to_ebitda_ttm": [8.0, 10.0, 12.0, 400.0],
        "pe_ttm": [15.0, 18.0, -4.0, 22.0],
    })
    spread = comps_spread(peers, estimates=None)
    stats = quartile_stats(spread)
    assert stats.loc["ev_to_ebitda_ttm", "adjusted_median"] == pytest.approx(10.0)
    assert stats.loc["ev_to_ebitda_ttm", "n_excluded"] == 1
    assert stats.loc["pe_ttm", "adjusted_median"] == pytest.approx(18.0)  # -4 excluded


def test_fy_forward_columns_na_without_export():
    peers = pd.DataFrame({
        "company_id": ["A"], "ticker": ["A"], "company_name": ["A"],
        "market_cap": [100.0], "enterprise_value": [120.0], "share_price": [10.0],
        "revenue_yoy_growth": [0.1], "ebitda_margin_ttm": [0.2],
        "ev_to_revenue_ttm": [2.0], "ev_to_ebitda_ttm": [8.0], "pe_ttm": [15.0],
    })
    spread = comps_spread(peers, estimates=None)
    assert spread["ev_to_ebitda_fy1"].isna().all()      # never faked
    assert spread["pe_fy2"].isna().all()

    est = pd.DataFrame({"company_id": ["A"], "ebitda_est_fy1": [20.0],
                        "eps_est_fy1": [2.0]})
    spread2 = comps_spread(peers, estimates=est)
    assert spread2["ev_to_ebitda_fy1"].iloc[0] == pytest.approx(6.0)   # 120/20
    assert spread2["pe_fy1"].iloc[0] == pytest.approx(5.0)             # 10/2
