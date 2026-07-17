"""Consensus beat/miss and revision math with graceful degradation."""

import pandas as pd
import pytest

from src.modeling.consensus import build_consensus_read


def _row(**kw):
    base = {"company_id": "X"}
    base.update(kw)
    return pd.Series(base)


def test_current_fq_comparison_is_not_labeled_beat_miss():
    out = build_consensus_read(_row(revenue=110.0, revenue_consensus=100.0,
                                    ebitda=18.0, ebitda_consensus=20.0))
    by = {r["metric"]: r for r in out.rows}
    assert by["Revenue"]["status"] == "above estimate"
    assert by["Revenue"]["delta_pct"] == pytest.approx(0.10)
    assert by["EBITDA"]["status"] == "below estimate"
    assert by["EBITDA"]["delta"] == pytest.approx(-2.0)
    assert not out.true_surprise


def test_matched_pre_report_consensus_enables_beat_miss():
    out = build_consensus_read(_row(
        period="2026-03-31", consensus_period="2026-03-31",
        consensus_basis="pre_report", revenue=110.0, revenue_consensus=100.0,
    ))
    assert out.true_surprise
    assert out.rows[0]["status"] == "beat"


def test_revisions_30_90():
    out = build_consensus_read(_row(
        revenue_est_ntm=105.0, revenue_est_ntm_30d_ago=100.0, revenue_est_ntm_90d_ago=110.0,
        eps_est_ntm=2.0, eps_est_ntm_30d_ago=2.0))
    assert out.revisions["revenue"]["d30"] == pytest.approx(0.05)
    assert out.revisions["revenue"]["d90"] == pytest.approx(105.0 / 110.0 - 1.0)
    assert out.revisions["eps"]["d30"] == pytest.approx(0.0)
    assert out.revisions["eps"]["d90"] is None


def test_guidance_midpoint_vs_consensus():
    out = build_consensus_read(_row(guidance_low=95.0, guidance_high=105.0,
                                    revenue_consensus=98.0))
    assert out.guidance["midpoint"] == pytest.approx(100.0)
    assert out.guidance["vs_consensus"] == pytest.approx(100.0 / 98.0 - 1.0)


def test_graceful_degradation_lists_missing():
    out = build_consensus_read(_row(revenue=100.0))
    assert out.rows == []
    assert any("consensus" in m for m in out.missing)
    assert any("guidance" in m for m in out.missing)
    assert out.next_earnings is None
