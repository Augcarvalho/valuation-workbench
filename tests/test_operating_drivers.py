from __future__ import annotations

import pandas as pd
import pytest

from src.app.operating_driver_view import _projection_chart
from src.modeling.operating_drivers import (
    COMPANY_PROFILE,
    PROFILES,
    build_operating_driver_model,
    operating_driver_payload,
    profile_for,
    reconcile_operating_kpis,
)
from scripts.generate_operating_kpi_queue import build_queue


def _kpis() -> pd.DataFrame:
    rows = []
    values = {
        "store_count_total": [("2023-01-01", 100), ("2024-01-01", 110), ("2025-01-01", 120)],
        "revenue_store_channel": [("2023-01-01", 500), ("2024-01-01", 560), ("2025-01-01", 600)],
        "revenue_ecommerce": [("2023-01-01", 300), ("2024-01-01", 330), ("2025-01-01", 360)],
        "revenue_other_channels": [("2023-01-01", 100), ("2024-01-01", 110), ("2025-01-01", 120)],
    }
    for metric, observations in values.items():
        for period, value in observations:
            rows.append({
                "company_id": "NASDAQ:LULU",
                "period": period,
                "fiscal_period": period[:4],
                "metric_id": metric,
                "metric_label": metric,
                "value": value,
                "unit": "count" if metric == "store_count_total" else "USDm",
                "scope": "Consolidated",
                "period_type": "annual",
                "data_type": "actual",
                "source_type": "company_filing",
                "source_name": "test filing",
                "source_url": "https://example.com",
                "retrieved_at": "2026-01-01",
                "definition": metric,
            })
    return pd.DataFrame(rows)


def test_physical_driver_build_reconciles_to_scenario_growth():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {
        "bear": [-0.05, 0.00, 0.01],
        "base": [0.02, 0.03, 0.03],
        "bull": [0.06, 0.06, 0.04],
    }
    build = build_operating_driver_model(row, _kpis(), pd.DataFrame(), growth, {}, 3)
    assert build.tier == 3
    assert build.coverage_pct == 1.0
    assert [segment["name"] for segment in build.segments] == [
        "Stores", "E-commerce", "Other channels"
    ]
    base = build.projection[build.projection["scenario"] == "base"]
    assert base["revenue_growth"].tolist() == pytest.approx(growth["base"])
    assert base.iloc[0]["ending_stores"] > base.iloc[0]["average_stores"]


def test_manual_physical_drivers_become_the_revenue_source():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {name: [0.02, 0.02, 0.02] for name in ("bear", "base", "bull")}
    raw = {
        "calibrate_to_consolidated": False,
        "scenarios": {
            name: {
                "net_store_adds": 0,
                "store_productivity_growth": 0.0,
                "ecommerce_growth": 0.0,
                "other_growth": 0.0,
            }
            for name in growth
        },
    }
    build = build_operating_driver_model(row, _kpis(), pd.DataFrame(), growth, raw, 3)
    assert build.status == "manual driver case"
    assert build.projection["revenue_growth"].abs().max() == pytest.approx(0.0)


def test_incomplete_physical_coverage_falls_back_to_reported_segments():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    incomplete = _kpis().query("metric_id != 'revenue_other_channels'")
    segments = pd.DataFrame([
        {"company_id": "NASDAQ:LULU", "segment": "A", "latest_fy": 2025, "revenue_usd": 700, "cagr_3y": 0.1},
        {"company_id": "NASDAQ:LULU", "segment": "B", "latest_fy": 2025, "revenue_usd": 500, "cagr_3y": 0.05},
    ])
    growth = {name: [0.02] * 3 for name in ("bear", "base", "bull")}
    build = build_operating_driver_model(row, incomplete, segments, growth, {}, 3)
    assert build.tier == 2
    assert "revenue_other_channels" in build.missing_metrics


def test_capital_iq_and_filing_values_are_reconciled_not_overwritten():
    frame = _kpis().head(1)
    capiq = frame.copy()
    capiq["source_type"] = "capital_iq_excel"
    capiq["value"] = frame["value"] * 1.005
    reconciled = reconcile_operating_kpis(pd.concat([frame, capiq], ignore_index=True))
    assert reconciled.iloc[0]["status"] == "matched"
    assert reconciled.iloc[0]["difference_pct"] == pytest.approx(0.005)


def test_every_watchlist_company_has_an_explicit_driver_architecture():
    assert len(COMPANY_PROFILE) == 26
    assert set(COMPANY_PROFILE.values()).issubset(PROFILES)
    assert all(profile_for(company_id).model_id == profile_id
               for company_id, profile_id in COMPANY_PROFILE.items())


def test_store_revenue_uses_average_not_ending_store_count():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {name: [0.02, 0.02] for name in ("bear", "base", "bull")}
    raw = {
        "calibrate_to_consolidated": False,
        "scenarios": {
            name: {
                "net_store_adds": [20, 30],
                "store_productivity_growth": [0.0, 0.0],
                "ecommerce_growth": [0.0, 0.0],
                "other_growth": [0.0, 0.0],
            }
            for name in growth
        },
    }
    build = build_operating_driver_model(row, _kpis(), pd.DataFrame(), growth, raw, 2)
    base = build.projection[build.projection["scenario"] == "base"].reset_index(drop=True)
    assert base.loc[0, "average_stores"] == pytest.approx(130.0)
    assert base.loc[0, "ending_stores"] == pytest.approx(140.0)
    assert base.loc[1, "average_stores"] == pytest.approx(155.0)
    assert base.loc[1, "ending_stores"] == pytest.approx(170.0)


def test_operating_kpi_queue_preserves_reviewed_formula_builder_mnemonics(tmp_path):
    output = tmp_path / "operating_kpi_config.csv"
    pd.DataFrame([{
        "company_id": "NASDAQ:LULU",
        "period": "2026-05-03",
        "fiscal_period": "Q1 FY2026",
        "metric_id": "comparable_sales_growth",
        "metric_label": "Comparable sales growth",
        "capiq_mnemonic": "IQ_SAME_STORE",
        "period_code": "IQ_FQ",
        "unit": "percentage",
        "scope": "Consolidated",
        "period_type": "quarterly",
        "data_type": "actual",
        "definition": "Reviewed in Capital IQ Formula Builder",
    }]).to_csv(output, index=False)

    queue = build_queue(output)
    reviewed = next(
        row for row in queue
        if row["company_id"] == "NASDAQ:LULU"
        and row["metric_id"] == "comparable_sales_growth"
    )
    assert reviewed["capiq_mnemonic"] == "IQ_SAME_STORE"
    assert reviewed["period_code"] == "IQ_FQ"
    assert len(queue) == 161


def test_manual_driver_tail_converges_to_terminal_growth_without_rewriting_explicit_years():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {
        name: [0.0, 0.0, 0.03, 0.025]
        for name in ("bear", "base", "bull")
    }
    raw = {
        "calibrate_to_consolidated": False,
        "scenarios": {
            name: {
                "net_store_adds": [0, 0],
                "store_productivity_growth": [0.10, 0.10],
                "ecommerce_growth": [0.10, 0.10],
                "other_growth": [0.10, 0.10],
            }
            for name in growth
        },
    }
    build = build_operating_driver_model(row, _kpis(), pd.DataFrame(), growth, raw, 4)
    base = build.projection[build.projection["scenario"] == "base"].reset_index(drop=True)
    assert base.loc[:1, "revenue_growth"].tolist() == pytest.approx([0.10, 0.10])
    assert base.loc[2:, "revenue_growth"].tolist() == pytest.approx([0.03, 0.025])


def test_operating_driver_fingerprint_changes_with_manual_driver_output():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {name: [0.02, 0.02] for name in ("bear", "base", "bull")}

    def build(adds: int):
        raw = {
            "calibrate_to_consolidated": False,
            "scenarios": {
                name: {
                    "net_store_adds": [adds, adds],
                    "store_productivity_growth": [0.0, 0.0],
                    "ecommerce_growth": [0.0, 0.0],
                    "other_growth": [0.0, 0.0],
                }
                for name in growth
            },
        }
        return build_operating_driver_model(
            row, _kpis(), pd.DataFrame(), growth, raw, 2
        )

    assert operating_driver_payload(build(5)) != operating_driver_payload(build(10))


def test_projection_chart_reserves_space_for_legend_and_growth_labels():
    row = pd.Series({"company_id": "NASDAQ:LULU", "revenue_ttm": 1200.0})
    growth = {name: [0.02, 0.03, 0.025] for name in ("bear", "base", "bull")}
    build = build_operating_driver_model(
        row, _kpis(), pd.DataFrame(), growth, {}, 3
    )

    fig = _projection_chart(build, "base", "USD", explicit_years=3)

    assert fig.layout.height >= 440
    assert fig.layout.margin.b >= 80
    assert fig.layout.legend.y < 0
    assert fig.layout.legend.yanchor == "top"
    assert all("Y%{x}" not in (trace.hovertemplate or "") for trace in fig.data)
