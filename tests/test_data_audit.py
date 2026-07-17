"""Data Audit checks: each rule verified on synthetic rows with known defects."""

import pandas as pd

from src.modeling.data_audit import (
    audit_scores,
    check_ev_bridge,
    check_market_cap_bridge,
    check_refresh_consistency,
    check_sign_conventions,
    check_stale_periods,
    check_ttm_completeness,
    check_unit_sanity,
    run_audit,
)


def _row(**kw):
    base = {"company_id": "X:TEST", "ticker": "TEST", "period": pd.Timestamp("2026-03-31"),
            "business_model": "operating"}
    base.update(kw)
    return base


def test_market_cap_bridge_tolerances():
    # shares in units, mcap in millions: 10 x 100m shares = 1,000m
    clean = pd.DataFrame([_row(share_price=10.0, shares_outstanding=100e6, market_cap=1000.0)])
    assert check_market_cap_bridge(clean) == []
    off = pd.DataFrame([_row(share_price=10.0, shares_outstanding=100e6, market_cap=1400.0)])
    issues = check_market_cap_bridge(off)
    assert issues and issues[0]["severity"] == "medium"        # ~29% gap
    worse = pd.DataFrame([_row(share_price=10.0, shares_outstanding=100e6, market_cap=2000.0)])
    assert check_market_cap_bridge(worse)[0]["severity"] == "high"
    off2 = pd.DataFrame([_row(share_price=10.0, shares_outstanding=100e6, market_cap=1100.0)])
    assert check_market_cap_bridge(off2)[0]["severity"] == "low"


def test_ev_bridge_partial_and_gap():
    row = _row(market_cap=1000.0, enterprise_value=1150.0, total_debt=200.0, cash=50.0)
    issues = check_ev_bridge(pd.DataFrame([row]))
    assert issues == []                                       # calc = 1150 exact
    row_bad = _row(market_cap=1000.0, enterprise_value=2000.0, total_debt=200.0, cash=50.0)
    issues = check_ev_bridge(pd.DataFrame([row_bad]))
    assert issues[0]["severity"] == "high" and "partial bridge" in issues[0]["detail"]


def test_unit_sanity_catches_currency_mix():
    row = _row(market_cap=5_000_000.0, revenue_ttm=800.0)     # 6,250x
    issues = check_unit_sanity(pd.DataFrame([row]))
    assert issues and issues[0]["severity"] == "high"


def test_sign_convention_flags_not_flips():
    row = _row(cfo_ttm=100.0, capex_ttm=-30.0, fcf_ttm=70.0)
    issues = check_sign_conventions(pd.DataFrame([row]))
    assert any("negative" in i["detail"] for i in issues)      # flagged
    row2 = _row(cfo_ttm=100.0, capex_ttm=30.0, fcf_ttm=70.0)
    assert check_sign_conventions(pd.DataFrame([row2])) == []  # consistent
    row3 = _row(cfo_ttm=100.0, capex_ttm=30.0, fcf_ttm=20.0)
    issues3 = check_sign_conventions(pd.DataFrame([row3]))
    assert any("!=" in i["detail"] for i in issues3)


def test_ttm_completeness_and_financial_masking():
    df = pd.DataFrame([_row(period=pd.Timestamp(p)) for p in
                       ("2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31")])
    latest = pd.DataFrame([_row(revenue_ttm=100.0, net_income_ttm=10.0,
                                ebitda_ttm=None, cfo_ttm=None)])
    issues = check_ttm_completeness(df, latest)
    assert issues and issues[0]["severity"] == "medium"
    fin = pd.DataFrame([_row(business_model="financial", revenue_ttm=100.0,
                             net_income_ttm=10.0)])
    fin_issues = check_ttm_completeness(df, fin)
    assert all(i["severity"] in ("low", "info") for i in fin_issues)

    short = df.iloc[:2]
    short_latest = pd.DataFrame([_row()])
    si = check_ttm_completeness(short, short_latest)
    assert si and si[0]["severity"] == "high"


def test_stale_periods_use_dates():
    latest = pd.DataFrame([
        _row(company_id="A", period=pd.Timestamp("2026-06-30")),
        _row(company_id="B", period=pd.Timestamp("2026-03-31")),
        _row(company_id="C", period=pd.Timestamp("2025-09-30")),
    ])
    issues = check_stale_periods(latest)
    by_id = {i["company_id"]: i for i in issues}
    assert "A" not in by_id
    assert "B" not in by_id  # one normalized calendar quarter is not enough to call stale
    assert by_id["C"]["severity"] == "high"


def test_refresh_log_mismatch_detected():
    latest = pd.DataFrame([_row(company_id=f"C{i}") for i in range(66)])
    exports = {"financials": pd.DataFrame({"company_id": [f"C{i}" for i in range(66)]})}
    log = pd.DataFrame([{"companies": 62, "financial_rows": 1240,
                         "market_rows": 62, "estimate_rows": 62, "valuation_rows": 2232}])
    issues = check_refresh_consistency(latest, exports, log)
    assert any(i["check"] == "refresh_consistency" and "62" in i["detail"] for i in issues)


def test_run_audit_and_scores_shape():
    df = pd.DataFrame([_row(period=pd.Timestamp(p)) for p in
                       ("2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31")])
    latest = pd.DataFrame([_row(share_price=10.0, shares_outstanding=100e6, market_cap=1400.0,
                                enterprise_value=2000.0, total_debt=200.0, cash=50.0,
                                revenue_ttm=100.0, net_income_ttm=10.0, ebitda_ttm=20.0,
                                cfo_ttm=15.0, capex_ttm=5.0, fcf_ttm=10.0)])
    issues = run_audit(df, latest)
    assert not issues.empty
    assert set(issues.columns) == {"company_id", "ticker", "check", "severity",
                                   "source_table", "detail", "value"}
    scores = audit_scores(issues, latest)
    assert 0 <= scores["score"].iloc[0] < 100
