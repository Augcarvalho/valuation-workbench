"""Attention score: where should the team spend the next ten hours?

A 0–100 composite that ranks the watchlist by *actionability*, not by size or
alphabet. Components (each normalized to 0–1):

- **valuation dislocation** (35%) — discount to the peer-group median and/or
  cheapness vs the company's own multiple history, whichever screams louder.
- **revision momentum** (25%) — estimates being cut is the classic precursor
  of a debate; cuts score fully, raises score partially (still information).
- **operating inflection** (20%) — how much the margin and growth picture
  *changed* YoY; stable names score low regardless of level.
- **flag pressure** (20%) — count of open high/medium red flags.

Missing components contribute zero rather than blocking the score, so the
ranking works on day one and sharpens as valuation history and consensus
tables get populated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WEIGHTS = {
    "valuation": 0.35,
    "revisions": 0.25,
    "inflection": 0.20,
    "flags": 0.20,
}


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _valuation_component(premium: float | None, history_percentile: float | None) -> float:
    peer_part = 0.0
    if premium is not None and not pd.isna(premium) and premium < 0:
        peer_part = _clip01(-premium / 0.50)          # a 50% discount saturates
    hist_part = 0.0
    if history_percentile is not None and not pd.isna(history_percentile):
        hist_part = _clip01((0.5 - history_percentile) / 0.5) if history_percentile < 0.5 else 0.0
    return max(peer_part, hist_part)


def _revision_component(revisions: dict | None) -> float:
    if not revisions or not revisions.get("available"):
        return 0.0
    moves = [v for v in (revisions.get("revenue_30d"), revisions.get("eps_30d")) if v is not None]
    if not moves:
        return 0.0
    avg = float(np.mean(moves))
    if avg < 0:
        return _clip01(-avg / 0.05)                   # a 5% cut in 30 days saturates
    return 0.4 * _clip01(avg / 0.05)


def _inflection_component(row: pd.Series, prior: pd.Series | None) -> float:
    if prior is None:
        return 0.0
    financial = str(row.get("business_model", "operating")).lower() == "financial"
    margin_metric = "net_income_margin_ttm" if financial else "ebitda_margin_ttm"
    parts = []
    m, mp = row.get(margin_metric), prior.get(margin_metric)
    if pd.notna(m) and pd.notna(mp):
        parts.append(_clip01(abs(float(m) - float(mp)) / 0.05))    # 500bps saturates
    g, gp = row.get("revenue_yoy_growth"), prior.get("revenue_yoy_growth")
    if pd.notna(g) and pd.notna(gp):
        parts.append(_clip01(abs(float(g) - float(gp)) / 0.15))    # 15pp swing saturates
    return float(np.mean(parts)) if parts else 0.0


def _flag_component(flags_count: int) -> float:
    return _clip01(flags_count / 4.0)


def compute_attention(
    row: pd.Series,
    prior: pd.Series | None,
    premium: float | None,
    history_percentile: float | None,
    revisions: dict | None,
    flags_count: int,
) -> tuple[float, dict]:
    components = {
        "valuation": _valuation_component(premium, history_percentile),
        "revisions": _revision_component(revisions),
        "inflection": _inflection_component(row, prior),
        "flags": _flag_component(flags_count),
    }
    score = 100.0 * sum(WEIGHTS[k] * v for k, v in components.items())
    return round(score, 1), components
