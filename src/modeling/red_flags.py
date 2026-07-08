"""Red-flag engine (v2).

Each flag carries a severity, the observed reason, and the management question
an investment team would actually ask. Rules are business-model aware: signals
marked ``n/m`` never fire, and lender-specific economics are handled by the
profitability rules on net income margin.

V2 adds earnings-quality and working-capital rules that only activate when the
deep-dive CapIQ fields (SBC, AR/inventory, diluted shares, goodwill) are
present — so the engine sharpens automatically after a full export refresh.
"""

from __future__ import annotations

import pandas as pd

from src.utils import fmt_multiple, fmt_pct, fmt_signed_pct


def _flag(severity: str, area: str, observation: str, question: str) -> dict[str, str]:
    return {
        "severity": severity,
        "area": area,
        "observation": observation,
        "management_question": question,
    }


def generate_red_flags(
    row: pd.Series,
    prior: pd.Series | None = None,
    revisions: dict | None = None,
) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    financial = str(row.get("business_model", "operating")).lower() == "financial"

    # --- Growth ---------------------------------------------------------------
    if row.get("revenue_yoy_growth_signal") == "red":
        flags.append(_flag(
            "High", "Growth",
            f"Revenue YoY growth is {fmt_pct(row.get('revenue_yoy_growth'))}.",
            "What changed in volume, pricing, churn, or sales productivity versus the prior-year quarter?",
        ))

    # --- Profitability ----------------------------------------------------------
    if financial:
        if row.get("net_income_margin_ttm_signal") == "red":
            flags.append(_flag(
                "High", "Profitability",
                f"TTM net income margin is {fmt_pct(row.get('net_income_margin_ttm'))}.",
                "How much of the margin pressure is credit provisioning versus funding cost versus opex?",
            ))
    else:
        if row.get("ebitda_margin_ttm_signal") == "red":
            flags.append(_flag(
                "High", "Margins",
                f"TTM EBITDA margin is {fmt_pct(row.get('ebitda_margin_ttm'))}.",
                "Which cost lines explain margin compression, and which actions are already underway?",
            ))

    # --- Cash conversion (operating companies only) ------------------------------
    if row.get("fcf_conversion_ttm_signal") in {"red", "yellow"}:
        flags.append(_flag(
            "Medium", "Cash conversion",
            f"TTM FCF conversion is {fmt_pct(row.get('fcf_conversion_ttm'))}.",
            "How much of the cash conversion pressure is recurring versus timing-related working capital?",
        ))

    # --- Leverage ----------------------------------------------------------------
    if row.get("net_debt_to_ebitda_ttm_signal") in {"red", "yellow"}:
        flags.append(_flag(
            "Medium", "Leverage",
            f"Net debt / EBITDA is {fmt_multiple(row.get('net_debt_to_ebitda_ttm'))}.",
            "What is the deleveraging path under base and downside EBITDA scenarios?",
        ))

    # --- Valuation vs peers ---------------------------------------------------------
    if row.get("ev_to_ebitda_ttm_signal") == "red":
        flags.append(_flag(
            "Medium", "Valuation",
            f"EV / EBITDA is {fmt_multiple(row.get('ev_to_ebitda_ttm'))}.",
            "Is the current valuation supported by growth, margin quality, and cash conversion versus peers?",
        ))

    # --- Earnings quality: stock-based compensation --------------------------------
    sbc_pct = row.get("sbc_pct_of_fcf_ttm")
    if pd.notna(sbc_pct) and sbc_pct >= 0.30:
        flags.append(_flag(
            "Medium", "Earnings quality",
            f"Stock-based compensation absorbs {fmt_pct(sbc_pct)} of TTM free cash flow.",
            "How does management think about SBC as a real economic cost, and what is the dilution glide path?",
        ))

    # --- Dilution --------------------------------------------------------------------
    share_growth = row.get("share_count_yoy")
    if pd.notna(share_growth) and share_growth >= 0.03:
        flags.append(_flag(
            "Medium", "Dilution",
            f"Diluted share count grew {fmt_signed_pct(share_growth)} YoY.",
            "What offsets the dilution — buybacks, and at what valuation discipline?",
        ))

    # --- Working capital: receivables and inventory -------------------------------------
    if prior is not None:
        dso, dso_prior = row.get("dso"), prior.get("dso")
        if pd.notna(dso) and pd.notna(dso_prior) and dso_prior > 0 and (dso - dso_prior) >= 15:
            flags.append(_flag(
                "Medium", "Receivables",
                f"DSO rose to {dso:.0f} days from {dso_prior:.0f} a year ago.",
                "Is the receivables build customer mix, terms extension, or collectability risk?",
            ))
        dio, dio_prior = row.get("dio"), prior.get("dio")
        if pd.notna(dio) and pd.notna(dio_prior) and dio_prior > 0 and (dio / dio_prior - 1) >= 0.20:
            flags.append(_flag(
                "High", "Inventory",
                f"Inventory days rose to {dio:.0f} from {dio_prior:.0f} a year ago.",
                "How much of the inventory build is deliberate versus demand shortfall, and what is the markdown risk?",
            ))

    # --- Balance-sheet quality: goodwill ---------------------------------------------------
    goodwill, equity = row.get("goodwill"), row.get("total_equity")
    if pd.notna(goodwill) and pd.notna(equity) and equity > 0 and goodwill / equity >= 0.6:
        flags.append(_flag(
            "Medium", "Balance sheet",
            f"Goodwill is {fmt_pct(goodwill / equity)} of book equity.",
            "Which acquired assets carry the goodwill, and how are their earn-outs and impairment tests trending?",
        ))

    # --- Estimate revisions -------------------------------------------------------------------
    if revisions and revisions.get("available") and revisions.get("direction") == "cutting":
        moves = [v for v in (revisions.get("revenue_30d"), revisions.get("eps_30d")) if v is not None]
        worst = min(moves) if moves else None
        flags.append(_flag(
            "High", "Estimate momentum",
            f"Consensus NTM estimates were cut over the last 30 days ({fmt_signed_pct(worst)} at worst).",
            "What is driving the downward revisions, and does management's own outlook agree with the street?",
        ))

    if not flags:
        flags.append(_flag(
            "Monitor", "Overall",
            "No red KPI flags under the current watchlist thresholds.",
            "Which value-creation initiatives can accelerate growth, margin expansion, or cash conversion next quarter?",
        ))

    return flags
