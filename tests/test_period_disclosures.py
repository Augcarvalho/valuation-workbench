import pandas as pd
import pytest

from src.reporting.charts import valuation_chart
from src.reporting.periods import (
    financial_period_span,
    peer_metric_basis_note,
    peer_snapshot_context,
    source_as_of,
)


class _Store:
    mode = "private"
    source_log = pd.DataFrame({
        "table_name": ["market_data"],
        "retrieved_at": ["2026-07-08"],
    })


def test_peer_snapshot_discloses_separate_market_and_financial_dates():
    peers = pd.DataFrame({"period": ["2026-03-31", "2026-06-30"]})
    text = peer_snapshot_context(_Store(), peers)
    assert "Market snapshot retrieved 08 Jul 2026" in text
    assert "Financials through Q1 2026 to Q2 2026" in text
    assert financial_period_span(peers) == "Q1 2026 to Q2 2026"
    assert source_as_of(_Store.source_log, "market_data") == "08 Jul 2026"


def test_metric_basis_note_is_explicit():
    note = peer_metric_basis_note()
    assert "latest reported quarter YoY" in note
    assert "= LTM" in note
    assert "exclude the selected company" in note


def test_peer_benchmark_median_excludes_selected_company():
    df = pd.DataFrame({
        "company_id": ["A", "B", "C", "D"],
        "ticker": ["A", "B", "C", "D"],
        "period": pd.to_datetime(["2026-03-31"] * 4),
        "peer_group": ["Software"] * 4,
        "ev_to_ebitda_ttm": [100.0, 10.0, 20.0, 30.0],
    })
    fig = valuation_chart(df, None, "A", peer_ids=["B", "C", "D"])
    median_lines = [shape for shape in fig.layout.shapes if shape.type == "line"]
    assert median_lines
    assert float(median_lines[0].y0) == pytest.approx(20.0)
