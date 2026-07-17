"""Institutional valuation charts for the Valuation Case page and HTML export.

Every figure follows one restrained language: graphite ink on transparent/cream,
sage + graphite data hues, gold for the market/current reference, muted green
for upside and copper/oxblood for downside. No default-Plotly blue, no clutter.

Pure *data builders* (football-field ranges, bridge steps, provenance
classification) are separated from figure builders so the finance logic is
unit-testable without rendering.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.branding import FONT_SANS, FONT_SERIF, PALETTE

INK = PALETTE["ink"]
GRAPHITE = PALETTE["charcoal"]
SAGE = PALETTE["anchor"]
GOLD = PALETTE["gold"]
COPPER = PALETTE["copper"]
GREEN = PALETTE["green"]
RED = PALETTE["red"]
MUTED = PALETTE["muted"]
MUTED2 = PALETTE["muted_2"]
LINE = PALETTE["line"]
LINE_SOFT = PALETTE["line_soft"]
CREAM = PALETTE["cream"]

_AXIS = dict(
    showgrid=True, gridcolor=LINE_SOFT, zeroline=False,
    linecolor=LINE, ticks="outside", tickcolor=LINE, ticklen=4,
    tickfont=dict(size=11, color=PALETTE["slate"]),
    title_font=dict(size=11, color=MUTED),
)


def _style(fig: go.Figure, title: str, subtitle: str = "", height: int = 360) -> go.Figure:
    # Editorial pairing: serif display title (matches the app chrome), sans
    # kicker-style subtitle and data labels. Native title.subtitle carries its
    # own font — plotly's pseudo-HTML <span> cannot hold a quoted font stack.
    # Top margin reserves distinct bands for title, subtitle, and the legend
    # strip so none of the three ever touch.
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0, xanchor="left", y=0.98, yanchor="top",
                   font=dict(size=16.5, color=GRAPHITE, family=FONT_SERIF),
                   subtitle=dict(text=subtitle or None,
                                 font=dict(size=11, color=MUTED, family=FONT_SANS))),
        font=dict(family=FONT_SANS, color=PALETTE["slate"], size=12),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=24, r=20, t=92 if subtitle else 64, b=46),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    font=dict(size=10.5), bgcolor="rgba(0,0,0,0)",
                    itemwidth=30, tracegroupgap=4),
        hoverlabel=dict(font_size=12, font_family=FONT_SANS,
                        bordercolor=LINE, bgcolor=PALETTE["panel"],
                        font_color=INK),
    )
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def _empty_state(message: str, title: str, height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=12, color=MUTED2))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, title, height=height)


def _clean(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def apply_status_footnote(fig: go.Figure, case) -> go.Figure:
    """Stamp auto-anchored charts so screenshots can never be mistaken for a view.

    The note is anchored a fixed pixel distance below the plot area (not a
    paper fraction, which scales with height and used to land on the x-axis
    labels); the bottom margin is widened to guarantee the room.
    """
    status = getattr(case.assumptions, "status", None) or ("draft" if case.assumptions.from_file else "auto")
    if status == "auto":
        fig.add_annotation(
            x=0, y=0, xref="paper", yref="paper", xanchor="left", yanchor="top",
            yshift=-60,
            text="auto-anchored assumptions - calibration only, not an investment view",
            showarrow=False, font=dict(size=10, color=RED),
        )
        fig.update_layout(margin=dict(b=max(fig.layout.margin.b or 34, 84)))
    return fig


# =====================================================================================
# Data builders (pure, testable)
# =====================================================================================

def _implied_price_from_multiple(row: pd.Series, multiple: float) -> float | None:
    """EV/EBITDA multiple -> implied share price via the unit-safe equity ratio."""
    ebitda = _clean(row.get("ebitda_ttm"))
    market_cap = _clean(row.get("market_cap"))
    price = _clean(row.get("share_price"))
    if not ebitda or ebitda <= 0 or not market_cap or market_cap <= 0 or not price:
        return None
    net_debt = _clean(row.get("net_debt"))
    if net_debt is None:
        cash = _clean(row.get("cash_st_invest"))
        if cash is None:
            cash = _clean(row.get("cash"))
        net_debt = (_clean(row.get("total_debt")) or 0.0) - (cash or 0.0)
    minority = _clean(row.get("minority_interest")) or 0.0
    preferred = _clean(row.get("preferred_equity")) or 0.0
    implied_equity = ebitda * multiple - net_debt - minority - preferred
    if implied_equity <= 0:
        return None
    return price * implied_equity / market_cap


def _implied_price_from_revenue_multiple(row: pd.Series, multiple: float) -> float | None:
    """EV/Revenue multiple -> implied share price via the same equity bridge."""
    revenue = _clean(row.get("revenue_ttm"))
    market_cap = _clean(row.get("market_cap"))
    price = _clean(row.get("share_price"))
    if not revenue or revenue <= 0 or not market_cap or market_cap <= 0 or not price:
        return None
    net_debt = _clean(row.get("net_debt"))
    if net_debt is None:
        cash = _clean(row.get("cash_st_invest"))
        if cash is None:
            cash = _clean(row.get("cash"))
        net_debt = (_clean(row.get("total_debt")) or 0.0) - (cash or 0.0)
    minority = _clean(row.get("minority_interest")) or 0.0
    preferred = _clean(row.get("preferred_equity")) or 0.0
    implied_equity = revenue * multiple - net_debt - minority - preferred
    if implied_equity <= 0:
        return None
    return price * implied_equity / market_cap


def _implied_price_from_pe(row: pd.Series, pe: float) -> float | None:
    """Peer P/E applied to anchor EPS: implied = price x (peer PE / own PE)."""
    price = _clean(row.get("share_price"))
    own_pe = _clean(row.get("pe_ttm"))
    if not price or not own_pe or own_pe <= 0 or pe is None or pe <= 0:
        return None
    return price * pe / own_pe


def football_field_data(case, price_history: pd.DataFrame | None = None) -> dict:
    """Ranges for the football field. Every range optional; skipped when absent.

    ``price_history``: optional monthly valuation-history frame for the anchor
    (columns date/share_price) used to derive the 52-week range when the
    dedicated export fields are absent. No analyst consensus target is
    exported, so that classic bar is not drawn - documented limitation.
    """
    row = case.assessment.row
    price = _clean(row.get("share_price"))
    ranges: list[dict] = []

    # DCF scenarios.
    targets = {k: case.scenarios[k].target_price for k in ("bear", "base", "bull")}
    if all(v is not None for v in targets.values()):
        ranges.append({
            "label": "DCF (bear-bull)",
            "low": min(targets.values()),
            "high": max(targets.values()),
            "mid": targets["base"],
            "note": f"base {targets['base']:,.2f}",
        })

    stats = case.spread_stats

    def _comps_range(metric: str, label: str, implied) -> None:
        if metric not in stats.index:
            return
        q1, q3 = stats.loc[metric, "q1"], stats.loc[metric, "q3"]
        med = stats.loc[metric, "adjusted_median"]
        lo = implied(row, q1) if pd.notna(q1) else None
        hi = implied(row, q3) if pd.notna(q3) else None
        mid = implied(row, med) if pd.notna(med) else None
        if lo is not None and hi is not None and hi > lo:
            ranges.append({"label": label, "low": lo, "high": hi, "mid": mid,
                           "note": f"{q1:.1f}x-{q3:.1f}x"})

    # Peer comps quartiles, one bar per applicable multiple lens.
    _comps_range("ev_to_ebitda_ttm", "EV/EBITDA LTM comps (25th-75th pct)", _implied_price_from_multiple)
    _comps_range("ev_to_revenue_ttm", "EV/Revenue LTM comps (25th-75th pct)", _implied_price_from_revenue_multiple)
    _comps_range("pe_ttm", "P/E LTM comps (25th-75th pct)", _implied_price_from_pe)

    # Own multiple history band.
    hc = case.assessment.history_context
    if hc.get("available") and hc.get("low") and hc.get("high"):
        lo = _implied_price_from_multiple(row, hc["low"])
        hi = _implied_price_from_multiple(row, hc["high"])
        mid = _implied_price_from_multiple(row, hc["median"]) if hc.get("median") else None
        if lo is not None and hi is not None and hi > lo:
            ranges.append({"label": f"Own multiple history ({hc['n_obs']} obs)", "low": lo, "high": hi,
                           "mid": mid, "note": f"{hc['low']:.1f}x-{hc['high']:.1f}x"})

    # 52-week price range: exported fields first, else derived from the
    # monthly price history (approximate - monthly closes, labeled as such).
    wk_lo, wk_hi = _clean(row.get("week52_low")), _clean(row.get("week52_high"))
    if not (wk_lo and wk_hi) and price_history is not None and not price_history.empty \
            and {"date", "share_price"}.issubset(price_history.columns):
        recent = price_history[price_history["date"]
                               >= price_history["date"].max() - pd.DateOffset(months=12)]
        prices = pd.to_numeric(recent["share_price"], errors="coerce").dropna()
        if len(prices) >= 6:
            wk_lo, wk_hi = float(prices.min()), float(prices.max())
    if wk_lo and wk_hi and wk_hi > wk_lo:
        ranges.append({"label": "52-week range (monthly closes)", "low": wk_lo, "high": wk_hi,
                       "mid": None, "note": ""})

    return {"ranges": ranges, "current_price": price,
            "base_target": case.base.target_price, "currency": str(row.get("currency", ""))}


def fcf_bridge_data(forecast: pd.DataFrame, year_index: int = -1) -> list[dict]:
    """Waterfall steps: EBITDA - taxes - capex - dNWC = UFCF (D&A nets out)."""
    r = forecast.iloc[year_index]
    return [
        {"label": f"EBITDA (Y{int(r['year'])})", "value": float(r["ebitda"]), "measure": "absolute"},
        {"label": "Taxes", "value": -float(r["taxes"]), "measure": "relative"},
        {"label": "Capex", "value": -float(r["capex"]), "measure": "relative"},
        {"label": "Change in NWC", "value": -float(r["delta_nwc"]), "measure": "relative"},
        {"label": "UFCF", "value": float(r["ufcf"]), "measure": "total"},
    ]


def equity_bridge_data(base) -> list[dict]:
    steps = [
        {"label": "PV of explicit FCF", "value": base.pv_explicit, "measure": "absolute"},
        {"label": "PV of terminal value", "value": base.pv_terminal_exit, "measure": "relative"},
        {"label": "Enterprise value", "value": base.enterprise_value, "measure": "total"},
        {"label": "Net debt", "value": -base.net_debt, "measure": "relative"},
    ]
    if base.minority_interest:
        steps.append({"label": "Minority interest", "value": -base.minority_interest, "measure": "relative"})
    if base.preferred_equity:
        steps.append({"label": "Preferred equity", "value": -base.preferred_equity, "measure": "relative"})
    steps.append({"label": "Implied equity", "value": base.implied_equity, "measure": "total"})
    return steps


_STATUS_LABELS = {
    "auto": "AUTO-ANCHORED - NOT AN INVESTMENT VIEW",
    "illustrative": "ILLUSTRATIVE ASSUMPTIONS - NOT A FINAL VIEW",
    "draft": "ANALYST DRAFT",
    "final": "ANALYST ASSUMPTIONS",
}


def assumptions_status(case) -> tuple[str, str]:
    """(status_key, banner label) for the disclosure badge."""
    status = getattr(case.assumptions, "status", None) or ("draft" if case.assumptions.from_file else "auto")
    return status, _STATUS_LABELS.get(status, status.upper())


def assumptions_provenance(case) -> pd.DataFrame:
    """Classify every material input: analyst | anchored | default."""
    a = case.assumptions
    w = case.wacc
    items: list[dict] = []

    for name in ("bear", "base", "bull"):
        scen = a.scenarios[name]
        items.append({
            "item": f"{name.title()} scenario drivers",
            "value": f"g {scen.revenue_growth[0]:+.0%}->{scen.revenue_growth[-1]:+.0%}, "
                     f"margin {scen.ebitda_margin[-1]:.0%}",
            "source": "analyst" if scen.source == "analyst" else "anchored",
        })

    beta_map = {"analyst": "analyst", "market_data": "anchored", "peers": "anchored", "default": "default"}
    items.append({"item": "Beta", "value": f"{w.beta:.2f} ({w.beta_source})",
                  "source": beta_map.get(w.beta_source, "default")})
    items.append({"item": "Cost of debt (pre-tax)", "value": f"{w.cost_of_debt_pretax:.1%}",
                  "source": "analyst" if a.pretax_cost_of_debt is not None else
                            ("default" if any("no interest/debt data" in n for n in w.notes) else "anchored")})
    items.append({"item": "Rate environment (rf/ERP/tax)",
                  "value": f"rf {w.risk_free_rate:.1%}, ERP {w.equity_risk_premium:.1%}, tax {w.tax_rate:.0%}",
                  "source": "anchored"})
    if w.overridden:
        items.append({"item": "WACC override", "value": f"{w.wacc:.1%}", "source": "analyst"})
    items.append({"item": "Terminal WACC", "value": f"{a.terminal_wacc:.1%} ({a.terminal_wacc_source})",
                  "source": "analyst" if a.terminal_wacc_source == "analyst" else "anchored"})

    items.append({"item": "Exit multiple", "value": f"{case.exit_multiple:.1f}x ({case.exit_multiple_source})",
                  "source": "analyst" if "analyst" in case.exit_multiple_source else
                            ("default" if "fallback" in " ".join(case.notes) and "peer" not in case.exit_multiple_source
                             else "anchored")})
    items.append({
        "item": "Market multiple reference",
        "value": (f"{case.market_reference_multiple:.1f}x ({case.market_reference_source})"
                  if case.market_reference_multiple is not None else case.market_reference_source),
        "source": "anchored" if case.market_reference_multiple is not None else "default",
    })
    items.append({"item": "Perpetuity growth", "value": f"{a.perpetuity_growth:.1%}",
                  "source": getattr(a, "perpetuity_source", "anchored")})
    items.append({"item": "Terminal ROIC", "value": f"{a.terminal_roic:.1%}",
                  "source": getattr(a, "terminal_roic_source", "anchored")})
    items.append({"item": "Stable reinvestment",
                  "value": f"g / ROIC = {case.base.terminal_reinvestment_rate:.1%}"
                  if case.base.terminal_reinvestment_rate is not None else "n/m",
                  "source": "anchored"})
    items.append({"item": "Working capital basis",
                  "value": "DSO/DIH/DPO days" if a.scenarios["base"].nwc_mode == "days" else "% of revenue",
                  "source": "anchored" if a.scenarios["base"].nwc_mode == "days" else "default"})

    for note in a.anchors.get("notes", []):
        if "defaulted" in note or "assuming zero" in note:
            items.append({"item": "Anchor fallback", "value": note, "source": "default"})

    return pd.DataFrame(items)


# =====================================================================================
# Figures
# =====================================================================================

def football_field_chart(case, height: int | None = None,
                         price_history: pd.DataFrame | None = None) -> go.Figure:
    data = football_field_data(case, price_history=price_history)
    ranges, price = data["ranges"], data["current_price"]
    if not ranges or price is None:
        return _empty_state("Insufficient data for a valuation range chart.", "Valuation Football Field", 300)

    # Dynamic height: breathing room per range bar plus the label/footnote bands.
    height = height or max(340, 210 + 78 * len(ranges))

    fig = go.Figure()
    labels = [r["label"] for r in ranges]
    fig.add_bar(
        y=labels, x=[r["high"] - r["low"] for r in ranges], base=[r["low"] for r in ranges],
        orientation="h", marker=dict(color=PALETTE["sage_soft"], line=dict(color=SAGE, width=1.2)),
        width=0.55,
        hovertemplate="%{y}<br>%{base:,.2f} - %{customdata:,.2f}<extra></extra>",
        customdata=[r["high"] for r in ranges], showlegend=False,
    )
    mids = [(r["label"], r["mid"]) for r in ranges if r.get("mid") is not None]
    if mids:
        # Explained in the subtitle rather than a legend: the legend strip
        # would share the band where the current/target labels live.
        fig.add_scatter(y=[m[0] for m in mids], x=[m[1] for m in mids], mode="markers",
                        marker=dict(symbol="line-ns", size=16, line=dict(color=GRAPHITE, width=2.5)),
                        name="mid / base", showlegend=False,
                        hovertemplate="mid %{x:,.2f}<extra></extra>")

    # Price labels sit on two stacked rows just above the plot area (fixed
    # pixel offsets), so they cannot collide with each other, the subtitle,
    # or the x-axis labels below. Anchors flip when the lines are close.
    target = data["base_target"]
    close = target is not None and price and abs(target - price) / price < 0.10
    current_anchor = ("right" if (close and target >= price) else "center")
    fig.add_vline(x=price, line=dict(color=GOLD, width=2, dash="dash"))
    fig.add_annotation(x=price, y=1.0, yref="paper", yanchor="bottom", yshift=3,
                       text=f"current {price:,.2f}",
                       showarrow=False, xanchor=current_anchor, font=dict(size=11, color=GOLD))
    if target is not None:
        target_anchor = ("left" if (close and target >= price) else
                         ("right" if close else "center"))
        fig.add_vline(x=target, line=dict(color=GREEN, width=1.4))
        fig.add_annotation(x=target, y=1.0, yref="paper", yanchor="bottom", yshift=17,
                           text=f"target {target:,.2f}", showarrow=False,
                           xanchor=target_anchor, font=dict(size=11, color=GREEN))
    fig = _style(fig, "Valuation Football Field",
                 "Implied share price ranges | gold dash = current | green = base target | tick = mid/base", height)
    fig.update_yaxes(showgrid=False, autorange="reversed", automargin=True)
    fig.update_xaxes(title=f"Share price ({data['currency']})")
    fig.update_layout(margin=dict(t=112))
    return apply_status_footnote(fig, case)


def sensitivity_heatmap(case, height: int = 480) -> go.Figure:
    grid = case.sens_wacc_multiple
    price = case.base.current_price
    z = grid.values.astype(float)
    fig = go.Figure(go.Heatmap(
        z=z, x=list(grid.columns), y=list(grid.index),
        colorscale=[[0.0, COPPER], [0.5, CREAM], [1.0, GREEN]],
        zmid=price if price else float(np.nanmean(z)),
        text=[[f"{v:,.2f}" if not np.isnan(v) else "n/a" for v in r] for r in z],
        texttemplate="%{text}", textfont=dict(size=11.5, family=FONT_SANS),
        showscale=False, xgap=4, ygap=6,
        hovertemplate="WACC %{y} | exit %{x}<br>target %{z:,.2f}<extra></extra>",
    ))
    # Outline + label the base-case cell (center).
    ci, cj = len(grid.index) // 2, len(grid.columns) // 2
    fig.add_shape(type="rect", x0=cj - 0.5, x1=cj + 0.5, y0=ci - 0.5, y1=ci + 0.5,
                  line=dict(color=GRAPHITE, width=3))
    fig.add_annotation(x=cj, y=ci - 0.5, yanchor="bottom", yshift=2, text="BASE",
                       showarrow=False,
                       font=dict(size=9, color=GRAPHITE, family=FONT_SANS))
    subtitle = "Target price | outlined cell = base case"
    if price:
        subtitle += f" | green = above current {price:,.2f}"
    fig = _style(fig, "DCF Sensitivity - WACC x Exit Multiple", subtitle, height)
    # Explicit category axes: the labels are formatted strings, and letting
    # the browser's plotly build infer the type scrambles the grid.
    fig.update_xaxes(title="Exit EV/EBITDA", showgrid=False, side="top", type="category")
    fig.update_yaxes(title="WACC", showgrid=False, autorange="reversed", type="category")
    # The top-side axis (ticks + axis title) needs its own band under the
    # title/subtitle block, otherwise the three stacks overlap.
    fig.update_layout(margin=dict(t=136))
    return apply_status_footnote(fig, case)


def current_ev_bridge_chart(bridge: dict, height: int = 360) -> go.Figure:
    """Market cap -> calculated EV waterfall, with the reported TEV reference."""
    if not bridge.get("available"):
        return _empty_state("EV bridge inputs missing.", "Current EV Bridge")
    labels = ["Market cap", "+ Total debt", "+ Minority", "+ Preferred"]
    values = [bridge["market_cap"], bridge["total_debt"],
              bridge["minority_interest"], bridge["preferred_equity"]]
    if bridge.get("lease_liabilities") is not None:
        labels.append("+ Leases")
        values.append(bridge["lease_liabilities"])
    labels += ["- Cash", "Calculated EV"]
    values += [-bridge["cash"], bridge["calculated_ev"]]
    measures = ["absolute"] + ["relative"] * (len(labels) - 2) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measures,
        connector=dict(line=dict(color=LINE, width=1)),
        increasing=dict(marker=dict(color=SAGE)),
        decreasing=dict(marker=dict(color=COPPER)),
        totals=dict(marker=dict(color=GRAPHITE)),
        text=[f"{v:,.0f}" for v in values], textposition="outside",
        textfont=dict(size=10.5, family=FONT_SANS), cliponaxis=False,
        hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
    ))
    subtitle = "partial bridge (minority/preferred not exported)" if bridge.get("partial") \
        else "full bridge"
    if bridge.get("reported_ev"):
        fig.add_hline(y=bridge["reported_ev"], line=dict(color=GOLD, width=2, dash="dash"),
                      annotation_text=f"reported TEV {bridge['reported_ev']:,.0f}"
                                      + (f" ({bridge['gap']:+.0%})" if bridge.get("gap") is not None else ""),
                      annotation_position="top left",
                      annotation_font=dict(size=10, color=GOLD))
    fig = _style(fig, "Current EV Bridge", f"Calculated vs reported enterprise value | {subtitle}", height)
    fig.update_layout(showlegend=False, margin=dict(b=44))
    return fig


def value_creation_bridge_chart(lbo, height: int = 380) -> go.Figure:
    """PE attribution: equity check -> EBITDA growth / multiple / deleveraging -> exit."""
    b = lbo.bridge
    if not b or not lbo.valid:
        return _empty_state("LBO not applicable for this name.", "Value-Creation Bridge")
    labels = ["Equity check", "EBITDA growth", "Multiple change", "Deleveraging",
              "Excess cash", "Fees", "Exit equity"]
    values = [b["equity_check"], b["ebitda_growth"], b["multiple_change"],
              b["deleveraging"], b.get("excess_cash", 0.0), b["fees"], b["exit_equity"]]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values,
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "total"],
        connector=dict(line=dict(color=LINE, width=1)),
        increasing=dict(marker=dict(color=GREEN)),
        decreasing=dict(marker=dict(color=RED)),
        totals=dict(marker=dict(color=SAGE)),
        text=[f"{v:,.0f}" for v in values], textposition="outside",
        textfont=dict(size=11, family=FONT_SANS), cliponaxis=False,
        hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
    ))
    moic_txt = f"{lbo.moic:.1f}x MOIC" if lbo.moic else "MOIC n/a"
    irr_txt = f"{lbo.irr:.0%} IRR" if lbo.irr is not None else "IRR n/a"
    fig = _style(fig, "Value-Creation Bridge",
                 f"{lbo.horizon}-year hold | {moic_txt} | {irr_txt} | where the sponsor return comes from", height)
    fig.update_yaxes(title="Equity value")
    fig.update_layout(showlegend=False, margin=dict(b=44))
    return fig


def debt_paydown_chart(lbo, height: int = 340) -> go.Figure:
    """Debt outstanding + leverage through the hold (100% cash sweep)."""
    s = lbo.schedule
    if s.empty or not lbo.valid:
        return _empty_state("LBO not applicable for this name.", "Debt Paydown")
    years = [f"Y{int(y)}" for y in s["year"]]
    fig = go.Figure()
    fig.add_bar(x=years, y=s["debt_end"], name="Debt outstanding", marker_color=COPPER,
                marker_line_width=0, opacity=0.9,
                hovertemplate="Debt: %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=years, y=s["leverage"], name="Leverage", mode="lines+markers",
                    line=dict(color=GOLD, width=2.6), marker=dict(size=6), yaxis="y2",
                    hovertemplate="%{y:.1f}x EBITDA<extra></extra>")
    fig = _style(fig, "Debt Paydown",
                 f"Entry {lbo.debt_pct:.0%} debt at {lbo.cost_of_debt:.1%} cost | 100% cash sweep", height)
    fig.update_yaxes(title="Debt outstanding")
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", ticksuffix="x",
                                  showgrid=False, zeroline=False,
                                  tickfont=dict(size=11, color=GOLD),
                                  title=dict(text="Debt / EBITDA", font=dict(size=11, color=GOLD))))
    return fig


def implied_growth_heatmap(case, height: int = 460) -> go.Figure:
    """What growth-forever does each WACC x exit-multiple cell embed?"""
    grid = getattr(case, "sens_implied_growth", None)
    if grid is None or grid.empty:
        return _empty_state("Implied growth grid not available.", "Implied Perpetuity Growth")
    anchor = case.assumptions.perpetuity_growth
    z = grid.values.astype(float)
    fig = go.Figure(go.Heatmap(
        z=z, x=list(grid.columns), y=list(grid.index),
        colorscale=[[0.0, CREAM], [0.5, "#efe6cf"], [1.0, RED]],
        zmid=anchor,
        text=[[f"{v:+.1%}" if not np.isnan(v) else "n/a" for v in r] for r in z],
        texttemplate="%{text}", textfont=dict(size=11.5, family=FONT_SANS),
        showscale=False, xgap=4, ygap=6,
        hovertemplate="WACC %{y} | exit %{x}<br>implied g %{z:.1%}<extra></extra>",
    ))
    ci, cj = len(grid.index) // 2, len(grid.columns) // 2
    fig.add_shape(type="rect", x0=cj - 0.5, x1=cj + 0.5, y0=ci - 0.5, y1=ci + 0.5,
                  line=dict(color=GRAPHITE, width=3))
    fig = _style(fig, "Implied Perpetuity Growth",
                 f"Implied growth-forever | red = above the {anchor:.1%} long-run anchor", height)
    fig.update_xaxes(title="Exit EV/EBITDA", showgrid=False, side="top", type="category")
    fig.update_yaxes(title="WACC", showgrid=False, autorange="reversed", type="category")
    # Top-side axis gets its own band under the title/subtitle block.
    fig.update_layout(margin=dict(t=136))
    return apply_status_footnote(fig, case)


def tornado_chart(case, height: int = 430) -> go.Figure:
    """One-way driver sensitivity of the target price, widest bar first."""
    t = getattr(case, "tornado", None)
    if t is None or t.empty:
        return _empty_state("Tornado not computable for this case.", "Driver Sensitivity")
    base = float(t["base_price"].iloc[0])
    t = t.iloc[::-1]  # widest at the top after axis flip
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=t["driver"], x=t["high_price"] - t["low_price"], base=t["low_price"],
        orientation="h", marker_color=SAGE, marker_line_width=0, opacity=0.9,
        customdata=np.stack([t["low_price"], t["high_price"],
                             t["low_label"], t["high_label"]], axis=-1),
        hovertemplate="%{y}<br>%{customdata[2]}: %{customdata[0]:,.2f} | "
                      "%{customdata[3]}: %{customdata[1]:,.2f}<extra></extra>",
    ))
    for _, r in t.iterrows():
        fig.add_annotation(x=r["low_price"], y=r["driver"], text=str(r["low_label"]),
                           showarrow=False, xanchor="right", xshift=-6,
                           font=dict(size=10, color=MUTED, family=FONT_SANS))
        fig.add_annotation(x=r["high_price"], y=r["driver"], text=str(r["high_label"]),
                           showarrow=False, xanchor="left", xshift=6,
                           font=dict(size=10, color=MUTED, family=FONT_SANS))
    # Base and current labels on two stacked rows above the plot so they never
    # collide with each other or with the x-axis labels below.
    fig.add_vline(x=base, line=dict(color=GOLD, width=2, dash="dash"),
                  annotation_text=f"base {base:,.2f}", annotation_position="top",
                  annotation_yshift=2, annotation_font=dict(size=10, color=GOLD))
    price = case.base.current_price
    if price:
        fig.add_vline(x=price, line=dict(color=GRAPHITE, width=1.4, dash="dot"),
                      annotation_text=f"current {price:,.2f}", annotation_position="top",
                      annotation_yshift=17, annotation_font=dict(size=10, color=GRAPHITE))
    fig = _style(fig, "Driver Sensitivity (Tornado)",
                 "Target price, one driver flexed at a time | widest bar = the debate that matters", height)
    # Padded range keeps the flex labels inside the canvas at both ends.
    lo, hi = float(t["low_price"].min()), float(t["high_price"].max())
    if price:
        lo, hi = min(lo, price), max(hi, price)
    pad = (hi - lo) * 0.16 if hi > lo else max(abs(hi), 1.0) * 0.16
    fig.update_xaxes(title="Target price", range=[lo - pad, hi + pad])
    fig.update_yaxes(showgrid=False, automargin=True)
    fig.update_layout(showlegend=False, bargap=0.4,
                      margin=dict(l=170, r=70, t=110))
    return apply_status_footnote(fig, case)


def scenario_target_chart(case, height: int = 360) -> go.Figure:
    rows = []
    for name, color in (("bear", COPPER), ("base", GOLD), ("bull", GREEN)):
        r = case.scenarios[name]
        if r.target_price is not None:
            rows.append((name.title(), r.target_price, r.upside, color))
    price = case.base.current_price
    if not rows or price is None:
        return _empty_state("Price targets unavailable (missing market data).", "Scenario Price Targets", height)

    fig = go.Figure(go.Bar(
        x=[r[0] for r in rows], y=[r[1] for r in rows],
        marker=dict(color=[r[3] for r in rows], line=dict(width=0)), width=0.55,
        text=[f"{r[1]:,.2f}<br>({r[2]:+.0%})" for r in rows],
        textposition="outside", textfont=dict(size=12, color=INK),
        hovertemplate="%{x}: %{y:,.2f}<extra></extra>", showlegend=False,
    ))
    fig.add_hline(y=price, line=dict(color=GRAPHITE, width=1.6, dash="dash"),
                  annotation_text=f"current {price:,.2f}", annotation_position="top left",
                  annotation_font=dict(size=11, color=GRAPHITE))
    fig = _style(fig, "Scenario Price Targets", "Implied share price and upside by case", height)
    fig.update_yaxes(title="Share price", rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    max_target = max(r[1] for r in rows)
    fig.update_yaxes(range=[0, max(max_target, price) * 1.22])
    return apply_status_footnote(fig, case)


def forecast_chart(case, scenario_name: str = "base", height: int = 380) -> go.Figure:
    res = case.scenarios[scenario_name]
    row = case.assessment.row
    f = res.forecast
    x = ["LTM"] + [f"Y{int(y)}" for y in f["year"]]

    revenue = [_clean(row.get("revenue_ttm"))] + list(f["revenue"])
    ebitda = [_clean(row.get("ebitda_ttm"))] + list(f["ebitda"])
    ufcf = [None] + list(f["ufcf"])

    colors = [MUTED2] + [SAGE] * len(f)
    fig = go.Figure()
    fig.add_bar(x=x, y=revenue, name="Revenue", marker=dict(color=colors, line=dict(width=0)),
                hovertemplate="%{x} revenue %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=ebitda, name="EBITDA", mode="lines+markers",
                    line=dict(color=GOLD, width=2.4), marker=dict(size=6),
                    hovertemplate="%{x} EBITDA %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=ufcf, name="UFCF", mode="lines+markers",
                    line=dict(color=GREEN, width=2.2, dash="dot"), marker=dict(size=6),
                    hovertemplate="%{x} UFCF %{y:,.0f}<extra></extra>")
    fig.add_vline(x=0.5, line=dict(color=LINE, width=1, dash="dot"))
    fig = _style(fig, f"Operating Forecast - {scenario_name.title()} Case",
                 "Gray bar = LTM anchor; forecast traceable to the assumption glidepaths", height)
    fig.update_yaxes(title=f"{row.get('currency', '')}m")
    fig.update_xaxes(showgrid=False)
    return apply_status_footnote(fig, case)


def _waterfall(steps: list[dict], title: str, subtitle: str, currency: str, height: int = 380) -> go.Figure:
    fig = go.Figure(go.Waterfall(
        x=[s["label"] for s in steps],
        y=[s["value"] for s in steps],
        measure=[s["measure"] for s in steps],
        connector=dict(line=dict(color=LINE, width=1)),
        increasing=dict(marker=dict(color=SAGE)),
        decreasing=dict(marker=dict(color=COPPER)),
        totals=dict(marker=dict(color=GRAPHITE)),
        text=[f"{s['value']:,.0f}" for s in steps],
        textposition="outside", textfont=dict(size=11, color=INK), cliponaxis=False,
        hovertemplate="%{x}: %{y:,.0f}<extra></extra>",
    ))
    fig = _style(fig, title, subtitle, height)
    fig.update_yaxes(title=f"{currency}m")
    fig.update_xaxes(showgrid=False, tickangle=-18)
    return fig


def fcf_bridge_chart(case, scenario_name: str = "base", height: int = 380) -> go.Figure:
    res = case.scenarios[scenario_name]
    steps = fcf_bridge_data(res.forecast)
    fig = _waterfall(steps, "Free Cash Flow Bridge (Terminal Year)",
                     "EBITDA - taxes - capex - dNWC = UFCF (D&A nets out of NOPAT+D&A)",
                     str(case.assessment.row.get("currency", "")), height)
    return apply_status_footnote(fig, case)


_BRIDGE_SHORT_LABELS = {
    "PV of explicit FCF": "PV of FCF",
    "PV of terminal value": "PV of TV",
    "Enterprise value": "EV",
    "Net debt": "Net debt",
    "Minority interest": "Minority",
    "Preferred equity": "Preferred",
    "Implied equity": "Equity",
}


def equity_bridge_chart(case, height: int = 400) -> go.Figure:
    base = case.base
    steps = equity_bridge_data(base)
    display = [dict(s, label=_BRIDGE_SHORT_LABELS.get(s["label"], s["label"])) for s in steps]
    fig = _waterfall(display, "Equity Value Bridge (Base Case)",
                     "PV of FCF + PV of TV = EV, less debt-like claims = implied equity",
                     str(case.assessment.row.get("currency", "")), height)
    fig.update_xaxes(tickangle=0)
    fig.update_layout(margin=dict(b=46))
    if base.target_price is not None and base.upside is not None:
        fig.add_annotation(x=len(steps) - 1, y=base.implied_equity,
                           text=f"target {base.target_price:,.2f} ({base.upside:+.0%})",
                           showarrow=False, yshift=34, font=dict(size=12, color=GREEN))
    return apply_status_footnote(fig, case)


def wacc_build_chart(case, height: int = 360) -> go.Figure:
    w = case.wacc
    fig = go.Figure()
    # Cost of equity build (stacked): rf + beta*ERP + country premium.
    segs = [("Risk-free", w.risk_free_rate, MUTED2),
            (f"Beta {w.beta:.2f} x ERP", w.beta * w.equity_risk_premium, SAGE),
            ("Country premium", w.country_risk_premium, GOLD)]
    for name, value, color in segs:
        if value <= 0:
            continue
        fig.add_bar(y=["Cost of equity"], x=[value], name=name, orientation="h",
                    marker=dict(color=color, line=dict(width=0)),
                    hovertemplate=f"{name}: %{{x:.2%}}<extra></extra>")
    fig.add_bar(y=["After-tax cost of debt"], x=[w.cost_of_debt_aftertax], orientation="h",
                marker=dict(color=COPPER, line=dict(width=0)), showlegend=False,
                hovertemplate="After-tax Kd: %{x:.2%}<extra></extra>")
    fig.add_bar(y=["WACC"], x=[w.wacc], orientation="h",
                marker=dict(color=GRAPHITE, line=dict(width=0)), showlegend=False,
                hovertemplate="WACC: %{x:.2%}<extra></extra>")
    fig.add_bar(y=["Terminal WACC"], x=[case.base.terminal_wacc], orientation="h",
                marker=dict(color=GOLD, line=dict(width=0)), showlegend=False,
                hovertemplate="Terminal WACC: %{x:.2%}<extra></extra>")
    for label, value in [("Cost of equity", w.cost_of_equity),
                         ("After-tax cost of debt", w.cost_of_debt_aftertax),
                         ("WACC", w.wacc),
                         ("Terminal WACC", case.base.terminal_wacc)]:
        fig.add_annotation(y=label, x=value, text=f" {value:.2%}", showarrow=False,
                           xanchor="left", font=dict(size=12, color=INK))
    weights = f"weights: {w.equity_weight:.0%} equity / {w.debt_weight:.0%} debt | beta source: {w.beta_source}"
    if w.overridden:
        weights += " | ANALYST OVERRIDE"
    fig = _style(fig, "WACC Build", weights, height)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(showgrid=False, categoryorder="array",
                     categoryarray=["Terminal WACC", "WACC", "After-tax cost of debt", "Cost of equity"])
    fig.update_xaxes(tickformat=".1%", range=[0, max(w.cost_of_equity, w.wacc,
                                                     case.base.terminal_wacc) * 1.35])
    return apply_status_footnote(fig, case)


def terminal_value_chart(case, height: int = 360) -> go.Figure:
    base = case.base
    perp_ok = not np.isnan(base.terminal_value_perp)
    exit_label = "Analyst exit multiple" if "analyst" in case.exit_multiple_source else "Fundamental multiple"
    x = [exit_label, "Perpetuity"]
    tv = [base.pv_terminal_exit, base.pv_terminal_perp if perp_ok else 0]
    colors = [SAGE, MUTED2]
    if case.market_reference_multiple is not None and base.exit_multiple > 0:
        market_pv = base.pv_terminal_exit * case.market_reference_multiple / base.exit_multiple
        x.append("Market reference")
        tv.append(market_pv)
        colors.append(GOLD)
    fig = go.Figure(go.Bar(
        x=x, y=tv, width=0.5,
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:,.0f}" if v else "n/m" for v in tv], textposition="outside",
        textfont=dict(size=12, color=INK), showlegend=False,
        hovertemplate="%{x}: PV %{y:,.0f}<extra></extra>",
    ))
    notes = []
    if base.implied_terminal_growth is not None:
        notes.append(f"exit {case.exit_multiple:.1f}x implies g = {base.implied_terminal_growth:+.1%}")
    if base.implied_exit_multiple is not None:
        notes.append(f"perpetuity {case.assumptions.perpetuity_growth:.1%} implies {base.implied_exit_multiple:.1f}x")
    if base.terminal_reinvestment_rate is not None:
        notes.append(f"stable reinvestment {base.terminal_reinvestment_rate:.0%}")
    if case.market_reference_multiple is not None:
        notes.append(f"market reference {case.market_reference_multiple:.1f}x")
    subtitle = "PV of terminal value | " + "; ".join(notes) if notes else "PV of terminal value"
    fig = _style(fig, "Terminal Value - Two Methods", subtitle, height)
    fig.update_yaxes(title=f"{case.assessment.row.get('currency', '')}m")
    fig.update_xaxes(showgrid=False)
    return apply_status_footnote(fig, case)


def terminal_value_divergence(case) -> str | None:
    """Divergence note rendered OUTSIDE the plot (page footnote / export box)."""
    base = case.base
    if np.isnan(base.terminal_value_perp) or base.pv_terminal_exit <= 0:
        return None
    signed_gap = base.pv_terminal_perp / base.pv_terminal_exit - 1.0
    gap = abs(signed_gap)
    if gap > 0.25:
        direction = "above" if signed_gap > 0 else "below"
        return (f"Perpetuity terminal value is {gap:.0%} {direction} the exit-multiple result. "
                f"The market multiple and stable-growth economics are telling different stories; "
                f"reconcile terminal growth, ROIC, WACC, and the exit multiple before relying on the target.")
    return None


def peer_quartile_panels(case, height: int = 360) -> go.Figure:
    stats = case.spread_stats
    row = case.assessment.row
    panels = [
        ("Rev growth\nLatest Q YoY", "revenue_yoy_growth", row.get("revenue_yoy_growth"), ".0%"),
        ("EBITDA margin\nLTM", "ebitda_margin_ttm", row.get("ebitda_margin_ttm"), ".0%"),
        ("EV/Revenue\nLTM", "ev_to_revenue_ttm", row.get("ev_to_revenue_ttm"), ".1f"),
        ("EV/EBITDA\nLTM", "ev_to_ebitda_ttm", row.get("ev_to_ebitda_ttm"), ".1f"),
        ("P/E\nLTM", "pe_ttm", row.get("pe_ttm"), ".1f"),
    ]
    usable = [p for p in panels
              if p[1] in stats.index and pd.notna(stats.loc[p[1], "median"]) and stats.loc[p[1], "n"] >= 3]
    if not usable:
        return _empty_state("Peer statistics unavailable.", "Peer Benchmarking", height)

    fig = make_subplots(rows=1, cols=len(usable),
                        subplot_titles=[p[0] for p in usable], horizontal_spacing=0.09)
    for i, (label, metric, own, fmt) in enumerate(usable, start=1):
        q1, med, q3 = (stats.loc[metric, k] for k in ("q1", "median", "q3"))
        fig.add_bar(x=[label], y=[q3 - q1], base=[q1], width=0.35,
                    marker=dict(color=PALETTE["sage_soft"], line=dict(color=SAGE, width=1.2)),
                    showlegend=False, hoverinfo="skip", row=1, col=i)
        fig.add_scatter(x=[label], y=[med], mode="markers",
                        marker=dict(symbol="line-ew", size=26, line=dict(color=GRAPHITE, width=2.5)),
                        showlegend=(i == 1), name="Peer median (ex-company)", row=1, col=i)
        if pd.notna(own):
            fig.add_scatter(x=[label], y=[float(own)], mode="markers",
                            marker=dict(symbol="diamond", size=12, color=GOLD,
                                        line=dict(color=GRAPHITE, width=1)),
                            showlegend=(i == 1), name=str(row.get("ticker", "")).replace(".SA", ""),
                            row=1, col=i)
        fig.update_yaxes(tickformat=fmt.replace("f", "f") if "f" in fmt else fmt, row=1, col=i, **_AXIS)
        fig.update_xaxes(visible=False, row=1, col=i)
    fig = _style(fig, "Peer Benchmarking - Quartile Positioning",
                 "Peer-only band and median | selected company shown as diamond | metric basis in each panel", height)
    fig.update_annotations(font=dict(size=11.5, color=MUTED))
    return apply_status_footnote(fig, case)


def revision_momentum_chart(case, height: int = 300) -> go.Figure | None:
    rev = case.assessment.revisions
    if not rev.get("available"):
        return None
    points = {
        "revenue": [rev.get("revenue_90d"), rev.get("revenue_30d")],
        "eps": [rev.get("eps_90d"), rev.get("eps_30d")],
    }
    # Convert drift-vs-today into an indexed path: 90d ago = today/(1+drift90).
    x = ["90d ago", "30d ago", "Today"]
    fig = go.Figure()
    plotted = False
    for name, (d90, d30), color in [("NTM revenue est.", points["revenue"], SAGE),
                                    ("NTM EPS est.", points["eps"], GOLD)]:
        if d90 is None and d30 is None:
            continue
        base90 = 100.0 / (1 + d90) if d90 is not None else None
        base30 = 100.0 / (1 + d30) if d30 is not None else None
        series = [base90, base30, 100.0]
        fig.add_scatter(x=x, y=series, name=name, mode="lines+markers",
                        line=dict(color=color, width=2.4), marker=dict(size=7),
                        hovertemplate="%{x}: %{y:.1f}<extra></extra>")
        plotted = True
    if not plotted:
        return None
    fig = _style(fig, "Estimate Revision Momentum",
                 f"Indexed to today = 100 | direction: {rev.get('direction', 'n/a')}", height)
    fig.update_yaxes(title="Index")
    fig.update_xaxes(showgrid=False)
    return fig


def working_capital_chart(df: pd.DataFrame, case, height: int = 320) -> go.Figure | None:
    company_id = case.company_id
    history = df[df["company_id"] == company_id].sort_values("period").tail(12)
    if "dso" not in history.columns or history["dso"].notna().sum() < 2:
        return None
    x = [f"Q{pd.Timestamp(p).quarter} {pd.Timestamp(p).year % 100:02d}" for p in history["period"]]
    fig = go.Figure()
    for col, name, color in [("dso", "DSO", SAGE), ("dio", "DIO", GOLD), ("dpo", "DPO", COPPER)]:
        if col in history.columns and history[col].notna().any():
            fig.add_scatter(x=x, y=history[col], name=name, mode="lines",
                            line=dict(color=color, width=2),
                            hovertemplate=f"{name} %{{y:.0f}}d<extra></extra>")
    if "cash_conversion_cycle" in history.columns and history["cash_conversion_cycle"].notna().any():
        fig.add_scatter(x=x, y=history["cash_conversion_cycle"], name="CCC", mode="lines+markers",
                        line=dict(color=GRAPHITE, width=2.6), marker=dict(size=5),
                        hovertemplate="CCC %{y:.0f}d<extra></extra>")
    scen = case.assumptions.scenarios["base"]
    subtitle = "Historical days"
    if scen.nwc_mode == "days" and scen.dso:
        subtitle += f" | forecast glidepath: DSO ->{scen.dso[-1]:.0f}d, DIH ->{scen.dih[-1]:.0f}d, DPO ->{scen.dpo[-1]:.0f}d"
    fig = _style(fig, "Working Capital Days", subtitle, height)
    fig.update_yaxes(title="days")
    fig.update_xaxes(showgrid=False)
    return fig


# =====================================================================================
# Static export helpers (kaleido)
# =====================================================================================

def figure_to_png_uri(fig: go.Figure, width: int = 860, height: int | None = None, scale: float = 2.0) -> str | None:
    """Render a figure to a base64 PNG data URI; None if static export unavailable."""
    import base64
    try:
        # Solid background for the standalone HTML document.
        fig = go.Figure(fig)
        fig.update_layout(paper_bgcolor=CREAM, plot_bgcolor=CREAM)
        png = fig.to_image(format="png", width=width, height=height or fig.layout.height or 380, scale=scale)
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except Exception:
        return None


def case_chart_images(case, df: pd.DataFrame | None = None) -> dict[str, str]:
    """Render all HTML-export charts in one Kaleido session.

    Plotly's per-figure ``to_image`` path starts a browser renderer for every
    chart. Besides being slow, that can flash several temporary windows on
    Windows. The batch API reuses one renderer for the complete case.
    """
    import base64
    from pathlib import Path
    from tempfile import TemporaryDirectory

    import plotly.io as pio

    builders = {
        "scenario_targets": lambda: scenario_target_chart(case),
        "football_field": lambda: football_field_chart(case),
        "forecast": lambda: forecast_chart(case),
        "fcf_bridge": lambda: fcf_bridge_chart(case),
        "sensitivity": lambda: sensitivity_heatmap(case),
        "tornado": lambda: tornado_chart(case),
        "implied_growth": lambda: implied_growth_heatmap(case),
        "equity_bridge": lambda: equity_bridge_chart(case),
        "wacc_build": lambda: wacc_build_chart(case),
        "terminal_value": lambda: terminal_value_chart(case),
        "peer_quartiles": lambda: peer_quartile_panels(case),
        "revisions": lambda: revision_momentum_chart(case),
        "working_capital": (lambda: working_capital_chart(df, case)) if df is not None else (lambda: None),
    }
    keys: list[str] = []
    figures: list[go.Figure] = []
    for key, build in builders.items():
        try:
            fig = build()
        except Exception:
            fig = None
        if fig is None:
            continue
        export_fig = go.Figure(fig)
        export_fig.update_layout(paper_bgcolor=CREAM, plot_bgcolor=CREAM)
        keys.append(key)
        figures.append(export_fig)

    if not figures:
        return {}

    try:
        with TemporaryDirectory(prefix="valuation-case-charts-") as temp_dir:
            files = [Path(temp_dir) / f"{key}.png" for key in keys]
            heights = [int(fig.layout.height or 380) for fig in figures]
            pio.write_images(figures, files, format="png", width=860,
                             height=heights, scale=2.0)
            return {
                key: "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
                for key, path in zip(keys, files)
                if path.exists() and path.stat().st_size > 0
            }
    except Exception:
        # The HTML template is designed to degrade gracefully when a static
        # renderer is unavailable; the financial tables still export in full.
        return {}
