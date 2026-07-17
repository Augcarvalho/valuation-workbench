import pandas as pd

from src.modeling.metrics import prepare_monitoring_dataset, safe_divide


def _inputs():
    companies = pd.DataFrame(
        [
            {
                "company_id": "A",
                "ticker": "A",
                "company_name": "Alpha",
                "sector": "Software-Enabled Services",
                "exchange": "B3",
                "currency": "BRL",
                "source": "test",
            },
            {
                "company_id": "B",
                "ticker": "B",
                "company_name": "Beta",
                "sector": "Software-Enabled Services",
                "exchange": "B3",
                "currency": "BRL",
                "source": "test",
            },
        ]
    )
    periods = pd.date_range("2023-03-31", periods=5, freq="QE")
    rows = []
    market = []
    for company_id, base in [("A", 100), ("B", 90)]:
        for idx, period in enumerate(periods):
            revenue = base + idx * 10
            ebitda = revenue * 0.25
            rows.append(
                {
                    "company_id": company_id,
                    "period": period.date().isoformat(),
                    "revenue": revenue,
                    "gross_profit": revenue * 0.55,
                    "ebitda": ebitda,
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
                }
            )
            market.append(
                {
                    "company_id": company_id,
                    "period": period.date().isoformat(),
                    "share_price": 10,
                    "shares_outstanding": 1000,
                    "market_cap": 1000,
                    "enterprise_value": 1070,
                    "source": "test",
                }
            )
    return {
        "companies": companies,
        "financials": pd.DataFrame(rows),
        "market_data": pd.DataFrame(market),
        "estimates": pd.DataFrame(
            columns=[
                "company_id",
                "period",
                "revenue_consensus",
                "ebitda_consensus",
                "guidance_low",
                "guidance_high",
                "source",
            ]
        ),
    }


def test_safe_divide_handles_zero_denominator():
    result = safe_divide(pd.Series([1, 2, 3]), pd.Series([1, 0, 3]))
    assert result.iloc[0] == 1
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 1


def test_prepare_monitoring_dataset_calculates_ttm_and_growth():
    df = prepare_monitoring_dataset(_inputs())
    latest = df[(df["company_id"] == "A") & (df["period"] == pd.Timestamp("2024-03-31"))].iloc[0]

    assert latest["revenue_ttm"] == 110 + 120 + 130 + 140
    assert round(latest["revenue_yoy_growth"], 4) == 0.4
    assert round(latest["ebitda_margin_ttm"], 4) == 0.25
    assert round(latest["fcf_conversion_ttm"], 4) == 0.56
    assert round(latest["net_debt_to_ebitda_ttm"], 4) == round(70 / latest["ebitda_ttm"], 4)


def test_monitoring_dataset_adds_peer_percentiles_and_signals():
    df = prepare_monitoring_dataset(_inputs())
    latest = df[df["period"] == pd.Timestamp("2024-03-31")]

    assert "ev_to_ebitda_ttm_peer_pct" in latest.columns
    assert "revenue_yoy_growth_signal" in latest.columns
    assert latest["data_quality_score"].min() == 1.0


def test_ttm_requires_four_consecutive_quarters():
    inputs = _inputs()
    fin = inputs["financials"]
    market = inputs["market_data"]
    missing_period = "2023-09-30"
    inputs["financials"] = fin[~((fin["company_id"] == "A") & (fin["period"] == missing_period))]
    inputs["market_data"] = market[~((market["company_id"] == "A") & (market["period"] == missing_period))]
    df = prepare_monitoring_dataset(inputs)
    latest = df[df["company_id"] == "A"].sort_values("period").iloc[-1]
    assert not bool(latest["ttm_complete"])
    assert pd.isna(latest["revenue_ttm"])


def test_operating_nwc_excludes_non_operating_current_items():
    inputs = _inputs()
    inputs["financials"]["ar"] = 40.0
    inputs["financials"]["inventory"] = 10.0
    inputs["financials"]["ap"] = 25.0
    df = prepare_monitoring_dataset(inputs)
    latest = df[df["company_id"] == "A"].sort_values("period").iloc[-1]
    assert latest["operating_nwc"] == 25.0
    assert latest["working_capital"] == 35.0
