"""Actual vs consensus: beats/misses, revision momentum, guidance framing.

Works with whatever the estimate export provides and degrades gracefully -
missing fields become None with an explicit availability map, never faked.

Caveat disclosed in the UI: the exported ``*_consensus`` fields are the
CURRENT-quarter consensus as of the refresh date; comparing them to the latest
REPORTED quarter is an approximation until as-reported consensus history is
exported.
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
    missing: list[str] = field(default_factory=list)


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


def _beat(actual: float | None, consensus: float | None) -> dict | None:
    if actual is None or consensus is None or consensus == 0:
        return None
    delta = actual - consensus
    return {"actual": actual, "consensus": consensus, "delta": delta,
            "delta_pct": delta / abs(consensus),
            "status": "beat" if delta > 0 else ("miss" if delta < 0 else "in line")}


def _revision(now: float | None, ago: float | None) -> float | None:
    if now is None or ago is None or ago == 0:
        return None
    return now / ago - 1.0


def build_consensus_read(row: pd.Series) -> ConsensusRead:
    """Latest-row consensus analytics for one company."""
    out = ConsensusRead(company_id=str(row.get("company_id")))

    pairs = [
        ("Revenue", _clean(row.get("revenue")), _clean(row.get("revenue_consensus"))),
        ("EBITDA", _clean(row.get("ebitda")), _clean(row.get("ebitda_consensus"))),
        ("EPS", None, _clean(row.get("eps_consensus"))),   # reported EPS not exported yet
    ]
    for name, actual, consensus in pairs:
        b = _beat(actual, consensus)
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
    return out
