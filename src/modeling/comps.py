"""Comps spread: per-peer trading table with quartile statistics.

Lean MVP version of the Grupo Mateus Comps tab: LTM multiples from the
monitoring dataset plus NTM forward multiples where consensus estimates
exist (forward EV/EBITDA = EV / NTM EBITDA estimate). FY+1/FY+2 forwards
arrive with export v3 and slot into the same frame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SPREAD_COLUMNS = [
    "ticker", "company_name", "market_cap", "enterprise_value", "net_debt",
    "revenue_ttm", "ebitda_ttm", "net_income_ttm",
    "revenue_yoy_growth", "ebitda_margin_ttm", "beta_2y",
    "ev_to_revenue_ttm", "ev_to_ebitda_ttm", "pe_ttm", "p_tbv",
    "ev_to_ebitda_ntm", "ev_to_revenue_ntm", "pe_ntm",
    "ev_to_revenue_fy1", "ev_to_revenue_fy2",
    "ev_to_ebitda_fy1", "ev_to_ebitda_fy2",
    "pe_fy1", "pe_fy2",
]

STAT_METRICS = [
    "revenue_yoy_growth", "ebitda_margin_ttm",
    "ev_to_revenue_ttm", "ev_to_ebitda_ttm", "pe_ttm", "p_tbv",
    "ev_to_ebitda_ntm", "ev_to_revenue_ntm", "pe_ntm",
    "ev_to_ebitda_fy1", "ev_to_ebitda_fy2", "pe_fy1", "pe_fy2",
]

# Optional FY+1/FY+2 consensus fields (export v3; n/a until exported).
FY_ESTIMATE_COLUMNS = [
    "revenue_est_fy1", "revenue_est_fy2",
    "ebitda_est_fy1", "ebitda_est_fy2",
    "eps_est_fy1", "eps_est_fy2",
]


def _latest_estimates(estimates: pd.DataFrame | None) -> pd.DataFrame:
    if estimates is None or estimates.empty or "company_id" not in getattr(estimates, "columns", []):
        return pd.DataFrame(columns=["company_id", "revenue_est_ntm", "ebitda_est_ntm"])
    df = estimates.copy()
    if "period" in df.columns:
        df = df.sort_values("period")
    return df.groupby("company_id", as_index=False).tail(1)


def comps_spread(peers: pd.DataFrame, estimates: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per peer with LTM, NTM, and (when exported) FY1/FY2 multiples.

    FY1/FY2 forwards require the optional estimate fields (export v3); they
    render as n/a until then - never faked from LTM."""
    out = peers.copy()
    est = _latest_estimates(estimates)
    if not est.empty:
        keep = [c for c in ["company_id", "revenue_est_ntm", "ebitda_est_ntm",
                            "eps_est_ntm"] + FY_ESTIMATE_COLUMNS if c in est.columns]
        # The dataset rows may already carry these estimate columns; drop them
        # before merging or pandas suffixes both sides and every NTM multiple
        # silently becomes NaN.
        collide = [c for c in keep if c != "company_id" and c in out.columns]
        out = out.drop(columns=collide).merge(est[keep], on="company_id", how="left")
    for col in ["revenue_est_ntm", "ebitda_est_ntm"] + FY_ESTIMATE_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    ev = out.get("enterprise_value")
    price = out.get("share_price")

    def _fwd(numer_col: str):
        base = out[numer_col].where(out[numer_col] > 0)
        return ev / base

    out["ev_to_ebitda_ntm"] = _fwd("ebitda_est_ntm")
    out["ev_to_revenue_ntm"] = _fwd("revenue_est_ntm")
    out["ev_to_ebitda_fy1"] = _fwd("ebitda_est_fy1")
    out["ev_to_ebitda_fy2"] = _fwd("ebitda_est_fy2")
    out["ev_to_revenue_fy1"] = _fwd("revenue_est_fy1")
    out["ev_to_revenue_fy2"] = _fwd("revenue_est_fy2")
    if price is not None:
        # NTM P/E guardrail: negative/zero/missing forward EPS -> NaN (N/M),
        # never a negative multiple silently entering a median.
        eps_ntm = out["eps_est_ntm"] if "eps_est_ntm" in out.columns else pd.Series(np.nan, index=out.index)
        out["pe_ntm"] = price / eps_ntm.where(eps_ntm > 0)
        out["pe_fy1"] = price / out["eps_est_fy1"].where(out["eps_est_fy1"] > 0)
        out["pe_fy2"] = price / out["eps_est_fy2"].where(out["eps_est_fy2"] > 0)
    else:
        out["pe_ntm"] = np.nan
        out["pe_fy1"] = np.nan
        out["pe_fy2"] = np.nan

    cols = ["company_id"] + [c for c in SPREAD_COLUMNS if c in out.columns]
    return out[cols].sort_values("ev_to_ebitda_ttm", na_position="last").reset_index(drop=True)


def quartile_stats(spread: pd.DataFrame) -> pd.DataFrame:
    """Per-metric statistics with explicit outlier handling.

    Columns: q1, median (raw), adjusted_median (outliers excluded), mean, q3,
    high, low, n, n_excluded, excluded (list of (ticker, reason))."""
    from src.modeling.outliers import adjusted_stats

    rows = {}
    for metric in STAT_METRICS:
        if metric not in spread.columns:
            continue
        s = adjusted_stats(spread, metric)
        rows[metric] = {
            "q1": s["q1"],
            "median": s["raw_median"],
            "adjusted_median": s["adjusted_median"],
            "mean": s["mean"],
            "q3": s["q3"],
            "high": s["high"],
            "low": s["low"],
            "n": s["n_valid"],
            "n_excluded": s["n_excluded"],
            "excluded": s["excluded"],
        }
    return pd.DataFrame(rows).T


def exit_multiple_from_comps(spread: pd.DataFrame, anchor_company_id: str | None = None) -> tuple[float | None, str]:
    """Peer-median exit multiple: NTM forward EV/EBITDA preferred, LTM fallback.

    The anchor company is excluded from its own comp median.
    """
    from src.modeling.outliers import adjusted_stats

    pool = spread
    if anchor_company_id is not None and "company_id" in spread.columns:
        pool = spread[spread["company_id"] != anchor_company_id]
    for column, label in [("ev_to_ebitda_fy1", "peer adjusted-median FY1 EV/EBITDA"),
                          ("ev_to_ebitda_ntm", "peer adjusted-median NTM EV/EBITDA"),
                          ("ev_to_ebitda_ttm", "peer adjusted-median LTM EV/EBITDA")]:
        if column in pool.columns:
            s = adjusted_stats(pool, column)
            n_adj = s["n_valid"] - s["n_excluded"]
            if n_adj >= 3 and not np.isnan(s["adjusted_median"]) and s["adjusted_median"] > 0:
                return float(s["adjusted_median"]), label
    return None, "insufficient peer multiples"
