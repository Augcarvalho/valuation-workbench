"""Investment-judgment layer.

Turns the normalized watchlist dataset into the structured judgment an
investment team writes up: scored KPI cards, key positives, key concerns,
red flags, a headline verdict, an investment view, and valuation logic.

Verdicts use watchlist vocabulary — where should the team spend time?

- ``Do Work``      — dislocation candidate: quality at a discount, or a broken
                     operating story the market is already pricing (value trap
                     vs entry is exactly the debate worth having).
- ``Constructive`` — operating story on track; valuation not a blocker.
- ``Watch``        — mixed signals; no forced action.
- ``Avoid / Pass`` — deteriorating without valuation support.

Judgment is business-model aware: lenders and banks are never judged on the
EBITDA framework (their signals come back ``n/m``), and their cards switch to
net-income margin and P/E.

Both the Streamlit dashboard and the exported board pack consume the same
``build_assessment()`` output so the narrative is identical across surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.modeling.attention import compute_attention
from src.modeling.expectations import revision_momentum, valuation_vs_history
from src.modeling.metrics import latest_rows
from src.modeling.peer_sets import resolve_peers
from src.modeling.red_flags import generate_red_flags
from src.modeling.thesis import Thesis, load_thesis
from src.utils import (
    fmt_bps,
    fmt_money,
    fmt_multiple,
    fmt_ordinal,
    fmt_pct,
    fmt_signed_pct,
)

VERDICT_LABELS = {
    "do_work": "Do Work",
    "constructive": "Constructive",
    "watch": "Watch",
    "avoid": "Avoid / Pass",
}

# Premium/discount gates vs the peer-group median multiple.
CHEAP_GATE = -0.15
RICH_GATE = 0.25

_REAL_SIGNALS = {"green", "yellow", "red"}


@dataclass
class Kpi:
    key: str
    label: str
    value: str
    context: str
    signal: str = "n/a"
    delta: str | None = None
    delta_dir: str = "flat"          # up | down | flat
    delta_good: bool | None = None   # is the move favorable?
    percentile: float | None = None
    percentile_label: str | None = None


@dataclass
class Assessment:
    company_id: str
    row: pd.Series
    prior: pd.Series | None
    peers: pd.DataFrame
    peer_median: dict
    kpis: list[Kpi] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    red_flags: list[dict] = field(default_factory=list)
    management_questions: list[str] = field(default_factory=list)
    commentary: str = ""
    sponsor_view: str = ""
    verdict_key: str = "watch"
    verdict_label: str = "Watch"
    verdict_rationale: str = ""
    valuation: dict = field(default_factory=dict)
    # V2 context (populated when the store's side tables exist).
    history_context: dict = field(default_factory=dict)   # multiple vs own history
    revisions: dict = field(default_factory=dict)         # estimate momentum
    attention_score: float = 0.0
    attention_components: dict = field(default_factory=dict)
    thesis: Thesis | None = None
    # Peer provenance (resolution hierarchy: approved set > peer_group > universe).
    peer_source: str = "peer_group"
    peer_reviewed: bool = False
    peer_warning: str | None = None
    peer_set_name: str = ""

    @property
    def business_model(self) -> str:
        return str(self.row.get("business_model", "operating")).lower()

    @property
    def peer_group(self) -> str:
        return str(self.row.get("peer_group", self.row.get("sector", "")))

    @property
    def theme(self) -> str:
        return str(self.row.get("theme", self.row.get("sector", "")))


# --- helpers ----------------------------------------------------------------

def _company_history(df: pd.DataFrame, company_id: str) -> pd.DataFrame:
    return df[df["company_id"] == company_id].sort_values("period")


def _prior_year_row(history: pd.DataFrame) -> pd.Series | None:
    """The reading from four quarters before the latest, if available."""
    if len(history) >= 5:
        return history.iloc[-5]
    return None


def _peer_frame(df: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    """The true comp set: the company's peer group, else the full universe."""
    latest = latest_rows(df)
    group_col = "peer_group" if "peer_group" in latest.columns else "sector"
    group = row.get(group_col)
    same_group = latest[latest[group_col] == group]
    if len(same_group) >= 3:
        return same_group.copy()
    return latest.copy()


def _median(peers: pd.DataFrame, column: str) -> float:
    if column in peers.columns:
        return float(peers[column].median(skipna=True))
    return float("nan")


def _delta(current: float, prior: float | None, lower_is_better: bool) -> tuple[str, str, bool | None]:
    """Return (chip_text, direction, is_favorable) for a YoY move."""
    if prior is None or pd.isna(prior) or pd.isna(current):
        return (None, "flat", None)
    diff = current - prior
    if abs(diff) < 1e-9:
        return ("flat", "flat", None)
    direction = "up" if diff > 0 else "down"
    favorable = (diff < 0) if lower_is_better else (diff > 0)
    return (None, direction, favorable)


def _business_model(row: pd.Series) -> str:
    return str(row.get("business_model", "operating")).lower()


def _valuation_premium(row: pd.Series, peer_median: dict) -> tuple[float | None, str]:
    """Premium vs the peer-group median on the relevant multiple.

    Operating/insurer names are read on EV/EBITDA; financials on P/E.
    Returns (premium, multiple_name).
    """
    if _business_model(row) == "financial":
        value, med, name = row.get("pe_ttm"), peer_median.get("pe_ttm"), "P/E"
    else:
        value, med, name = row.get("ev_to_ebitda_ttm"), peer_median.get("ev_to_ebitda_ttm"), "EV/EBITDA"
    if pd.isna(value) or med is None or pd.isna(med) or med <= 0:
        return None, name
    premium = float(value) / float(med) - 1
    # Sanity guard: premiums beyond +/-500% almost always mean broken inputs
    # (e.g. currency-unit mismatches on cross-listed names), not information.
    if abs(premium) > 5:
        return None, name
    return premium, name


# --- KPI construction -------------------------------------------------------

def _revenue_kpi(row: pd.Series, currency: str) -> Kpi:
    g = row.get("revenue_yoy_growth")
    pctile = row.get("revenue_yoy_growth_peer_pct")
    return Kpi(
        key="revenue_ttm",
        label="TTM Revenue",
        value=fmt_money(row.get("revenue_ttm"), currency),
        context=f"Trailing twelve months · {fmt_signed_pct(g)} YoY" if pd.notna(g) else "Trailing twelve months",
        signal=str(row.get("revenue_yoy_growth_signal", "n/a")),
        delta=fmt_signed_pct(g) if pd.notna(g) else None,
        delta_dir="up" if (pd.notna(g) and g > 0) else ("down" if pd.notna(g) else "flat"),
        delta_good=(g > 0) if pd.notna(g) else None,
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    )


def _margin_kpi(row: pd.Series, prior: pd.Series | None, metric: str, label: str) -> Kpi:
    m = row.get(metric)
    m_prior = prior.get(metric) if prior is not None else np.nan
    bps = (m - m_prior) if (pd.notna(m) and pd.notna(m_prior)) else None
    _, mdir, mgood = _delta(m, None if pd.isna(m_prior) else float(m_prior), lower_is_better=False)
    pctile = row.get(f"{metric}_peer_pct")
    return Kpi(
        key=metric,
        label=label,
        value=fmt_pct(m),
        context=f"TTM · {fmt_bps(bps)} YoY" if bps is not None else "TTM margin",
        signal=str(row.get(f"{metric}_signal", "n/a")),
        delta=fmt_bps(bps) if bps is not None else None,
        delta_dir=mdir,
        delta_good=mgood,
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    )


def _build_kpis_operating(row: pd.Series, prior: pd.Series | None, peer_median: dict) -> list[Kpi]:
    currency = row.get("currency", "BRL")

    def prior_val(col: str):
        if prior is None:
            return None
        v = prior.get(col)
        return None if pd.isna(v) else float(v)

    kpis: list[Kpi] = [_revenue_kpi(row, currency), _margin_kpi(row, prior, "ebitda_margin_ttm", "EBITDA Margin")]

    fc = row.get("fcf_conversion_ttm")
    fc_prior = prior_val("fcf_conversion_ttm")
    _, fdir, fgood = _delta(fc, fc_prior, lower_is_better=False)
    pctile = row.get("fcf_conversion_ttm_peer_pct")
    kpis.append(Kpi(
        key="fcf_conversion_ttm",
        label="FCF Conversion",
        value=fmt_pct(fc),
        context="FCF / EBITDA (TTM)",
        signal=str(row.get("fcf_conversion_ttm_signal", "n/a")),
        delta=fmt_signed_pct(fc - fc_prior) if (pd.notna(fc) and fc_prior is not None) else None,
        delta_dir=fdir,
        delta_good=fgood,
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    ))

    nd = row.get("net_debt_to_ebitda_ttm")
    nd_prior = prior_val("net_debt_to_ebitda_ttm")
    _, ndir, ngood = _delta(nd, nd_prior, lower_is_better=True)
    pctile = row.get("net_debt_to_ebitda_ttm_peer_pct")
    kpis.append(Kpi(
        key="net_debt_to_ebitda_ttm",
        label="Net Debt / EBITDA",
        value=fmt_multiple(nd),
        context="Leverage vs TTM EBITDA",
        signal=str(row.get("net_debt_to_ebitda_ttm_signal", "n/a")),
        delta=(f"{nd - nd_prior:+.1f}x" if (pd.notna(nd) and nd_prior is not None) else None),
        delta_dir=ndir,
        delta_good=ngood,
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    ))

    ev = row.get("ev_to_ebitda_ttm")
    ev_med = peer_median.get("ev_to_ebitda_ttm")
    prem = (ev / ev_med - 1) if (pd.notna(ev) and ev_med and not pd.isna(ev_med)) else None
    pctile = row.get("ev_to_ebitda_ttm_peer_pct")
    kpis.append(Kpi(
        key="ev_to_ebitda_ttm",
        label="EV / EBITDA",
        value=fmt_multiple(ev),
        context=(f"vs {fmt_multiple(ev_med)} peer median" if ev_med and pd.notna(ev_med) else "TTM"),
        signal=str(row.get("ev_to_ebitda_ttm_signal", "n/a")),
        delta=(f"{fmt_signed_pct(prem)} vs peers" if prem is not None else None),
        delta_dir=("up" if (prem is not None and prem > 0) else ("down" if prem is not None else "flat")),
        delta_good=None,  # a premium is neither inherently good nor bad
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    ))

    evr = row.get("ev_to_revenue_ttm")
    evr_med = peer_median.get("ev_to_revenue_ttm")
    kpis.append(Kpi(
        key="ev_to_revenue_ttm",
        label="EV / Revenue",
        value=fmt_multiple(evr),
        context=(f"vs {fmt_multiple(evr_med)} peer median" if evr_med and pd.notna(evr_med) else "TTM"),
        signal="n/a",
    ))
    return kpis


def _build_kpis_financial(row: pd.Series, prior: pd.Series | None, peer_median: dict) -> list[Kpi]:
    """Card set for lenders/banks: the EBITDA framework is not meaningful."""
    currency = row.get("currency", "BRL")
    kpis: list[Kpi] = [_revenue_kpi(row, currency)]

    ni = row.get("net_income_ttm")
    kpis.append(Kpi(
        key="net_income_ttm",
        label="TTM Net Income",
        value=fmt_money(ni, currency),
        context="Bottom line (TTM)",
        signal="n/a",
    ))

    kpis.append(_margin_kpi(row, prior, "net_income_margin_ttm", "Net Income Margin"))

    pe = row.get("pe_ttm")
    pe_med = peer_median.get("pe_ttm")
    prem = (pe / pe_med - 1) if (pd.notna(pe) and pe_med and not pd.isna(pe_med) and pe_med > 0) else None
    pctile = row.get("pe_ttm_peer_pct")
    kpis.append(Kpi(
        key="pe_ttm",
        label="P / E",
        value=fmt_multiple(pe),
        context=(f"vs {fmt_multiple(pe_med)} peer median" if pe_med and pd.notna(pe_med) else "TTM earnings"),
        signal=str(row.get("pe_ttm_signal", "n/a")),
        delta=(f"{fmt_signed_pct(prem)} vs peers" if prem is not None else None),
        delta_dir=("up" if (prem is not None and prem > 0) else ("down" if prem is not None else "flat")),
        delta_good=None,
        percentile=float(pctile) if pd.notna(pctile) else None,
        percentile_label=f"{fmt_ordinal(pctile)} pctile vs peers" if pd.notna(pctile) else None,
    ))

    kpis.append(Kpi(
        key="market_cap",
        label="Market Cap",
        value=fmt_money(row.get("market_cap"), currency),
        context="Equity value · EBITDA framework n/m for financials",
        signal="n/a",
    ))
    return kpis


def _build_kpis(row: pd.Series, prior: pd.Series | None, peer_median: dict) -> list[Kpi]:
    if _business_model(row) == "financial":
        return _build_kpis_financial(row, prior, peer_median)
    return _build_kpis_operating(row, prior, peer_median)


# --- narrative --------------------------------------------------------------

def _build_positives(row: pd.Series, prior: pd.Series | None, peer_median: dict) -> list[str]:
    financial = _business_model(row) == "financial"
    out: list[str] = []
    g = row.get("revenue_yoy_growth")
    if pd.notna(g) and g >= 0.10:
        out.append(f"Top line compounding at {fmt_pct(g)} YoY, ahead of the +10% watch threshold.")

    margin_metric = "net_income_margin_ttm" if financial else "ebitda_margin_ttm"
    margin_name = "net income margin" if financial else "EBITDA margin"
    m = row.get(margin_metric)
    m_prior = prior.get(margin_metric) if prior is not None else np.nan
    if pd.notna(m) and pd.notna(m_prior) and (m - m_prior) >= 0.005:
        out.append(f"{margin_name.capitalize()} expanding {fmt_bps(m - m_prior)} YoY to {fmt_pct(m)}.")
    elif pd.notna(m) and str(row.get(f"{margin_metric}_signal", "")) == "green":
        out.append(f"Healthy {fmt_pct(m)} TTM {margin_name}, in the upper band for the peer group.")

    if not financial:
        fc = row.get("fcf_conversion_ttm")
        if pd.notna(fc) and fc >= 0.60:
            out.append(f"Strong cash conversion at {fmt_pct(fc)} of EBITDA, supporting self-funded growth.")
        nd = row.get("net_debt_to_ebitda_ttm")
        if pd.notna(nd) and nd <= 1.0:
            descriptor = "a net cash position" if nd < 0 else "conservative leverage"
            out.append(f"Balance sheet carries {descriptor} at {fmt_multiple(nd)} net debt / EBITDA.")

    pct = row.get(f"{margin_metric}_peer_pct")
    if pd.notna(pct) and pct >= 0.75:
        out.append(f"Profitability ranks in the {fmt_ordinal(pct)} percentile of the peer group.")
    if not out:
        out.append("No KPI breaches under the watchlist thresholds; the name screens as steady-state.")
    return out[:5]


def _build_concerns(row: pd.Series, prior: pd.Series | None) -> list[str]:
    financial = _business_model(row) == "financial"
    out: list[str] = []
    g = row.get("revenue_yoy_growth")
    if pd.notna(g) and g < 0.02:
        out.append(f"Revenue growth has stalled at {fmt_pct(g)} YoY, below the +2% watch line.")

    margin_metric = "net_income_margin_ttm" if financial else "ebitda_margin_ttm"
    margin_name = "net income margin" if financial else "EBITDA margin"
    m = row.get(margin_metric)
    m_prior = prior.get(margin_metric) if prior is not None else np.nan
    if pd.notna(m) and pd.notna(m_prior) and (m - m_prior) <= -0.01:
        out.append(f"{margin_name.capitalize()} compressed {fmt_bps(m - m_prior)} YoY to {fmt_pct(m)}.")
    if pd.notna(m) and str(row.get(f"{margin_metric}_signal", "")) == "red":
        out.append(f"Thin profitability at {fmt_pct(m)} TTM {margin_name}.")

    if not financial:
        fc = row.get("fcf_conversion_ttm")
        if pd.notna(fc) and fc < 0.30:
            out.append(f"Weak cash conversion at {fmt_pct(fc)} of EBITDA points to working-capital or capex drag.")
        elif pd.isna(fc) and bool(row.get("ttm_complete", True)):
            out.append("Cash conversion is not computable from reported data — a data-completeness gap to close.")
        nd = row.get("net_debt_to_ebitda_ttm")
        if pd.notna(nd) and nd >= 3.5:
            out.append(f"Elevated leverage at {fmt_multiple(nd)} net debt / EBITDA narrows the margin for error.")
        ic = row.get("interest_coverage_ttm")
        if pd.notna(ic) and ic < 2.0:
            out.append(f"Thin interest coverage at {fmt_multiple(ic)} EBITDA / interest.")

    if not out:
        out.append("No material concerns flagged this quarter; continue standard coverage.")
    return out[:5]


def _core_signals(row: pd.Series) -> dict[str, str]:
    """The applicable core KPI signals for the verdict, by business model."""
    if _business_model(row) == "financial":
        candidates = {
            "revenue growth": row.get("revenue_yoy_growth_signal"),
            "net income margin": row.get("net_income_margin_ttm_signal"),
        }
    else:
        candidates = {
            "revenue growth": row.get("revenue_yoy_growth_signal"),
            "EBITDA margin": row.get("ebitda_margin_ttm_signal"),
            "cash conversion": row.get("fcf_conversion_ttm_signal"),
            "leverage": row.get("net_debt_to_ebitda_ttm_signal"),
        }
    return {k: str(v) for k, v in candidates.items() if str(v) in _REAL_SIGNALS}


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _verdict(row: pd.Series, premium: float | None, multiple_name: str) -> tuple[str, str]:
    """Watchlist verdict from operating signals *and* valuation vs peers."""
    core = _core_signals(row)
    reds = [k for k, v in core.items() if v == "red"]
    greens = [k for k, v in core.items() if v == "green"]
    yellows = [k for k, v in core.items() if v == "yellow"]

    growth = core.get("revenue growth")
    profitability = core.get("EBITDA margin") or core.get("net income margin")

    broken = len(reds) >= 2 or (growth == "red" and profitability == "red")
    strong = (
        growth == "green"
        and profitability != "red"
        and len(reds) == 0
        and len(greens) >= min(3, max(2, len(core) - 1))
    )
    cheap = premium is not None and premium <= CHEAP_GATE
    rich = premium is not None and premium >= RICH_GATE

    prem_txt = f"{fmt_signed_pct(premium)} vs the peer-group median {multiple_name}" if premium is not None else None

    if broken:
        if cheap:
            return "do_work", (
                f"Core KPIs are deteriorating ({_join(reds)}) but the market already prices it "
                f"({prem_txt}). Value trap or entry point — this is the debate to have now."
            )
        if premium is None:
            return "watch", (
                f"Core KPIs are deteriorating ({_join(reds)}); valuation context is incomplete, "
                f"so hold at Watch until the multiple can be benchmarked."
            )
        return "avoid", (
            f"Core KPIs are deteriorating ({_join(reds)}) and the valuation offers no support "
            f"({prem_txt}). No edge at this price."
        )

    if strong:
        if cheap:
            return "do_work", (
                f"Operating profile is on track ({_join(greens)}) yet the name trades at {prem_txt}. "
                f"Potential mispriced quality — prioritize the work."
            )
        if rich:
            return "constructive", (
                f"On track across {_join(greens)}, but the multiple already pays for it ({prem_txt}). "
                f"Own the story, don't chase it."
            )
        return "constructive", f"On track across {_join(greens)}; valuation is not a blocker."

    if len(reds) == 1:
        tail = f" Valuation sits at {prem_txt}." if prem_txt else ""
        return "watch", f"{reds[0].capitalize()} screens red; watch for confirmation next quarter.{tail}"
    if len(yellows) >= 2:
        return "watch", f"Amber readings on {_join(yellows)} suggest the trajectory needs watching."
    return "watch", "KPIs are broadly in range; maintain standard coverage."


def _commentary(row: pd.Series, prior: pd.Series | None) -> str:
    financial = _business_model(row) == "financial"
    name = row.get("company_name", "The company")
    g = row.get("revenue_yoy_growth")
    margin_metric = "net_income_margin_ttm" if financial else "ebitda_margin_ttm"
    margin_name = "net income margin" if financial else "EBITDA margin"
    m = row.get(margin_metric)
    m_prior = prior.get(margin_metric) if prior is not None else np.nan
    fc = row.get("fcf_conversion_ttm")
    nd = row.get("net_debt_to_ebitda_ttm")

    parts: list[str] = []
    if pd.notna(g):
        trend = "growth" if g >= 0 else "a contraction"
        parts.append(f"{name} posted {fmt_pct(g)} TTM revenue {trend} versus the prior-year quarter")
    else:
        parts.append(f"{name} reported the latest quarter")
    if pd.notna(m):
        if pd.notna(m_prior) and abs(m - m_prior) >= 0.005:
            move = "expansion" if m > m_prior else "compression"
            parts.append(f"with {margin_name} at {fmt_pct(m)} ({fmt_bps(m - m_prior)} {move} YoY)")
        else:
            parts.append(f"with a {margin_name} of {fmt_pct(m)}")
    sentence_one = ", ".join(parts) + "."

    tail: list[str] = []
    if not financial and pd.notna(fc):
        quality = "robust" if fc >= 0.6 else ("adequate" if fc >= 0.3 else "soft")
        tail.append(f"Cash conversion is {quality} at {fmt_pct(fc)} of EBITDA")
    if not financial and pd.notna(nd):
        lev = "a net cash position" if nd < 0 else f"{fmt_multiple(nd)} net leverage"
        tail.append(f"and the balance sheet carries {lev}")
    sentence_two = (", ".join(tail) + ".") if tail else ""
    return (sentence_one + " " + sentence_two).strip()


def _investment_view(row: pd.Series, verdict_key: str, premium: float | None, multiple_name: str) -> str:
    stance = {
        "do_work": "Through an investment lens this is where diligence hours pay: the spread between "
                   "what the operations say and what the price implies is wide enough to matter.",
        "constructive": "Through an investment lens this is a compounding story tracking to plan; the work "
                        "is monitoring the thesis, protecting the multiple, and sizing on weakness.",
        "watch": "Through an investment lens the signal mix is not yet actionable; let the next quarter "
                 "confirm direction before committing diligence time.",
        "avoid": "Through an investment lens the risk/reward is unattractive: fundamentals are deteriorating "
                 "and the price does not compensate for it.",
    }[verdict_key]

    val_note = ""
    if premium is not None:
        if premium > 0.10:
            val_note = (f" The market already pays a {fmt_signed_pct(premium)} {multiple_name} premium to peers, "
                        f"so returns lean on execution rather than re-rating.")
        elif premium < -0.10:
            val_note = (f" Trading at a {fmt_signed_pct(premium)} discount to the peer median leaves room for a "
                        f"re-rating if the operating story holds.")
        else:
            val_note = " Valuation sits broadly in line with peers, so returns hinge on operational delivery."
    return stance + val_note


def _management_questions(red_flags: list[dict], row: pd.Series) -> list[str]:
    questions = [f["management_question"] for f in red_flags if f.get("management_question")]
    g = row.get("revenue_yoy_growth")
    if pd.notna(g) and g >= 0.10:
        questions.append("How durable is the current growth rate, and what is the organic vs inorganic split?")
    questions.append("What are the top two uses of free cash flow over the next 12 months, and at what return?")
    seen, ordered = set(), []
    for q in questions:
        if q not in seen:
            seen.add(q)
            ordered.append(q)
    return ordered[:6]


def _valuation(row: pd.Series, peer_median: dict, premium: float | None, multiple_name: str) -> dict:
    financial = _business_model(row) == "financial"
    ev = row.get("ev_to_ebitda_ttm")
    evr = row.get("ev_to_revenue_ttm")
    pe = row.get("pe_ttm")
    ev_med = peer_median.get("ev_to_ebitda_ttm")
    evr_med = peer_median.get("ev_to_revenue_ttm")
    pe_med = peer_median.get("pe_ttm")

    anchor_val = fmt_multiple(pe if financial else ev)
    anchor_med = fmt_multiple(pe_med if financial else ev_med)

    if premium is None:
        stance, commentary = "n/a", "Insufficient data to position valuation against the peer-group median."
    elif premium > 0.10:
        stance = "premium"
        commentary = (
            f"Trades at {anchor_val} {multiple_name}, a {fmt_signed_pct(premium)} premium to the {anchor_med} "
            f"peer-group median. The premium is defensible only if growth and profitability stay top-quartile."
        )
    elif premium < -0.10:
        stance = "discount"
        commentary = (
            f"Trades at {anchor_val} {multiple_name}, a {fmt_signed_pct(premium)} discount to the {anchor_med} "
            f"peer-group median — a re-rating candidate if the operating concerns prove transitory."
        )
    else:
        stance = "in line"
        commentary = (
            f"Trades broadly in line with the peer group at {anchor_val} {multiple_name} "
            f"(median {anchor_med}); returns will be driven by delivery, not multiple expansion."
        )

    g = row.get("revenue_yoy_growth")
    m = row.get("net_income_margin_ttm" if financial else "ebitda_margin_ttm")
    fc = row.get("fcf_conversion_ttm")
    wntbt = []
    if premium is not None and premium > 0.10:
        if pd.notna(g):
            wntbt.append(f"Revenue growth holds at or above {fmt_pct(g)} to keep pace with embedded expectations.")
        if pd.notna(m):
            wntbt.append(f"Profitability is defended around {fmt_pct(m)} despite reinvestment.")
        if financial:
            wntbt.append("Credit costs stay contained so book value keeps compounding through the cycle.")
        else:
            wntbt.append("Cash conversion turns the premium multiple into real, distributable cash.")
    elif premium is not None and premium < -0.10:
        wntbt.append("At least one of the soft KPIs (growth, profitability, or conversion) stabilises next quarter.")
        wntbt.append("The market recognises the discount once the operating data inflects.")
    else:
        wntbt.append("Management executes the base plan; valuation offers limited cushion either way.")
        if not financial and pd.notna(fc):
            wntbt.append(f"Cash conversion stays near {fmt_pct(fc)} to fund growth without added leverage.")

    return {
        "ev_to_ebitda": fmt_multiple(ev),
        "ev_to_ebitda_median": fmt_multiple(ev_med),
        "ev_to_revenue": fmt_multiple(evr),
        "ev_to_revenue_median": fmt_multiple(evr_med),
        "pe": fmt_multiple(pe),
        "pe_median": fmt_multiple(pe_med),
        "premium": premium,
        "premium_label": fmt_signed_pct(premium) if premium is not None else "n/a",
        "multiple_name": multiple_name,
        "stance": stance,
        "commentary": commentary,
        "what_needs_to_be_true": wntbt,
    }


# --- public API -------------------------------------------------------------

def build_assessment(df: pd.DataFrame, company_id: str, store=None) -> Assessment:
    """Build the full judgment object for one company.

    ``store`` is an optional :class:`src.ingestion.store.WatchlistStore`;
    when provided, valuation-history percentiles, revision momentum, the
    attention score, and the analyst thesis are populated as well.
    """
    history = _company_history(df, company_id)
    row = history.iloc[-1]
    prior = _prior_year_row(history)
    resolution = resolve_peers(latest_rows(df), row)
    peers = resolution.peers

    peer_median = {
        col: _median(peers, col)
        for col in [
            "revenue_yoy_growth",
            "ebitda_margin_ttm",
            "net_income_margin_ttm",
            "fcf_conversion_ttm",
            "net_debt_to_ebitda_ttm",
            "ev_to_ebitda_ttm",
            "ev_to_revenue_ttm",
            "pe_ttm",
        ]
    }

    premium, multiple_name = _valuation_premium(row, peer_median)

    # V2 side-table context (all graceful when the store is absent/empty).
    financial = _business_model(row) == "financial"
    hist_column = "pe_ltm" if financial else "ev_to_ebitda_ltm"
    current_multiple = row.get("pe_ttm" if financial else "ev_to_ebitda_ttm")
    val_history = getattr(store, "valuation_history", None)
    estimates = getattr(store, "estimates", None)
    history_context = valuation_vs_history(
        val_history, company_id,
        None if pd.isna(current_multiple) else float(current_multiple),
        column=hist_column,
    )
    revisions = revision_momentum(estimates, company_id)

    red_flags = generate_red_flags(row, prior=prior, revisions=revisions)
    verdict_key, rationale = _verdict(row, premium, multiple_name)

    flags_count = sum(1 for f in red_flags if f.get("severity") in {"High", "Medium"})
    attention_score, attention_components = compute_attention(
        row, prior, premium, history_context.get("percentile"), revisions, flags_count,
    )

    thesis = None
    theses_dir = getattr(store, "theses_dir", None)
    if theses_dir is not None:
        thesis = load_thesis(company_id, theses_dir)

    return Assessment(
        company_id=company_id,
        row=row,
        prior=prior,
        peers=peers,
        peer_median=peer_median,
        kpis=_build_kpis(row, prior, peer_median),
        positives=_build_positives(row, prior, peer_median),
        concerns=_build_concerns(row, prior),
        red_flags=red_flags,
        management_questions=_management_questions(red_flags, row),
        commentary=_commentary(row, prior),
        sponsor_view=_investment_view(row, verdict_key, premium, multiple_name),
        verdict_key=verdict_key,
        verdict_label=VERDICT_LABELS[verdict_key],
        verdict_rationale=rationale,
        valuation=_valuation(row, peer_median, premium, multiple_name),
        history_context=history_context,
        revisions=revisions,
        attention_score=attention_score,
        attention_components=attention_components,
        thesis=thesis,
        peer_source=resolution.source,
        peer_reviewed=resolution.reviewed,
        peer_warning=resolution.warning,
        peer_set_name=resolution.set_name,
    )


# --- watchlist ranking ------------------------------------------------------

_VERDICT_RANK = {"do_work": 0, "avoid": 1, "watch": 2, "constructive": 3}


def watchlist_summary(df: pd.DataFrame, store=None) -> pd.DataFrame:
    """One ranked row per company for the Watchlist Home page.

    Primary ordering is the **attention score** (valuation dislocation,
    estimate revisions, operating inflection, flag pressure); verdict rank
    breaks ties so Do Work names float above equally-scored Watch names.
    """
    rows = []
    for company_id in latest_rows(df)["company_id"]:
        a = build_assessment(df, company_id, store=store)
        r = a.row
        financial = a.business_model == "financial"
        flags = [f for f in a.red_flags if f.get("severity") in {"High", "Medium"}]
        rows.append({
            "company_id": company_id,
            "ticker": str(r.get("ticker", "")).replace(".SA", ""),
            "company_name": r.get("company_name", ""),
            "theme": a.theme,
            "peer_group": a.peer_group,
            "business_model": a.business_model,
            "currency": r.get("currency", ""),
            "verdict_key": a.verdict_key,
            "verdict_label": a.verdict_label,
            "verdict_rationale": a.verdict_rationale,
            "attention_score": a.attention_score,
            "revenue_ttm": r.get("revenue_ttm"),
            "revenue_yoy_growth": r.get("revenue_yoy_growth"),
            "profitability": r.get("net_income_margin_ttm" if financial else "ebitda_margin_ttm"),
            "profitability_signal": str(r.get(("net_income_margin_ttm" if financial else "ebitda_margin_ttm") + "_signal", "n/a")),
            "growth_signal": str(r.get("revenue_yoy_growth_signal", "n/a")),
            "fcf_conversion_ttm": r.get("fcf_conversion_ttm"),
            "net_debt_to_ebitda_ttm": r.get("net_debt_to_ebitda_ttm"),
            "multiple_name": a.valuation.get("multiple_name", "EV/EBITDA"),
            "multiple_value": r.get("pe_ttm" if financial else "ev_to_ebitda_ttm"),
            "valuation_premium": a.valuation.get("premium"),
            "history_percentile": a.history_context.get("percentile"),
            "revision_direction": a.revisions.get("direction", "n/a"),
            "next_earnings_date": a.revisions.get("next_earnings_date"),
            "thesis_stage": a.thesis.stage_label if (a.thesis and a.thesis.exists) else "",
            "flags": len(flags),
            "as_of": r.get("period"),
        })
    out = pd.DataFrame(rows)
    out["_verdict_rank"] = out["verdict_key"].map(_VERDICT_RANK).fillna(9)
    out = out.sort_values(
        ["attention_score", "_verdict_rank", "flags"],
        ascending=[False, True, False],
    ).drop(columns=["_verdict_rank"]).reset_index(drop=True)
    out.insert(0, "rank", out.index + 1)
    return out
