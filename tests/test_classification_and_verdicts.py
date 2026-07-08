import pandas as pd
import pytest

from src.ingestion.classification import apply_classification
from src.modeling.assessment import _verdict, build_assessment, watchlist_summary
from src.modeling.metrics import prepare_monitoring_dataset


def _company(company_id, sector, business_model=None, peer_group=None):
    row = {
        "company_id": company_id,
        "ticker": company_id,
        "company_name": f"Co {company_id}",
        "sector": sector,
        "exchange": "NYSE",
        "currency": "USD",
        "source": "test",
    }
    if business_model is not None:
        row["business_model"] = business_model
    if peer_group is not None:
        row["peer_group"] = peer_group
    return row


def _inputs(companies_rows, n_periods=8, base=100.0):
    periods = pd.date_range("2024-03-31", periods=n_periods, freq="QE")
    fin, mkt = [], []
    for company in companies_rows:
        for idx, period in enumerate(periods):
            revenue = base + idx * 10
            fin.append({
                "company_id": company["company_id"],
                "period": period.date().isoformat(),
                "revenue": revenue,
                "gross_profit": revenue * 0.55,
                "ebitda": revenue * 0.25,
                "ebit": revenue * 0.20,
                "net_income": revenue * 0.12,
                "cfo": revenue * 0.18,
                "capex": revenue * 0.04,
                "fcf": revenue * 0.14,
                "cash": 50,
                "total_debt": 120,
                "net_debt": 70,
                "working_capital": 35,
                "interest_expense": 4,
                "source": "test",
            })
            mkt.append({
                "company_id": company["company_id"],
                "period": period.date().isoformat(),
                "share_price": 10,
                "shares_outstanding": 1000,
                "market_cap": 1000,
                "enterprise_value": 1070,
                "source": "test",
            })
    return {
        "companies": pd.DataFrame(companies_rows),
        "financials": pd.DataFrame(fin),
        "market_data": pd.DataFrame(mkt),
        "estimates": pd.DataFrame(columns=[
            "company_id", "period", "revenue_consensus", "ebitda_consensus",
            "guidance_low", "guidance_high", "source",
        ]),
    }


def test_classification_fallbacks_keep_theme_and_default_model():
    companies = pd.DataFrame([_company("ZZZ_UNMAPPED", "Some Theme")])
    out = apply_classification(companies)
    assert out.loc[0, "theme"] == "Some Theme"
    assert out.loc[0, "peer_group"] == "Some Theme"       # falls back to theme
    assert out.loc[0, "business_model"] == "operating"


def test_classification_respects_explicit_columns():
    companies = pd.DataFrame([_company("ZZZ", "Theme", business_model="financial", peer_group="My Comps")])
    out = apply_classification(companies)
    assert out.loc[0, "peer_group"] == "My Comps"
    assert out.loc[0, "business_model"] == "financial"


def test_ttm_requires_four_quarters():
    df = prepare_monitoring_dataset(_inputs([_company("A", "Theme")]))
    df = df.sort_values("period").reset_index(drop=True)
    assert df.loc[:2, "revenue_ttm"].isna().all()          # partial windows -> NaN
    assert pd.notna(df.loc[3, "revenue_ttm"])
    assert not df.loc[2, "ttm_complete"]
    assert df.loc[3, "ttm_complete"]


def test_financial_business_model_masks_ebitda_framework():
    rows = [
        _company("FIN1", "Credit Theme", business_model="financial"),
        _company("FIN2", "Credit Theme", business_model="financial"),
        _company("FIN3", "Credit Theme", business_model="financial"),
    ]
    df = prepare_monitoring_dataset(_inputs(rows))
    latest = df.sort_values(["company_id", "period"]).groupby("company_id").tail(1)
    assert (latest["ebitda_margin_ttm_signal"] == "n/m").all()
    assert (latest["net_debt_to_ebitda_ttm_signal"] == "n/m").all()
    assert set(latest["net_income_margin_ttm_signal"]) <= {"green", "yellow", "red"}

    a = build_assessment(df, "FIN1")
    labels = [k.label for k in a.kpis]
    assert "P / E" in labels and "Net Income Margin" in labels
    assert "EBITDA Margin" not in labels


def test_verdict_uses_valuation_context():
    signals = {
        "revenue_yoy_growth_signal": "red",
        "ebitda_margin_ttm_signal": "red",
        "fcf_conversion_ttm_signal": "yellow",
        "net_debt_to_ebitda_ttm_signal": "green",
        "business_model": "operating",
    }
    broken_cheap = pd.Series(signals)
    key, rationale = _verdict(broken_cheap, premium=-0.40, multiple_name="EV/EBITDA")
    assert key == "do_work"
    assert "Value trap or entry" in rationale

    key, _ = _verdict(broken_cheap, premium=0.30, multiple_name="EV/EBITDA")
    assert key == "avoid"

    strong = pd.Series({
        "revenue_yoy_growth_signal": "green",
        "ebitda_margin_ttm_signal": "green",
        "fcf_conversion_ttm_signal": "green",
        "net_debt_to_ebitda_ttm_signal": "green",
        "business_model": "operating",
    })
    key, _ = _verdict(strong, premium=-0.30, multiple_name="EV/EBITDA")
    assert key == "do_work"                                 # mispriced quality
    key, _ = _verdict(strong, premium=0.05, multiple_name="EV/EBITDA")
    assert key == "constructive"


def test_watchlist_summary_ranks_do_work_first():
    rows = [
        _company("A", "Theme A"),
        _company("B", "Theme A"),
        _company("C", "Theme B"),
    ]
    df = prepare_monitoring_dataset(_inputs(rows))
    summary = watchlist_summary(df)
    assert len(summary) == 3
    assert list(summary["rank"]) == [1, 2, 3]
    assert {"verdict_label", "theme", "peer_group", "as_of", "flags"} <= set(summary.columns)
    ranks = summary["verdict_key"].map({"do_work": 0, "avoid": 1, "watch": 2, "constructive": 3})
    assert ranks.is_monotonic_increasing


def test_peer_taxonomy_follows_comps_discipline():
    """Guard the IB comps rules on the merged taxonomy (committed demo file +
    private overlay when present): peer groups need >=3 members, and known
    model-mixing mistakes stay fixed. The composition of the private book is
    never committed, so the name-level assertions only run where the overlay
    exists (the analyst's machine)."""
    from src.ingestion.classification import load_classification

    ref = load_classification()
    ref = ref[~ref["company_id"].str.endswith(".SA")]
    if ref.empty:
        pytest.skip("private classification overlay not present - demo file has no non-demo rows")

    sizes = ref.groupby("peer_group")["company_id"].count()
    assert (sizes >= 3).all(), f"peer groups below 3 members: {sizes[sizes < 3].to_dict()}"

    group_of = dict(zip(ref["company_id"], ref["peer_group"]))
    # Brand apparel is never comped against restaurants/marketplaces.
    assert group_of["NASDAQ:LULU"] == group_of["NYSE:NKE"]
    assert group_of["NASDAQ:LULU"] != group_of["NASDAQ:SBUX"]
    assert group_of["NASDAQ:LULU"] != group_of["NASDAQ:ETSY"]
    # S&P Global is not an Adobe comp.
    assert group_of["NYSE:SPGI"] != group_of["NASDAQ:ADBE"]
    # Merchant acquiring is one global business model (STNE comps = GPN, not MELI).
    assert group_of["NASDAQ:STNE"] == group_of["NYSE:GPN"]
    assert group_of["NASDAQ:STNE"] != group_of["NASDAQ:MELI"]
