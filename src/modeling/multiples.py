"""Multi-multiple valuation framework: which multiple matters, and what it says.

IB/PE discipline: the right multiple depends on the business model, not on
habit. This module decides applicability (Primary / Secondary / Cross-check /
Not meaningful) per company, builds the per-multiple summary against peers and
own history, measures multiple momentum (re-rating vs de-rating vs sector
move), and produces deterministic rules-based commentary. Pure pandas - no
rendering, no LLM calls - so every judgment is unit-testable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling.expectations import valuation_vs_history
from src.modeling.outliers import adjusted_stats, multiple_outlier_reason

# metric key -> (display label, valuation_history column, peer NTM column)
MULTIPLE_SPECS: dict[str, dict] = {
    "ev_to_revenue_ttm": {"label": "EV / Revenue", "hist_col": "ev_to_revenue_ltm",
                          "ntm_col": "ev_to_revenue_ntm"},
    "ev_to_ebitda_ttm": {"label": "EV / EBITDA", "hist_col": "ev_to_ebitda_ltm",
                         "ntm_col": "ev_to_ebitda_ntm"},
    "pe_ttm": {"label": "P / E", "hist_col": "pe_ltm", "ntm_col": "pe_ntm"},
    "p_tbv": {"label": "P / TBV", "hist_col": None, "ntm_col": None},
}

ROLE_ORDER = {"primary": 0, "secondary": 1, "cross-check": 2, "not_meaningful": 3}
ROLE_LABELS = {"primary": "Primary", "secondary": "Secondary",
               "cross-check": "Cross-check", "not_meaningful": "Not meaningful"}

# Interpretation thresholds vs the adjusted peer median.
CHEAP_DISCOUNT = -0.15
EXPENSIVE_PREMIUM = 0.15

_HIGH_GROWTH = 0.25          # revenue growth above this = growth-story lens
_LOW_MARGIN = 0.10           # EBITDA margin below this with high growth
_CONSUMER_GROUPS = ("consumer", "retail", "apparel", "footwear", "brand")


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(v) or np.isinf(v)) else v


def multiple_roles(row: pd.Series) -> dict[str, dict]:
    """Applicability of each multiple for one company: role + reason.

    Rules (street practice, see docs/methodology.md):
    - Financials/insurers: P/E + P/TBV primary; EV multiples not meaningful.
    - Negative EBITDA: EV/Revenue primary; EV/EBITDA not meaningful.
    - High growth + thin margin: EV/Revenue primary, EV/EBITDA secondary.
    - Consumer/retail/branded: EV/EBITDA + P/E primary, EV/Revenue cross-check.
    - Mature operating default: EV/EBITDA primary, P/E secondary, EV/Revenue
      cross-check. Negative earnings always demote P/E to not meaningful.
    """
    model = str(row.get("business_model", "operating")).lower()
    group = f"{row.get('peer_group', '')} {row.get('sector', '')}".lower()
    ebitda = _num(row.get("ebitda_ttm"))
    earnings = _num(row.get("net_income_ttm"))
    growth = _num(row.get("revenue_yoy_growth"))
    margin = _num(row.get("ebitda_margin_ttm"))
    tbv_mult = _num(row.get("p_tbv"))

    roles: dict[str, dict] = {}

    def set_role(metric: str, role: str, reason: str) -> None:
        roles[metric] = {"role": role, "reason": reason}

    if model in ("financial", "insurer"):
        set_role("pe_ttm", "primary", "earnings are the value driver for balance-sheet businesses")
        if earnings is not None and earnings <= 0:
            set_role("pe_ttm", "not_meaningful", "negative earnings")
        set_role("p_tbv", "primary" if tbv_mult is not None else "not_meaningful",
                 "book value is productive capital for financials" if tbv_mult is not None
                 else "tangible book value not exported for this name")
        set_role("ev_to_ebitda_ttm", "not_meaningful",
                 "EV/EBITDA is not meaningful for financials (debt is raw material, not financing)")
        set_role("ev_to_revenue_ttm", "not_meaningful",
                 "EV framework not meaningful for balance-sheet businesses")
        return roles

    # Operating companies -----------------------------------------------------
    ebitda_negative = ebitda is not None and ebitda <= 0
    earnings_negative = earnings is not None and earnings <= 0
    high_growth = (growth is not None and growth >= _HIGH_GROWTH
                   and (margin is None or margin < _LOW_MARGIN or ebitda_negative))
    consumer = any(k in group for k in _CONSUMER_GROUPS)

    if ebitda_negative:
        set_role("ev_to_revenue_ttm", "primary", "negative EBITDA - revenue is the only clean base")
        set_role("ev_to_ebitda_ttm", "not_meaningful", "negative EBITDA")
    elif high_growth:
        set_role("ev_to_revenue_ttm", "primary",
                 "high-growth, margin-reset story - revenue base less distorted by investment phase")
        set_role("ev_to_ebitda_ttm", "secondary", "EBITDA positive but not yet normalized")
    elif consumer:
        set_role("ev_to_ebitda_ttm", "primary", "cash-generative brand economics")
        set_role("ev_to_revenue_ttm", "cross-check",
                 "margin-aware cross-check (a revenue multiple hides margin differences)")
    else:
        set_role("ev_to_ebitda_ttm", "primary", "mature operating profile - capital-structure-neutral")
        set_role("ev_to_revenue_ttm", "cross-check", "sanity check when margins diverge from peers")

    if earnings_negative:
        set_role("pe_ttm", "not_meaningful", "negative earnings")
    elif consumer:
        set_role("pe_ttm", "primary", "earnings quality is the consumer-brand debate")
    elif ebitda_negative or high_growth:
        set_role("pe_ttm", "cross-check", "earnings thin/volatile at this stage")
    else:
        set_role("pe_ttm", "secondary", "leverage-aware complement to EV/EBITDA")

    set_role("p_tbv", "not_meaningful", "book value is not the value driver outside financials")
    return roles


def interpretation(current: float | None, premium: float | None,
                   role: str, outlier_reason: str | None) -> str:
    """cheap | fair | expensive | distorted | not meaningful."""
    if role == "not_meaningful" or current is None:
        return "not meaningful"
    if outlier_reason:
        return "distorted"
    if premium is None:
        return "fair"
    if premium <= CHEAP_DISCOUNT:
        return "cheap"
    if premium >= EXPENSIVE_PREMIUM:
        return "expensive"
    return "fair"


def multiples_summary(row: pd.Series, peers: pd.DataFrame, company_id: str,
                      valuation_history: pd.DataFrame | None = None) -> list[dict]:
    """One dict per multiple: current, peer median, premium, history percentile,
    role, interpretation. Sorted primary-first."""
    roles = multiple_roles(row)
    pool = peers[peers["company_id"] != company_id] if "company_id" in peers.columns else peers
    out: list[dict] = []
    for metric, spec in MULTIPLE_SPECS.items():
        role = roles.get(metric, {"role": "not_meaningful", "reason": ""})
        current = _num(row.get(metric))
        stats = adjusted_stats(pool, metric) if metric in pool.columns else None
        med = stats["adjusted_median"] if stats else np.nan
        premium = (current / med - 1.0) if (current is not None and current > 0
                                            and not np.isnan(med) and med > 0) else None
        hist = {"available": False}
        if spec["hist_col"] and valuation_history is not None:
            hist = valuation_vs_history(valuation_history, company_id, current,
                                        column=spec["hist_col"])
        reason = multiple_outlier_reason(metric, current) if current is not None else None
        out.append({
            "metric": metric,
            "label": spec["label"],
            "current": current,
            "peer_median": None if stats is None or np.isnan(med) else float(med),
            "peer_median_raw": None if stats is None or np.isnan(stats["raw_median"]) else float(stats["raw_median"]),
            "n_peers": 0 if stats is None else int(stats["n_valid"] - stats["n_excluded"]),
            "premium": premium,
            "hist_percentile": hist.get("percentile"),
            "hist_median": hist.get("median"),
            "role": role["role"],
            "role_label": ROLE_LABELS[role["role"]],
            "role_reason": role["reason"],
            "outlier_reason": reason,
            "interpretation": interpretation(current, premium, role["role"], reason),
        })
    out.sort(key=lambda m: ROLE_ORDER[m["role"]])
    return out


# --- history & momentum -------------------------------------------------------

def multiple_history(valuation_history: pd.DataFrame, company_id: str,
                     peer_ids: list, column: str) -> dict:
    """Company series + peer median/quartile series for one history column.

    Negative observations (negative EBITDA/earnings months) are dropped from
    both series - a negative multiple is not a comparable level.
    """
    empty = {"available": False, "company": pd.DataFrame(), "peers": pd.DataFrame()}
    if valuation_history is None or valuation_history.empty or column not in valuation_history.columns:
        return empty
    vh = valuation_history[["company_id", "date", column]].copy()
    vh[column] = pd.to_numeric(vh[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    vh = vh[vh[column] > 0]

    own = vh[vh["company_id"] == company_id].sort_values("date")[["date", column]]
    peer_pool = vh[vh["company_id"].isin([p for p in peer_ids if p != company_id])]
    peers = (peer_pool.groupby("date")[column]
             .agg(median="median", q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75),
                  n="count")
             .reset_index().sort_values("date"))
    peers = peers[peers["n"] >= 3]
    if len(own) < 4:
        return empty
    return {"available": True, "company": own.rename(columns={column: "value"}),
            "peers": peers,
            "own_median": float(own[column].median()),
            "own_q1": float(own[column].quantile(0.25)),
            "own_q3": float(own[column].quantile(0.75))}


def _value_near(series: pd.DataFrame, target: pd.Timestamp, col: str,
                tolerance_days: int = 45) -> float | None:
    if series.empty:
        return None
    gaps = (series["date"] - target).abs()
    i = gaps.idxmin()
    if gaps.loc[i] > pd.Timedelta(days=tolerance_days):
        return None
    return _num(series.loc[i, col])


def multiple_momentum(valuation_history: pd.DataFrame, company_id: str,
                      peer_ids: list, column: str) -> dict:
    """Re-rating / de-rating vs sector for one multiple.

    Changes are measured on the monthly history (company vs peer median) at
    ~3/6/12 months back; ``relative`` = company change minus peer change.
    """
    out = {"available": False, "column": column, "current": None,
           "chg": {}, "peer_chg": {}, "relative": {}, "percentile": None, "verdict": None}
    hist = multiple_history(valuation_history, company_id, peer_ids, column)
    if not hist["available"]:
        return out
    own, peers = hist["company"], hist["peers"]
    last_date = own["date"].max()
    current = _num(own.loc[own["date"] == last_date, "value"].iloc[-1])
    if current is None:
        return out
    out["available"] = True
    out["current"] = current
    series = own["value"]
    out["percentile"] = float((series < current).mean())

    for months in (3, 6, 12):
        target = last_date - pd.DateOffset(months=months)
        base = _value_near(own, target, "value")
        out["chg"][months] = (current / base - 1.0) if base and base > 0 else None
        if not peers.empty:
            p_now = _value_near(peers, last_date, "median", tolerance_days=10)
            p_then = _value_near(peers, target, "median")
            out["peer_chg"][months] = (p_now / p_then - 1.0) if (p_now and p_then and p_then > 0) else None
        else:
            out["peer_chg"][months] = None
        c, p = out["chg"][months], out["peer_chg"][months]
        out["relative"][months] = (c - p) if (c is not None and p is not None) else None

    out["verdict"] = momentum_verdict(out["chg"].get(12), out["relative"].get(12))
    return out


def momentum_verdict(chg_12m: float | None, relative_12m: float | None) -> str:
    """Classify the 12m move: re-rating / de-rating, company-specific / sector."""
    if chg_12m is None:
        return "insufficient history"
    if abs(chg_12m) < 0.10:
        return "stable multiple"
    direction = "re-rating" if chg_12m > 0 else "de-rating"
    if relative_12m is None:
        return direction
    if abs(relative_12m) < 0.05:
        return f"{direction} - sector-driven"
    return f"{direction} - company-specific"


# --- deterministic commentary ---------------------------------------------------

def _fmt_mult(v: float | None) -> str:
    return f"{v:.1f}x" if v is not None else "n/a"


def valuation_commentary(summary: list[dict], momentum: dict[str, dict],
                         row: pd.Series) -> list[str]:
    """Short institutional read-outs, rules-based (no LLM)."""
    notes: list[str] = []
    by_metric = {m["metric"]: m for m in summary}

    primaries = [m for m in summary if m["role"] == "primary" and m["interpretation"] != "not meaningful"]
    for m in primaries[:2]:
        if m["premium"] is None:
            continue
        side = "below" if m["premium"] < 0 else "above"
        line = (f"{m['label']} at {_fmt_mult(m['current'])} trades {abs(m['premium']):.0%} "
                f"{side} the peer adjusted median ({_fmt_mult(m['peer_median'])}).")
        pct = m.get("hist_percentile")
        if pct is not None:
            if m["premium"] <= CHEAP_DISCOUNT and pct >= 0.6:
                line += (" Relative discount, but the multiple sits high in its own history - "
                         "limited absolute compression already priced out.")
            elif m["premium"] <= CHEAP_DISCOUNT and pct <= 0.4:
                line += " Cheap vs peers and vs its own history - the double discount worth underwriting."
            elif m["premium"] >= EXPENSIVE_PREMIUM and pct >= 0.6:
                line += " Rich vs peers and vs its own range - the multiple needs delivery, not hope."
            else:
                line += f" Sits at the {pct:.0%} percentile of its own history."
        notes.append(line)

    # Premium supported by fundamentals?
    ev_eb = by_metric.get("ev_to_ebitda_ttm")
    if ev_eb and ev_eb["premium"] is not None and ev_eb["premium"] >= EXPENSIVE_PREMIUM \
            and ev_eb["role"] in ("primary", "secondary"):
        growth_pct = _num(row.get("revenue_yoy_growth_peer_pct"))
        margin_pct = _num(row.get("ebitda_margin_ttm_peer_pct"))
        supported = (growth_pct is not None and growth_pct >= 0.6) or \
                    (margin_pct is not None and margin_pct >= 0.6)
        notes.append("The EV/EBITDA premium is supported by an above-peer growth/margin profile."
                     if supported else
                     "The EV/EBITDA premium is NOT obviously supported by growth or margin vs peers - "
                     "the burden of proof is on the multiple.")

    # Not-meaningful redirects.
    pe = by_metric.get("pe_ttm")
    if pe and pe["role"] == "not_meaningful" and "negative" in (pe["role_reason"] or ""):
        clean = next((m["label"] for m in summary if m["role"] == "primary"
                      and m["interpretation"] != "not meaningful"), None)
        if clean:
            notes.append(f"P/E is not meaningful on negative earnings; {clean} is the cleaner valuation lens.")

    # Momentum: company-specific vs sector.
    for metric, mom in momentum.items():
        m = by_metric.get(metric)
        if not mom.get("available") or m is None or m["role"] != "primary":
            continue
        verdict = mom.get("verdict") or ""
        if "company-specific" in verdict:
            direction = "de-rating" if "de-rating" in verdict else "re-rating"
            notes.append(f"The 12m {m['label']} {direction} is company-specific rather than "
                         f"sector-wide (peers moved {mom['peer_chg'].get(12, 0) or 0:+.0%}, "
                         f"the company {mom['chg'].get(12, 0) or 0:+.0%}).")
        elif "sector-driven" in verdict:
            notes.append(f"The 12m {m['label']} move is sector-driven - the whole comp set "
                         f"re-priced together; this is beta, not a company story.")
    return notes
