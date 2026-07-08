"""Tests for valuation chart data builders and figure construction."""

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.ingestion.store import load_store
from src.modeling.valuation_case import build_valuation_case
from src.reporting import valuation_charts as vch


@pytest.fixture(scope="module")
def demo_case():
    store = load_store(demo=True)
    df = pd.read_csv(store.dataset_path, parse_dates=["period"])
    return df, build_valuation_case(df, "TOTS3.SA", store=store)


@pytest.fixture(scope="module")
def auto_case():
    store = load_store(demo=True)
    df = pd.read_csv(store.dataset_path, parse_dates=["period"])
    return build_valuation_case(df, "PRNR3.SA", store=store)


# --- data builders ---------------------------------------------------------------

def test_football_field_ranges(demo_case):
    _, case = demo_case
    data = vch.football_field_data(case)
    assert data["current_price"] and data["current_price"] > 0
    labels = [r["label"] for r in data["ranges"]]
    assert any("DCF" in l for l in labels)
    for r in data["ranges"]:
        assert r["high"] > r["low"] > 0
        if r.get("mid") is not None:
            assert r["low"] <= r["mid"] <= r["high"]
    dcf = next(r for r in data["ranges"] if "DCF" in r["label"])
    scen = case.scenarios
    assert dcf["low"] == pytest.approx(min(s.target_price for s in scen.values()))
    assert dcf["high"] == pytest.approx(max(s.target_price for s in scen.values()))


def test_fcf_bridge_sums_to_ufcf(demo_case):
    _, case = demo_case
    steps = vch.fcf_bridge_data(case.base.forecast)
    # EBITDA - taxes - capex - dNWC must equal the reported UFCF exactly.
    walked = steps[0]["value"] + sum(s["value"] for s in steps[1:-1])
    assert walked == pytest.approx(steps[-1]["value"], rel=1e-9)
    assert steps[-1]["label"] == "UFCF"


def test_equity_bridge_sums(demo_case):
    _, case = demo_case
    steps = vch.equity_bridge_data(case.base)
    ev_step = next(s for s in steps if s["label"] == "Enterprise value")
    assert ev_step["value"] == pytest.approx(case.base.pv_explicit + case.base.pv_terminal_exit, rel=1e-9)
    # Walk from EV through the deductions to implied equity.
    deductions = [s["value"] for s in steps if s["measure"] == "relative" and s["label"] != "PV of terminal value"]
    assert ev_step["value"] + sum(deductions) == pytest.approx(steps[-1]["value"], rel=1e-9)


def test_provenance_classification(demo_case, auto_case):
    _, case = demo_case
    prov = vch.assumptions_provenance(case)
    assert set(prov["source"]) <= {"analyst", "anchored", "default"}
    # TOTS3 demo file sets base scenario + exit multiple -> analyst rows exist.
    assert (prov["source"] == "analyst").any()
    # Default beta is disclosed as default.
    beta_row = prov[prov["item"] == "Beta"].iloc[0]
    assert beta_row["source"] in {"default", "analyst"}

    prov_auto = vch.assumptions_provenance(auto_case)
    # Auto case: no analyst-specified scenarios.
    scen_rows = prov_auto[prov_auto["item"].str.contains("scenario")]
    assert (scen_rows["source"] == "anchored").all()


def test_assumptions_status_labels(demo_case, auto_case):
    _, case = demo_case
    key, label = vch.assumptions_status(case)
    assert key == "illustrative" and "NOT A FINAL VIEW" in label
    key_auto, label_auto = vch.assumptions_status(auto_case)
    assert key_auto == "auto" and "NOT AN INVESTMENT VIEW" in label_auto


# --- figures ------------------------------------------------------------------------

def test_all_figures_build(demo_case):
    df, case = demo_case
    figures = {
        "football": vch.football_field_chart(case),
        "heatmap": vch.sensitivity_heatmap(case),
        "scenarios": vch.scenario_target_chart(case),
        "forecast": vch.forecast_chart(case),
        "fcf_bridge": vch.fcf_bridge_chart(case),
        "equity_bridge": vch.equity_bridge_chart(case),
        "wacc": vch.wacc_build_chart(case),
        "tv": vch.terminal_value_chart(case),
        "quartiles": vch.peer_quartile_panels(case),
    }
    for name, fig in figures.items():
        assert isinstance(fig, go.Figure), name
        assert len(fig.data) >= 1, name


def test_optional_charts_graceful(demo_case):
    df, case = demo_case
    # Demo has synthetic estimates -> revisions chart exists.
    assert vch.revision_momentum_chart(case) is not None
    # Demo has no AR/AP days -> working-capital chart correctly absent.
    assert vch.working_capital_chart(df, case) is None


def test_heatmap_matches_sensitivity_grid(demo_case):
    _, case = demo_case
    fig = vch.sensitivity_heatmap(case)
    z = fig.data[0].z
    assert len(z) == case.sens_wacc_multiple.shape[0]
    assert len(z[0]) == case.sens_wacc_multiple.shape[1]


def test_chart_images_export(demo_case):
    df, case = demo_case
    images = vch.case_chart_images(case, df=df)
    assert len(images) >= 8
    assert all(uri.startswith("data:image/png;base64,") for uri in images.values())
    assert "working_capital" not in images   # None on demo -> skipped
