"""Expectations analytics: valuation vs own history and estimate revisions.

Two questions every memo opens with:

1. *Where is the multiple versus its own history?* — percentile and z-score of
   the current multiple against the company's monthly valuation series.
2. *Which way are the estimates moving?* — NTM revenue/EPS consensus today
   versus the 30- and 90-day-ago snapshots.

Both degrade gracefully: without a populated valuation history or estimates
table they return ``available: False`` and the callers show "not populated"
instead of fake numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_HISTORY_OBS = 8  # fewer observations than this -> percentile is noise


def valuation_vs_history(
    valuation_history: pd.DataFrame,
    company_id: str,
    current_value: float | None,
    column: str = "ev_to_ebitda_ltm",
) -> dict:
    """Percentile / z-score of ``current_value`` vs the company's own series."""
    out = {
        "available": False,
        "column": column,
        "n_obs": 0,
        "percentile": None,
        "z_score": None,
        "median": None,
        "low": None,
        "high": None,
        "current": current_value,
    }
    if valuation_history is None or valuation_history.empty or column not in valuation_history.columns:
        return out
    series = (
        valuation_history.loc[valuation_history["company_id"] == company_id, column]
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    # Negative multiples (negative EBITDA/earnings) are not comparable levels.
    series = series[series > 0]
    out["n_obs"] = int(len(series))
    if len(series) < MIN_HISTORY_OBS or current_value is None or pd.isna(current_value) or current_value <= 0:
        return out

    out["available"] = True
    out["percentile"] = float((series < current_value).mean())
    std = float(series.std(ddof=0))
    out["z_score"] = float((current_value - series.mean()) / std) if std > 0 else 0.0
    out["median"] = float(series.median())
    out["low"] = float(series.min())
    out["high"] = float(series.max())
    return out


def _latest_estimate_row(estimates: pd.DataFrame, company_id: str) -> pd.Series | None:
    if estimates is None or estimates.empty or "company_id" not in estimates.columns:
        return None
    rows = estimates[estimates["company_id"] == company_id]
    if rows.empty:
        return None
    if "period" in rows.columns:
        rows = rows.sort_values("period")
    return rows.iloc[-1]


def _pct_change(now, before) -> float | None:
    if now is None or before is None or pd.isna(now) or pd.isna(before) or before == 0:
        return None
    return float(now) / float(before) - 1


def revision_momentum(estimates: pd.DataFrame, company_id: str) -> dict:
    """NTM estimate drift vs the 30d/90d-ago snapshots."""
    out = {
        "available": False,
        "revenue_30d": None,
        "revenue_90d": None,
        "eps_30d": None,
        "eps_90d": None,
        "direction": "n/a",
        "num_analysts": None,
        "next_earnings_date": None,
    }
    row = _latest_estimate_row(estimates, company_id)
    if row is None:
        return out

    out["revenue_30d"] = _pct_change(row.get("revenue_est_ntm"), row.get("revenue_est_ntm_30d_ago"))
    out["revenue_90d"] = _pct_change(row.get("revenue_est_ntm"), row.get("revenue_est_ntm_90d_ago"))
    out["eps_30d"] = _pct_change(row.get("eps_est_ntm"), row.get("eps_est_ntm_30d_ago"))
    out["eps_90d"] = _pct_change(row.get("eps_est_ntm"), row.get("eps_est_ntm_90d_ago"))
    na = row.get("num_analysts")
    out["num_analysts"] = int(na) if pd.notna(na) else None
    ned = row.get("next_earnings_date")
    out["next_earnings_date"] = str(ned)[:10] if pd.notna(ned) and str(ned).strip() else None

    signals = [v for v in (out["revenue_30d"], out["eps_30d"]) if v is not None]
    if not signals:
        out["available"] = out["next_earnings_date"] is not None
        return out

    out["available"] = True
    avg = float(np.mean(signals))
    if avg <= -0.01:
        out["direction"] = "cutting"
    elif avg >= 0.01:
        out["direction"] = "raising"
    else:
        out["direction"] = "stable"
    return out


def beats_and_misses(df_row: pd.Series) -> dict:
    """Actual vs consensus for the reported quarter, when consensus exists."""
    rev = df_row.get("revenue_vs_consensus")
    ebitda = df_row.get("ebitda_vs_consensus")
    return {
        "available": pd.notna(rev) or pd.notna(ebitda),
        "revenue_surprise": None if pd.isna(rev) else float(rev),
        "ebitda_surprise": None if pd.isna(ebitda) else float(ebitda),
    }
