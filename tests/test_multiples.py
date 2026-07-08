"""Multi-multiple framework: applicability, NTM guardrails, momentum, outliers."""

import numpy as np
import pandas as pd
import pytest

from src.modeling.comps import comps_spread
from src.modeling.multiples import (
    interpretation,
    momentum_verdict,
    multiple_history,
    multiple_momentum,
    multiple_roles,
    multiples_summary,
    valuation_commentary,
)
from src.modeling.outliers import adjusted_stats, multiple_outlier_reason


def _row(**kw) -> pd.Series:
    base = dict(business_model="operating", peer_group="US Software", sector="Tech",
                ebitda_ttm=500.0, net_income_ttm=300.0, revenue_yoy_growth=0.10,
                ebitda_margin_ttm=0.30, ev_to_revenue_ttm=4.0, ev_to_ebitda_ttm=13.0,
                pe_ttm=20.0, p_tbv=np.nan, share_price=100.0)
    base.update(kw)
    return pd.Series(base)


# --- applicability by business model -----------------------------------------

def test_mature_operating_roles():
    roles = multiple_roles(_row())
    assert roles["ev_to_ebitda_ttm"]["role"] == "primary"
    assert roles["pe_ttm"]["role"] == "secondary"
    assert roles["ev_to_revenue_ttm"]["role"] == "cross-check"
    assert roles["p_tbv"]["role"] == "not_meaningful"


def test_negative_ebitda_promotes_ev_revenue():
    roles = multiple_roles(_row(ebitda_ttm=-50.0, net_income_ttm=-80.0))
    assert roles["ev_to_revenue_ttm"]["role"] == "primary"
    assert roles["ev_to_ebitda_ttm"]["role"] == "not_meaningful"
    assert roles["pe_ttm"]["role"] == "not_meaningful"


def test_high_growth_thin_margin_prefers_ev_revenue():
    roles = multiple_roles(_row(revenue_yoy_growth=0.45, ebitda_margin_ttm=0.05))
    assert roles["ev_to_revenue_ttm"]["role"] == "primary"
    assert roles["ev_to_ebitda_ttm"]["role"] == "secondary"


def test_consumer_gets_dual_primary():
    roles = multiple_roles(_row(peer_group="US Apparel & Footwear Brands"))
    assert roles["ev_to_ebitda_ttm"]["role"] == "primary"
    assert roles["pe_ttm"]["role"] == "primary"
    assert roles["ev_to_revenue_ttm"]["role"] == "cross-check"


def test_financial_never_forces_ev_framework():
    roles = multiple_roles(_row(business_model="financial", p_tbv=1.8))
    assert roles["pe_ttm"]["role"] == "primary"
    assert roles["p_tbv"]["role"] == "primary"
    assert roles["ev_to_ebitda_ttm"]["role"] == "not_meaningful"
    assert roles["ev_to_revenue_ttm"]["role"] == "not_meaningful"


def test_financial_negative_earnings_pe_not_meaningful():
    roles = multiple_roles(_row(business_model="financial", net_income_ttm=-10.0, p_tbv=0.9))
    assert roles["pe_ttm"]["role"] == "not_meaningful"


# --- NTM multiples (comps_spread) ---------------------------------------------

def _peers(n=6, **overrides) -> pd.DataFrame:
    df = pd.DataFrame({
        "company_id": [f"c{i}" for i in range(n)],
        "ticker": [f"T{i}" for i in range(n)],
        "company_name": [f"Peer {i}" for i in range(n)],
        "share_price": [100.0] * n,
        "market_cap": [1000.0] * n,
        "enterprise_value": [1200.0] * n,
        "net_debt": [200.0] * n,
        "revenue_ttm": [400.0] * n,
        "ebitda_ttm": [100.0] * n,
        "net_income_ttm": [60.0] * n,
        "revenue_yoy_growth": [0.1] * n,
        "ebitda_margin_ttm": [0.25] * n,
        "ev_to_revenue_ttm": [3.0, 3.5, 4.0, 4.5, 5.0, 60.0][:n],
        "ev_to_ebitda_ttm": [10.0, 12.0, 14.0, 16.0, 18.0, 120.0][:n],
        "pe_ttm": [15.0, 18.0, 21.0, 24.0, 27.0, 150.0][:n],
        "p_tbv": [np.nan] * n,
        "eps_est_ntm": [5.0, 4.0, -1.0, 0.0, np.nan, 2.0][:n],
        "revenue_est_ntm": [450.0] * n,
        "ebitda_est_ntm": [110.0] * n,
    })
    for k, v in overrides.items():
        df[k] = v
    return df


def test_pe_ntm_guardrails_negative_zero_missing():
    spread = comps_spread(_peers())
    pe = spread.set_index("ticker")["pe_ntm"]
    assert pe["T0"] == pytest.approx(20.0)          # 100 / 5
    assert np.isnan(pe["T2"])                       # negative EPS -> N/M
    assert np.isnan(pe["T3"])                       # zero EPS -> N/M
    assert np.isnan(pe["T4"])                       # missing EPS -> N/M


def test_ev_ntm_multiples_computed():
    spread = comps_spread(_peers())
    assert spread["ev_to_ebitda_ntm"].iloc[0] == pytest.approx(1200.0 / 110.0)
    assert spread["ev_to_revenue_ntm"].iloc[0] == pytest.approx(1200.0 / 450.0)


# --- outlier handling -----------------------------------------------------------

def test_extreme_multiples_flagged():
    assert multiple_outlier_reason("ev_to_ebitda_ttm", 120.0)
    assert multiple_outlier_reason("pe_ttm", 150.0)
    assert multiple_outlier_reason("pe_ntm", 150.0)
    assert multiple_outlier_reason("p_tbv", -0.5)
    assert multiple_outlier_reason("ev_to_ebitda_ttm", 20.0) is None


def test_adjusted_median_excludes_negative_and_extreme():
    spread = _peers()
    s = adjusted_stats(spread, "pe_ttm")
    # raw median includes the 150x print; adjusted excludes it.
    assert s["raw_median"] == pytest.approx(np.median([15, 18, 21, 24, 27, 150]))
    assert s["adjusted_median"] == pytest.approx(21.0)
    assert s["n_excluded"] == 1


# --- summary + interpretation -----------------------------------------------------

def test_summary_premium_and_labels():
    row = _row(ev_to_ebitda_ttm=10.0)
    summary = multiples_summary(row, _peers(), "anchor")
    ev = next(m for m in summary if m["metric"] == "ev_to_ebitda_ttm")
    assert ev["role"] == "primary"
    assert ev["peer_median"] == pytest.approx(14.0)   # adjusted (120x excluded)
    assert ev["premium"] == pytest.approx(10.0 / 14.0 - 1.0)
    assert ev["interpretation"] == "cheap"            # -29% < -15%


def test_interpretation_labels():
    assert interpretation(None, None, "primary", None) == "not meaningful"
    assert interpretation(10.0, -0.2, "primary", None) == "cheap"
    assert interpretation(10.0, 0.2, "primary", None) == "expensive"
    assert interpretation(10.0, 0.0, "primary", None) == "fair"
    assert interpretation(120.0, 0.0, "primary", "extreme multiple") == "distorted"


# --- history + momentum ------------------------------------------------------------

def _history(trend_anchor=1.0, trend_peers=1.0, n=24) -> pd.DataFrame:
    dates = pd.date_range("2024-01-31", periods=n, freq="ME")
    rows = []
    for cid, base, trend in [("anchor", 10.0, trend_anchor), ("p1", 12.0, trend_peers),
                             ("p2", 14.0, trend_peers), ("p3", 16.0, trend_peers),
                             ("p4", 18.0, trend_peers)]:
        for i, d in enumerate(dates):
            mult = base * (trend ** (i / (n - 1)))
            rows.append({"company_id": cid, "date": d, "share_price": 5.0 * mult,
                         "ev_to_ebitda_ltm": mult, "pe_ltm": mult * 1.5,
                         "ev_to_revenue_ltm": mult / 3})
    return pd.DataFrame(rows)


def test_historical_percentile_ranks_current():
    vh = _history(trend_anchor=2.0)  # anchor doubles -> current is its max
    mom = multiple_momentum(vh, "anchor", ["anchor", "p1", "p2", "p3", "p4"], "ev_to_ebitda_ltm")
    assert mom["available"]
    assert mom["percentile"] > 0.9
    assert mom["chg"][12] is not None and mom["chg"][12] > 0.3


def test_momentum_company_specific_rerating():
    vh = _history(trend_anchor=2.0, trend_peers=1.0)
    mom = multiple_momentum(vh, "anchor", ["anchor", "p1", "p2", "p3", "p4"], "ev_to_ebitda_ltm")
    assert "re-rating" in mom["verdict"] and "company-specific" in mom["verdict"]


def test_momentum_sector_driven():
    vh = _history(trend_anchor=1.6, trend_peers=1.6)
    mom = multiple_momentum(vh, "anchor", ["anchor", "p1", "p2", "p3", "p4"], "ev_to_ebitda_ltm")
    assert "sector-driven" in mom["verdict"]


def test_momentum_verdict_rules():
    assert momentum_verdict(None, None) == "insufficient history"
    assert momentum_verdict(0.02, 0.0) == "stable multiple"
    assert momentum_verdict(-0.3, -0.25) == "de-rating - company-specific"
    assert momentum_verdict(0.3, 0.01) == "re-rating - sector-driven"


def test_multiple_history_drops_negative_observations():
    vh = _history()
    vh.loc[vh.index[:3], "ev_to_ebitda_ltm"] = -5.0
    hist = multiple_history(vh, "anchor", ["anchor", "p1", "p2", "p3", "p4"], "ev_to_ebitda_ltm")
    assert hist["available"]
    assert (hist["company"]["value"] > 0).all()


# --- commentary ---------------------------------------------------------------------

def test_commentary_negative_earnings_redirect():
    row = _row(ebitda_ttm=-50.0, net_income_ttm=-80.0, pe_ttm=np.nan)
    summary = multiples_summary(row, _peers(), "anchor")
    notes = valuation_commentary(summary, {}, row)
    assert any("not meaningful" in n and "EV / Revenue" in n for n in notes)
