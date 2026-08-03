"""Actual vs consensus, revision momentum, and guidance framing.

Works with whatever the estimate export provides and degrades gracefully -
missing fields become None with an explicit availability map, never faked.

Current-quarter estimates are never labeled beats or misses. That language is
reserved for a point-in-time pre-report consensus matched to the actual period.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ConsensusRead:
    company_id: str
    rows: list[dict] = field(default_factory=list)          # metric-level actual vs consensus
    revisions: dict = field(default_factory=dict)           # metric -> {d30, d90}
    guidance: dict = field(default_factory=dict)            # low/high/midpoint/vs_consensus
    next_earnings: str | None = None
    num_analysts: float | None = None
    true_surprise: bool = False
    comparison_label: str = "Current FQ estimate comparison"
    missing: list[str] = field(default_factory=list)
    forward: dict = field(default_factory=dict)
    estimate_dispersion: dict = field(default_factory=dict)


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


def _comparison(actual: float | None, consensus: float | None, true_surprise: bool) -> dict | None:
    if actual is None or consensus is None or consensus == 0:
        return None
    delta = actual - consensus
    if true_surprise:
        status = "beat" if delta > 0 else ("miss" if delta < 0 else "in line")
    else:
        status = "above estimate" if delta > 0 else ("below estimate" if delta < 0 else "in line")
    return {"actual": actual, "consensus": consensus, "delta": delta,
            "delta_pct": delta / abs(consensus), "status": status}


def _revision(now: float | None, ago: float | None) -> float | None:
    if now is None or ago is None or ago == 0:
        return None
    return now / ago - 1.0


def build_consensus_read(row: pd.Series) -> ConsensusRead:
    """Latest-row consensus analytics for one company."""
    out = ConsensusRead(company_id=str(row.get("company_id")))

    actual_period = pd.to_datetime(row.get("period"), errors="coerce")
    consensus_period = pd.to_datetime(row.get("consensus_period"), errors="coerce")
    basis = str(row.get("consensus_basis", "")).strip().lower()
    period_match = pd.notna(actual_period) and pd.notna(consensus_period) \
        and actual_period.to_period("Q") == consensus_period.to_period("Q")
    out.true_surprise = basis in {"pre_report", "pre-report", "as_reported"} and period_match
    if out.true_surprise:
        out.comparison_label = "Actual vs pre-report consensus"
    else:
        out.missing.append("matched pre-report consensus (current IQ_FQ is not a beat/miss series)")

    pairs = [
        ("Revenue", _clean(row.get("revenue")), _clean(row.get("revenue_consensus"))),
        ("EBITDA", _clean(row.get("ebitda")), _clean(row.get("ebitda_consensus"))),
        ("EPS", _clean(row.get("reported_eps")), _clean(row.get("eps_consensus"))),
    ]
    for name, actual, consensus in pairs:
        b = _comparison(actual, consensus, out.true_surprise)
        if b is not None:
            out.rows.append({"metric": name, **b})
        elif consensus is None:
            out.missing.append(f"{name.lower()} consensus")
        elif actual is None:
            out.missing.append(f"reported {name.lower()}")

    out.revisions = {
        "revenue": {"d30": _revision(_clean(row.get("revenue_est_ntm")),
                                     _clean(row.get("revenue_est_ntm_30d_ago"))),
                    "d90": _revision(_clean(row.get("revenue_est_ntm")),
                                     _clean(row.get("revenue_est_ntm_90d_ago")))},
        "ebitda": {"d30": _revision(_clean(row.get("ebitda_est_ntm")),
                                    _clean(row.get("ebitda_est_ntm_30d_ago"))),
                   "d90": _revision(_clean(row.get("ebitda_est_ntm")),
                                    _clean(row.get("ebitda_est_ntm_90d_ago")))},
        "eps": {"d30": _revision(_clean(row.get("eps_est_ntm")),
                                 _clean(row.get("eps_est_ntm_30d_ago"))),
                "d90": _revision(_clean(row.get("eps_est_ntm")),
                                 _clean(row.get("eps_est_ntm_90d_ago")))},
    }
    if all(v is None for v in (out.revisions["ebitda"]["d30"], out.revisions["ebitda"]["d90"])):
        out.missing.append("EBITDA revision snapshots (ebitda_est_ntm_30d/90d_ago - export v3)")

    low, high = _clean(row.get("guidance_low")), _clean(row.get("guidance_high"))
    if low is not None and high is not None:
        mid = (low + high) / 2.0
        consensus_rev = _clean(row.get("revenue_consensus"))
        out.guidance = {
            "low": low, "high": high, "midpoint": mid,
            "metric": str(row.get("guidance_metric", "revenue")),
            "vs_consensus": (mid / consensus_rev - 1.0) if consensus_rev else None,
        }
    else:
        out.missing.append("guidance range (guidance_low/high not populated by this issuer)")

    ne = row.get("next_earnings_date")
    out.next_earnings = str(ne)[:10] if ne is not None and str(ne) not in ("nan", "NaT", "None") else None
    out.num_analysts = _clean(row.get("num_analysts"))
    out.forward = {
        "fy1_period": row.get("fy1_period"),
        "fy2_period": row.get("fy2_period"),
        "revenue_fy1": _clean(row.get("revenue_est_fy1")),
        "revenue_fy2": _clean(row.get("revenue_est_fy2")),
        "ebitda_fy1": _clean(row.get("ebitda_est_fy1")),
        "ebitda_fy2": _clean(row.get("ebitda_est_fy2")),
        "eps_fy1": _clean(row.get("eps_est_fy1")),
        "eps_fy2": _clean(row.get("eps_est_fy2")),
    }
    out.estimate_dispersion = {
        metric: _clean(row.get(f"{metric}_dispersion"))
        for metric in (
            "revenue_est_fy1", "revenue_est_fy2", "ebitda_est_fy1",
            "ebitda_est_fy2", "eps_est_fy1", "eps_est_fy2",
        )
    }
    return out
