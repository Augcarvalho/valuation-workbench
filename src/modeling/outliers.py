"""Explicit outlier handling for comps and peer medians.

IB discipline: outliers are never hidden - they stay in the table with a badge
and a reason, but they are EXCLUDED from the *adjusted* median so one broken
multiple cannot poison the exit-multiple anchor. Every consumer sees both the
raw and the adjusted statistic plus who was excluded and why.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# metric -> (rule callable returning reason-or-None)
EV_EBITDA_MAX = 75.0
PE_MAX = 100.0
EV_REVENUE_MAX = 50.0


def multiple_outlier_reason(metric: str, value: float) -> str | None:
    """Reason a single multiple observation is excluded from the adjusted median."""
    if value is None or pd.isna(value) or np.isinf(value):
        return None
    if metric in ("ev_to_ebitda_ttm", "ev_to_ebitda_ntm", "ev_to_ebitda_fy1", "ev_to_ebitda_fy2"):
        if value < 0:
            return "negative EBITDA"
        if value > EV_EBITDA_MAX:
            return f"extreme multiple (> {EV_EBITDA_MAX:.0f}x)"
    elif metric in ("pe_ttm", "pe_ntm", "pe_fy1", "pe_fy2"):
        if value < 0:
            return "negative earnings"
        if value > PE_MAX:
            return f"extreme multiple (> {PE_MAX:.0f}x)"
    elif metric == "p_tbv":
        if value < 0:
            return "negative tangible book"
    elif metric in ("ev_to_revenue_ttm", "ev_to_revenue_ntm", "ev_to_revenue_fy1", "ev_to_revenue_fy2"):
        if value < 0:
            return "negative EV"
        if value > EV_REVENUE_MAX:
            return f"extreme multiple (> {EV_REVENUE_MAX:.0f}x)"
    return None


def metric_flag_reason(metric: str, value: float) -> str | None:
    """Softer sanity flags for non-multiple metrics (flag, never exclude)."""
    if value is None or pd.isna(value) or np.isinf(value):
        return None
    if metric == "fcf_conversion_ttm" and (value > 2.0 or value < -1.0):
        return "FCF conversion outside [-100%, 200%]"
    if metric == "net_debt_to_ebitda_ttm" and (value > 8.0 or value < -5.0):
        return "leverage outside [-5x, 8x]"
    if metric == "revenue_yoy_growth" and value > 1.0:
        return "revenue growth > 100%"
    if metric == "ebitda_margin_ttm" and (value > 0.80 or value < -0.50):
        return "EBITDA margin outside [-50%, 80%]"
    return None


def adjusted_stats(spread: pd.DataFrame, metric: str,
                   label_col: str = "ticker") -> dict:
    """Raw vs adjusted statistics for one metric across a comp spread.

    Returns: {raw_median, adjusted_median, mean, q1, q3, high, low, n_valid,
              n_excluded, excluded: [(label, reason)]}
    """
    if metric not in spread.columns:
        return {"raw_median": np.nan, "adjusted_median": np.nan, "mean": np.nan,
                "q1": np.nan, "q3": np.nan, "high": np.nan, "low": np.nan,
                "n_valid": 0, "n_excluded": 0, "excluded": []}
    series = pd.to_numeric(spread[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)
    labels = spread[label_col] if label_col in spread.columns else spread.index.astype(str)

    valid_mask = series.notna()
    excluded: list[tuple[str, str]] = []
    keep_mask = valid_mask.copy()
    for i in series.index[valid_mask]:
        reason = multiple_outlier_reason(metric, float(series.loc[i]))
        if reason is not None:
            keep_mask.loc[i] = False
            excluded.append((str(labels.loc[i]), reason))

    raw = series[valid_mask]
    adj = series[keep_mask]
    return {
        "raw_median": float(raw.median()) if len(raw) else np.nan,
        "adjusted_median": float(adj.median()) if len(adj) else np.nan,
        "mean": float(adj.mean()) if len(adj) else np.nan,
        "q1": float(adj.quantile(0.25)) if len(adj) else np.nan,
        "q3": float(adj.quantile(0.75)) if len(adj) else np.nan,
        "high": float(adj.max()) if len(adj) else np.nan,
        "low": float(adj.min()) if len(adj) else np.nan,
        "n_valid": int(len(raw)),
        "n_excluded": int(len(excluded)),
        "excluded": excluded,
    }


def spread_badges(spread: pd.DataFrame) -> dict[str, list[str]]:
    """Per-company badges across all multiple metrics: {ticker: [reasons]}."""
    badges: dict[str, list[str]] = {}
    for metric in [c for c in spread.columns if c.startswith(("ev_to_", "pe_"))]:
        for _, row in spread.iterrows():
            reason = multiple_outlier_reason(metric, row.get(metric))
            if reason:
                key = str(row.get("ticker", row.get("company_id", "?")))
                badges.setdefault(key, []).append(f"{metric}: {reason}")
    return badges
