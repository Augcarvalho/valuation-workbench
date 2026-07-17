"""Data Audit: trust the data before trusting the valuation.

Nine check families produce a flat issue table (one row per finding):
    company_id, ticker, check, severity, source_table, detail, value

Severities: high | medium | low | info. Pure functions over the monitoring
dataset + raw export tables, so every rule is unit-testable without Streamlit.
Sign conventions are EXPLAINED and flagged - never silently flipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling.outliers import metric_flag_reason, multiple_outlier_reason

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

DEEP_FIELDS_CRITICAL = ["shares_diluted", "d_and_a", "total_assets", "total_equity"]
DEEP_FIELDS_NICE = ["sbc", "ar", "inventory", "ap", "minority_interest",
                    "preferred_equity", "beta_2y", "week52_high", "week52_low"]
FIN_DEEP_FIELDS = ["tangible_common_equity", "book_value"]


def _issue(row: pd.Series, check: str, severity: str, source: str, detail: str,
           value=None) -> dict:
    return {
        "company_id": row.get("company_id"),
        "ticker": str(row.get("ticker", "")).replace(".SA", ""),
        "check": check,
        "severity": severity,
        "source_table": source,
        "detail": detail,
        "value": value,
    }


def _clean(v) -> float | None:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


# --- 1/2. currency-unit sanity + market-cap bridge ------------------------------------

def check_market_cap_bridge(latest: pd.DataFrame) -> list[dict]:
    issues = []
    for _, row in latest.iterrows():
        price, shares, mcap = (_clean(row.get("share_price")),
                               _clean(row.get("shares_outstanding")),
                               _clean(row.get("market_cap")))
        if not price or not shares or not mcap or mcap <= 0:
            continue
        # shares are stored in units; market cap in millions.
        implied = price * shares / 1e6
        gap = abs(implied / mcap - 1.0)
        if gap < 0.05:
            continue
        sev = "low" if gap < 0.15 else ("medium" if gap < 0.30 else "high")
        issues.append(_issue(row, "market_cap_bridge", sev, "market_data",
                             f"price x shares = {implied:,.0f}m vs reported market cap "
                             f"{mcap:,.0f}m ({gap:+.0%} gap) - possible ADR ratio, share-class, "
                             f"or unit mismatch", round(gap, 4)))
    return issues


def check_unit_sanity(latest: pd.DataFrame) -> list[dict]:
    """Cross-table unit mismatches (the classic BRL/USD/CNY million traps)."""
    issues = []
    for _, row in latest.iterrows():
        mcap, rev = _clean(row.get("market_cap")), _clean(row.get("revenue_ttm"))
        if mcap and rev and rev > 0:
            ratio = mcap / rev
            if ratio > 500 or ratio < 0.01:
                issues.append(_issue(row, "unit_sanity", "high", "market_data vs financials",
                                     f"market cap / TTM revenue = {ratio:,.0f}x - units of the two "
                                     f"tables likely disagree (currency or millions-vs-units)",
                                     round(ratio, 2)))
        ev, ebitda = _clean(row.get("enterprise_value")), _clean(row.get("ebitda_ttm"))
        margin = _clean(row.get("ebitda_margin_ttm"))
        if ev and ebitda and ebitda > 0 and ev / ebitda > 500 and margin and margin > 0.05:
            issues.append(_issue(row, "unit_sanity", "high", "market_data vs financials",
                                 f"EV/EBITDA = {ev / ebitda:,.0f}x despite a {margin:.1%} EBITDA margin - "
                                 f"units likely disagree", round(ev / ebitda, 1)))
    return issues


# --- 3. EV bridge ----------------------------------------------------------------------

def check_ev_bridge(latest: pd.DataFrame) -> list[dict]:
    issues = []
    for _, row in latest.iterrows():
        mcap, ev = _clean(row.get("market_cap")), _clean(row.get("enterprise_value"))
        debt = _clean(row.get("total_debt"))
        # CapIQ TEV subtracts total cash & ST investments; prefer that basis.
        cash_sti = _clean(row.get("cash_st_invest"))
        cash = cash_sti if cash_sti is not None else _clean(row.get("cash"))
        if not mcap or not ev or debt is None or cash is None or ev <= 0:
            continue
        minority = _clean(row.get("minority_interest"))
        preferred = _clean(row.get("preferred_equity"))
        partial = minority is None or preferred is None
        calc = mcap + debt + (minority or 0.0) + (preferred or 0.0) - cash
        gap = abs(calc / ev - 1.0)
        if gap < 0.05:
            continue
        sev = "low" if gap < 0.15 else ("medium" if gap < 0.30 else "high")
        label = "partial bridge (minority/preferred not exported)" if partial else "full bridge"
        if cash_sti is None:
            label += ", cash & equivalents basis (ST investments not exported)"
        # Insurers / managed care hold regulated investment portfolios that
        # CapIQ's TEV treats differently from operating cash - a bridge gap is
        # expected there and EV is not the primary lens anyway.
        model = str(row.get("business_model", "")).lower()
        group = f"{row.get('peer_group', '')} {row.get('sector', '')}".lower()
        if model in ("financial", "insurer") or "managed care" in group or "insurance" in group:
            sev = "low"
            label += "; EV framework secondary for this business model (investment-portfolio cash basis)"
        issues.append(_issue(row, "ev_bridge", sev, "market_data vs financials",
                             f"calculated EV {calc:,.0f} vs reported {ev:,.0f} ({gap:+.0%}); {label}. "
                             f"Residual gaps usually mean a stale TEV print or FX/ADR share-count "
                             f"mismatches - check the as-of dates.",
                             round(gap, 4)))
    return issues


# --- 4. CFO / capex / FCF sign convention -----------------------------------------------

def check_sign_conventions(latest: pd.DataFrame) -> list[dict]:
    """The pipeline stores capex as a POSITIVE outflow and fcf = cfo - capex."""
    issues = []
    for _, row in latest.iterrows():
        cfo = _clean(row.get("cfo_ttm", row.get("cfo")))
        capex = _clean(row.get("capex_ttm", row.get("capex")))
        fcf = _clean(row.get("fcf_ttm", row.get("fcf")))
        if capex is not None and capex < 0:
            issues.append(_issue(row, "sign_convention", "medium", "financials",
                                 f"capex is negative ({capex:,.0f}); the pipeline convention is "
                                 f"positive outflow - NOT auto-flipped, verify the export",
                                 capex))
        if fcf is not None and cfo is None:
            issues.append(_issue(row, "sign_convention", "medium", "financials",
                                 "FCF populated but CFO missing - conversion metrics unreliable"))
        if fcf is not None and capex is None:
            issues.append(_issue(row, "sign_convention", "low", "financials",
                                 "FCF populated but capex missing - cannot verify FCF = CFO - capex"))
        if fcf is not None and cfo is not None and capex is not None:
            expected = cfo - capex
            denom = max(abs(expected), abs(fcf), 1.0)
            if abs(fcf - expected) / denom > 0.05:
                issues.append(_issue(row, "sign_convention", "medium", "financials",
                                     f"FCF {fcf:,.0f} != CFO - capex ({expected:,.0f}) - sign or "
                                     f"definition inconsistency", round(fcf - expected, 1)))
        conv = _clean(row.get("fcf_conversion_ttm"))
        if conv is not None and (conv > 3.0 or conv < -2.0):
            issues.append(_issue(row, "sign_convention", "medium", "derived",
                                 f"FCF conversion {conv:+.0%} is implausible - typically a sign "
                                 f"convention artifact", round(conv, 3)))
    return issues


# --- 5. TTM completeness -----------------------------------------------------------------

def check_ttm_completeness(df: pd.DataFrame, latest: pd.DataFrame) -> list[dict]:
    issues = []
    quarters = df.groupby("company_id")["period"].nunique()
    for _, row in latest.iterrows():
        cid = row.get("company_id")
        n_q = int(quarters.get(cid, 0))
        is_financial = str(row.get("business_model")) == "financial"
        if n_q < 4:
            issues.append(_issue(row, "ttm_completeness", "high", "financials",
                                 f"only {n_q} quarter(s) of history - TTM metrics not computable", n_q))
            continue
        if "ttm_complete" in row.index and not bool(row.get("ttm_complete")):
            issues.append(_issue(row, "ttm_completeness", "medium", "derived",
                                 "ttm_complete = False (gaps inside the 4-quarter window)"))
        core = ["revenue_ttm", "net_income_ttm"] + ([] if is_financial else ["ebitda_ttm", "cfo_ttm"])
        missing = [f for f in core if _clean(row.get(f)) is None]
        if missing:
            sev = "medium" if not is_financial else "low"
            issues.append(_issue(row, "ttm_completeness", sev, "financials",
                                 f"missing TTM fields: {', '.join(missing)}"
                                 + (" (financial: EBITDA-frame fields are n/m by design)"
                                    if is_financial else "")))
    return issues


# --- 6. stale period ---------------------------------------------------------------------

def check_stale_periods(latest: pd.DataFrame) -> list[dict]:
    issues = []
    periods = pd.to_datetime(latest["period"])
    universe_latest = periods.max()
    for (_, row), period in zip(latest.iterrows(), periods):
        lag_days = (universe_latest - period).days
        # A company with a March fiscal quarter is not stale merely because a
        # May fiscal quarter normalizes into the next calendar quarter. Only
        # flag names at least roughly two fiscal quarters behind the universe.
        if lag_days <= 135:
            continue
        quarters_stale = int(round(lag_days / 91.25))
        sev = "medium" if quarters_stale <= 1 else "high"
        issues.append(_issue(row, "stale_period", sev, "financials",
                             f"latest period {period.date()} is ~{quarters_stale} quarter(s) behind "
                             f"the universe latest {universe_latest.date()}", quarters_stale))
    return issues


# --- 7. refresh-log consistency -------------------------------------------------------------

def check_refresh_consistency(latest: pd.DataFrame, exports: dict[str, pd.DataFrame],
                              refresh_log: pd.DataFrame | None) -> list[dict]:
    issues = []
    n_dataset = latest["company_id"].nunique()
    counts = {
        "financial_rows": len(exports.get("financials", pd.DataFrame())),
        "market_rows": len(exports.get("market_data", pd.DataFrame())),
        "estimate_rows": len(exports.get("estimates", pd.DataFrame())),
        "valuation_rows": len(exports.get("valuation_history", pd.DataFrame())),
    }
    fin = exports.get("financials", pd.DataFrame())
    n_export = fin["company_id"].nunique() if "company_id" in getattr(fin, "columns", []) else 0
    stub = pd.Series({"company_id": "UNIVERSE", "ticker": "UNIVERSE"})
    if n_export and n_export != n_dataset:
        issues.append(_issue(stub, "refresh_consistency", "medium", "exports vs dataset",
                             f"dataset has {n_dataset} companies but financial export covers "
                             f"{n_export}", n_export - n_dataset))
    if refresh_log is not None and not refresh_log.empty:
        last = refresh_log.iloc[-1]
        logged = _clean(last.get("companies"))
        if logged is not None and int(logged) != n_dataset:
            issues.append(_issue(stub, "refresh_consistency", "medium", "refresh_log",
                                 f"latest refresh_log records {int(logged)} companies vs {n_dataset} "
                                 f"in the dataset - names added via single-fetch since the last full "
                                 f"refresh (log only updates on full runs)", int(logged) - n_dataset))
        for key in ("financial_rows", "market_rows", "estimate_rows", "valuation_rows"):
            logged_rows = _clean(last.get(key))
            if logged_rows is not None and counts[key] and abs(counts[key] - logged_rows) / max(counts[key], 1) > 0.10:
                issues.append(_issue(stub, "refresh_consistency", "low", "refresh_log",
                                     f"{key}: log says {int(logged_rows):,} vs {counts[key]:,} on disk "
                                     f"(single-name fetches accumulate between full refreshes)"))
    return issues


# --- 8. missing deep fields -------------------------------------------------------------------

def check_deep_fields(latest: pd.DataFrame) -> list[dict]:
    issues = []
    for _, row in latest.iterrows():
        is_financial = str(row.get("business_model")) in ("financial", "insurer")
        strict_review = str(row.get("coverage_role", "watchlist")) == "watchlist"
        critical_fields = DEEP_FIELDS_CRITICAL if strict_review else \
            (["total_equity"] if is_financial else [])
        crit_missing = [f for f in critical_fields
                        if f not in row.index or _clean(row.get(f)) is None]
        if crit_missing:
            issues.append(_issue(row, "deep_fields", "medium", "financials",
                                 f"missing valuation-critical fields: {', '.join(crit_missing)}"))
        nice_missing = [f for f in DEEP_FIELDS_NICE
                        if f not in row.index or _clean(row.get(f)) is None] if strict_review else []
        if nice_missing:
            issues.append(_issue(row, "deep_fields", "info", "exports",
                                 f"nice-to-have fields absent: {', '.join(nice_missing)}"))
        if is_financial and strict_review:
            fin_missing = [f for f in FIN_DEEP_FIELDS
                           if f not in row.index or _clean(row.get(f)) is None]
            if fin_missing:
                issues.append(_issue(row, "deep_fields", "medium", "financials",
                                     f"financial-institution fields absent: {', '.join(fin_missing)} "
                                     f"- P/TBV falls back to P/B on total equity"))
    return issues


# --- 9. outlier metrics -------------------------------------------------------------------------

def check_outlier_metrics(latest: pd.DataFrame) -> list[dict]:
    issues = []
    multiple_metrics = ["ev_to_ebitda_ttm", "pe_ttm", "ev_to_revenue_ttm"]
    flag_metrics = ["fcf_conversion_ttm", "net_debt_to_ebitda_ttm",
                    "revenue_yoy_growth", "ebitda_margin_ttm"]
    for _, row in latest.iterrows():
        for m in multiple_metrics:
            v = _clean(row.get(m))
            if v is None:
                continue
            reason = multiple_outlier_reason(m, v)
            if reason:
                issues.append(_issue(row, "outlier_metric", "medium", "derived",
                                     f"{m} = {v:,.1f}: {reason} - excluded from adjusted peer medians",
                                     round(v, 2)))
        for m in flag_metrics:
            v = _clean(row.get(m))
            if v is None:
                continue
            reason = metric_flag_reason(m, v)
            if reason:
                issues.append(_issue(row, "outlier_metric", "low", "derived",
                                     f"{m} = {v:,.2f}: {reason}", round(v, 3)))
    return issues


# --- orchestration ---------------------------------------------------------------------------------

def run_audit(df: pd.DataFrame, latest: pd.DataFrame,
              exports: dict[str, pd.DataFrame] | None = None,
              refresh_log: pd.DataFrame | None = None) -> pd.DataFrame:
    """All checks -> one issue table sorted by severity."""
    exports = exports or {}
    issues: list[dict] = []
    issues += check_market_cap_bridge(latest)
    issues += check_unit_sanity(latest)
    issues += check_ev_bridge(latest)
    issues += check_sign_conventions(latest)
    issues += check_ttm_completeness(df, latest)
    issues += check_stale_periods(latest)
    issues += check_refresh_consistency(latest, exports, refresh_log)
    issues += check_deep_fields(latest)
    issues += check_outlier_metrics(latest)
    out = pd.DataFrame(issues, columns=["company_id", "ticker", "check", "severity",
                                        "source_table", "detail", "value"])
    if out.empty:
        return out
    out["sev_rank"] = out["severity"].map(SEVERITY_ORDER).fillna(9)
    return out.sort_values(["sev_rank", "company_id"]).drop(columns="sev_rank").reset_index(drop=True)


def audit_scores(issues: pd.DataFrame, latest: pd.DataFrame) -> pd.DataFrame:
    """Per-company audit score (100 = clean): high -15, medium -5, low -1, info 0."""
    weights = {"high": 15, "medium": 5, "low": 1, "info": 0}
    rows = []
    for _, r in latest.iterrows():
        cid = r["company_id"]
        mine = issues[issues["company_id"] == cid] if not issues.empty else pd.DataFrame()
        penalty = int(sum(weights.get(s, 0) for s in mine.get("severity", [])))
        rows.append({
            "company_id": cid,
            "ticker": str(r.get("ticker", "")).replace(".SA", ""),
            "score": max(0, 100 - penalty),
            "high": int((mine.get("severity", pd.Series(dtype=str)) == "high").sum()),
            "medium": int((mine.get("severity", pd.Series(dtype=str)) == "medium").sum()),
            "low": int((mine.get("severity", pd.Series(dtype=str)) == "low").sum()),
        })
    return pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
