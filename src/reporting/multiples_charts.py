"""Charts for the multi-multiple valuation framework.

Same restrained language as the rest of the product. Color conventions,
used consistently across every figure here:
- selected company  -> sage/green
- peer median       -> graphite, dashed
- historical range  -> soft sage band / gold reference marks
- positive signal   -> green | negative -> copper/red | not meaningful -> muted
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.branding import FONT_SANS, PALETTE
from src.modeling.multiples import MULTIPLE_SPECS
from src.modeling.outliers import adjusted_stats, multiple_outlier_reason
from src.reporting.charts import _scatter_label_text, _style, stamp_period

SAGE = PALETTE["anchor"]
GREEN = PALETTE["green"]
GOLD = PALETTE["gold"]
COPPER = PALETTE["copper"]
GRAPHITE = PALETTE["charcoal"]
MUTED = PALETTE["muted"]
MUTED2 = PALETTE["muted_2"]
BLUE = PALETTE["peer"]


def _empty(title: str, note: str, height: int = 280) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=note, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=12, color=MUTED2))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, title, height=height)


# --- 1. historical multiple chart ---------------------------------------------

def multiple_history_chart(hist: dict, label: str, height: int = 420) -> go.Figure:
    """Company vs peer median through time, with the peer IQR band and the
    company's own historical median/quartile references. No peer spaghetti."""
    if not hist.get("available"):
        return _empty(f"{label} - History", "Valuation history not populated for this name.")
    own, peers = hist["company"], hist["peers"]
    fig = go.Figure()
    if not peers.empty:
        fig.add_scatter(x=peers["date"], y=peers["q3"], mode="lines",
                        line=dict(width=0), hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=peers["date"], y=peers["q1"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor="rgba(122,138,115,0.16)",
                        name="Peer 25th-75th pct", hoverinfo="skip")
        fig.add_scatter(x=peers["date"], y=peers["median"], mode="lines",
                        line=dict(color=GRAPHITE, width=1.8, dash="dash"), name="Peer median (ex-company)",
                        hovertemplate="%{x|%b %y} peers %{y:.1f}x<extra></extra>")
    # Own-history references: median solid gold dots, quartiles faint.
    for key, dash, w in (("own_q1", "dot", 1), ("own_q3", "dot", 1), ("own_median", "dot", 1.6)):
        fig.add_hline(y=hist[key], line=dict(color=GOLD, width=w, dash=dash), opacity=0.85)
    fig.add_annotation(x=own["date"].min(), y=hist["own_median"], text="own median",
                       showarrow=False, xanchor="left", yshift=9,
                       font=dict(size=9.5, color=GOLD))
    fig.add_scatter(x=own["date"], y=own["value"], mode="lines", name="Company",
                    line=dict(color=SAGE, width=2.8),
                    hovertemplate="%{x|%b %y}: %{y:.1f}x<extra></extra>")
    fig.add_scatter(x=[own["date"].iloc[-1]], y=[own["value"].iloc[-1]], mode="markers",
                    marker=dict(symbol="diamond", size=11, color=GOLD,
                                line=dict(color=GRAPHITE, width=1.2)),
                    name="Current", hovertemplate="current %{y:.1f}x<extra></extra>")
    pct = float((own["value"] < own["value"].iloc[-1]).mean())
    fig = _style(fig, f"{label} - History",
                 f"Company vs peer median (ex-company) | gold dots = own median & quartiles | "
                 f"current = {pct:.0%} pctile of own history", height)
    fig.update_yaxes(ticksuffix="x", rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    if len(own) >= 2:
        lo, hi = pd.Timestamp(own["date"].min()), pd.Timestamp(own["date"].max())
        fig = stamp_period(fig, f"{lo.strftime('%b %y')} - {hi.strftime('%b %y')}")
    return fig


# --- 2. momentum heatmap --------------------------------------------------------

def momentum_heatmap(momentum: dict[str, dict], height: int | None = None) -> go.Figure:
    """Relative multiple change (company minus peer median) over 3/6/12 months.

    Green = re-rating vs peers (company-specific expansion), copper =
    de-rating vs peers; near-zero = the move is sector-driven.
    """
    rows = [(MULTIPLE_SPECS[m]["label"], mom) for m, mom in momentum.items()
            if mom.get("available")]
    if not rows:
        return _empty("Multiple Momentum", "Not enough valuation history for momentum.")
    labels = [r[0] for r in rows]
    periods = [3, 6, 12]
    z, text = [], []
    for _, mom in rows:
        zrow, trow = [], []
        for p in periods:
            rel = mom["relative"].get(p)
            c, pc = mom["chg"].get(p), mom["peer_chg"].get(p)
            zrow.append(np.nan if rel is None else rel)
            trow.append("n/a" if c is None else
                        f"co {c:+.0%}" + (f"<br>peers {pc:+.0%}" if pc is not None else ""))
        z.append(zrow)
        text.append(trow)
    height = height or (150 + 62 * len(rows))
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{p}M" for p in periods], y=labels,
        colorscale=[[0.0, COPPER], [0.5, PALETTE["cream"]], [1.0, GREEN]],
        zmid=0.0, xgap=5, ygap=8, showscale=False,
        text=text, texttemplate="%{text}", textfont=dict(size=10.5, family=FONT_SANS),
        hovertemplate="%{y} | %{x}<br>vs peers %{z:+.1%}<extra></extra>",
    ))
    fig = _style(fig, "Multiple Momentum vs Peers",
                 "Color = company minus peers | green re-rates, copper de-rates", height)
    fig.update_xaxes(showgrid=False, side="top", type="category")
    fig.update_yaxes(showgrid=False, autorange="reversed", type="category", automargin=True)
    fig.update_layout(margin=dict(t=118))
    return fig


# --- 3. peer distribution panels -------------------------------------------------

def peer_distribution_panels(spread: pd.DataFrame, metrics: list[str], company_id: str,
                             row_height: int = 96) -> go.Figure:
    """IB-style spread visual: one horizontal strip per multiple - interquartile box,
    median tick, every valid peer as a dot, anchor as a gold diamond, flagged
    outliers in copper. Invalid (negative-base) names are counted, not drawn."""
    usable = []
    for m in metrics:
        if m in spread.columns and pd.to_numeric(spread[m], errors="coerce").gt(0).sum() >= 3:
            usable.append(m)
    if not usable:
        return _empty("Peer Multiple Distribution", "Not enough valid peer multiples.")

    fig = make_subplots(rows=len(usable), cols=1, shared_xaxes=False,
                        vertical_spacing=min(0.34, 0.16 + 0.02 * len(usable)))
    for i, metric in enumerate(usable, start=1):
        label = MULTIPLE_SPECS.get(metric, {}).get("label", metric)
        vals = pd.to_numeric(spread[metric], errors="coerce")
        peer_reference = spread.loc[spread["company_id"].astype(str) != str(company_id)] \
            if "company_id" in spread.columns else spread
        stats = adjusted_stats(peer_reference if not peer_reference.empty else spread, metric)
        n_invalid = int((vals <= 0).sum() + vals.isna().sum())
        # 25th-75th percentile box + median tick (adjusted stats, outliers excluded).
        if not np.isnan(stats["q1"]) and not np.isnan(stats["q3"]):
            fig.add_shape(type="rect", x0=stats["q1"], x1=stats["q3"], y0=-0.32, y1=0.32,
                          line=dict(color=SAGE, width=1.2),
                          fillcolor="rgba(122,138,115,0.16)", row=i, col=1)
        if not np.isnan(stats["adjusted_median"]):
            fig.add_shape(type="line", x0=stats["adjusted_median"], x1=stats["adjusted_median"],
                          y0=-0.42, y1=0.42, line=dict(color=GRAPHITE, width=2.4), row=i, col=1)
        # Peer dots: valid clean, flagged outliers copper x. An unclamped 170x
        # print would crush the readable cluster, so outliers are drawn at the
        # axis cap with the true value on hover.
        clean_x, clean_t, out_x, out_t = [], [], [], []
        own = spread.loc[spread["company_id"] == company_id, metric] if "company_id" in spread.columns else pd.Series(dtype=float)
        own_v = float(own.iloc[0]) if len(own) and pd.notna(own.iloc[0]) and own.iloc[0] > 0 else None
        for _, r in spread.iterrows():
            v = r.get(metric)
            if v is None or pd.isna(v) or v <= 0 or r.get("company_id") == company_id:
                continue
            t = str(r.get("ticker", "")).replace(".SA", "")
            if multiple_outlier_reason(metric, float(v)):
                out_x.append(float(v))
                out_t.append(t)
            else:
                clean_x.append(float(v))
                clean_t.append(t)
        in_range = clean_x + ([own_v] if own_v is not None else []) \
            + [v for v in (stats["q3"], stats["high"]) if not np.isnan(v)]
        cap = (max(in_range) if in_range else 1.0) * 1.15
        fig.add_scatter(x=clean_x, y=[0] * len(clean_x), mode="markers",
                        marker=dict(size=9, color=BLUE, opacity=0.75,
                                    line=dict(color="#ffffff", width=0.6)),
                        text=clean_t, hovertemplate="%{text}: %{x:.1f}x<extra></extra>",
                        showlegend=(i == 1), name="Peers", row=i, col=1)
        if out_x:
            fig.add_scatter(x=[min(v, cap) for v in out_x], y=[0] * len(out_x), mode="markers",
                            marker=dict(symbol="x", size=9, color=COPPER),
                            text=out_t, customdata=out_x,
                            hovertemplate="%{text}: %{customdata:.0f}x (outlier, drawn at cap)<extra></extra>",
                            showlegend=(i == 1), name="Flagged outlier", row=i, col=1)
        if own_v is not None:
            fig.add_scatter(x=[own_v], y=[0], mode="markers",
                            marker=dict(symbol="diamond", size=13, color=GOLD,
                                        line=dict(color=GRAPHITE, width=1.2)),
                            hovertemplate=f"Company: {own_v:.1f}x<extra></extra>",
                            showlegend=(i == 1), name="Company", row=i, col=1)
        note = label + (f"  (n/m for {n_invalid})" if n_invalid else "")
        fig.add_annotation(x=0, y=0.88, xref=f"x{i} domain" if i > 1 else "x domain",
                           yref=f"y{i} domain" if i > 1 else "y domain",
                           text=note, showarrow=False, xanchor="left",
                           font=dict(size=11.5, color=MUTED))
        fig.update_yaxes(visible=False, range=[-0.7, 1.0], row=i, col=1)
        fig.update_xaxes(ticksuffix="x", range=[0, cap * 1.04], row=i, col=1)
    height = 140 + row_height * len(usable)
    fig = _style(fig, "Peer Multiple Distribution",
                 "Box/tick use peers only: adjusted 25th-75th percentile and median | diamond = company | x = flagged outlier",
                 height)
    return fig


# --- 4. growth vs valuation scatters ---------------------------------------------

def fundamental_vs_multiple_scatter(spread: pd.DataFrame, company_id: str,
                                    xcol: str, ycol: str, xlabel: str, ylabel: str,
                                    title: str, subtitle: str,
                                    xfmt: str = ".0%", height: int = 380) -> go.Figure:
    """Is the multiple earned? One dot per peer; anchor highlighted."""
    cols = [c for c in (xcol, ycol, "ticker", "company_id") if c in spread.columns]
    if xcol not in cols or ycol not in cols:
        return _empty(title, "Metric not available in this comp set.")
    data = spread[cols].copy()
    data[ycol] = pd.to_numeric(data[ycol], errors="coerce")
    data = data[data[ycol] > 0].dropna(subset=[xcol])
    # Keep the multiple axis honest: flagged outliers out unless it's the anchor.
    extreme = data[ycol].map(lambda v: multiple_outlier_reason(ycol, v) is not None)
    excluded = data[extreme & ~data["company_id"].eq(company_id)]
    data = data[~extreme | data["company_id"].eq(company_id)]
    if len(data) < 3:
        return _empty(title, "Fewer than 3 valid peer observations.")
    labels = _scatter_label_text(data, xcol, ycol, company_id)
    fig = go.Figure()
    for is_anchor, sub in data.groupby(data["company_id"].eq(company_id)):
        fig.add_scatter(
            x=sub[xcol], y=sub[ycol], mode="markers+text",
            text=labels.loc[sub.index], textposition="top center",
            textfont=dict(size=10, color=PALETTE["slate"]),
            customdata=[t.replace(".SA", "") for t in sub["ticker"]],
            marker=dict(size=(17 if is_anchor else 12),
                        color=(GREEN if is_anchor else BLUE),
                        line=dict(width=(1.6 if is_anchor else 0.6), color="#ffffff"),
                        opacity=0.95),
            name=("Company" if is_anchor else "Peers"),
            hovertemplate="%{customdata}<br>" + xlabel + " %{x:" + xfmt + "}<br>"
                          + ylabel + " %{y:.1f}x<extra></extra>",
        )
    peer_reference = data.loc[data["company_id"].astype(str) != str(company_id)]
    med_x = peer_reference[xcol].median(skipna=True)
    med_y = peer_reference[ycol].median(skipna=True)
    if pd.notna(med_x):
        fig.add_vline(x=med_x, line=dict(color=MUTED2, width=1, dash="dash"))
    if pd.notna(med_y):
        fig.add_hline(y=med_y, line=dict(color=MUTED2, width=1, dash="dash"))
    if len(excluded):
        subtitle += " | off-scale excluded: " + ", ".join(
            t.replace(".SA", "") for t in excluded["ticker"].head(3))
    fig = _style(fig, title, subtitle, height)
    fig.update_xaxes(title=xlabel, tickformat=xfmt)
    fig.update_yaxes(title=ylabel, ticksuffix="x")
    return fig


# --- 5. re-rating bridge -----------------------------------------------------------

def rerating_decomposition(valuation_history: pd.DataFrame, company_id: str,
                           column: str, months: int = 12) -> dict:
    """Approximate 12m share-price decomposition: driver growth x multiple change.

    price = driver_per_share x multiple (exact for P/E; for EV multiples the
    residual absorbs net debt / share count / cross effects). Returns factors,
    or {'available': False} when history is missing.
    """
    out = {"available": False}
    if valuation_history is None or valuation_history.empty:
        return out
    needed = {"company_id", "date", "share_price", column}
    if not needed.issubset(valuation_history.columns):
        return out
    own = valuation_history[valuation_history["company_id"] == company_id].sort_values("date")
    own = own.dropna(subset=["share_price", column])
    own = own[(own["share_price"] > 0) & (own[column] > 0)]
    if len(own) < 4:
        return out
    last = own.iloc[-1]
    target = last["date"] - pd.DateOffset(months=months)
    gaps = (own["date"] - target).abs()
    base = own.loc[gaps.idxmin()]
    if gaps.min() > pd.Timedelta(days=60):
        return out
    p0, p1 = float(base["share_price"]), float(last["share_price"])
    m0, m1 = float(base[column]), float(last[column])
    driver = (p1 / m1) / (p0 / m0) - 1.0          # implied fundamental per share
    mult = m1 / m0 - 1.0
    total = p1 / p0 - 1.0
    residual = (1 + total) / ((1 + driver) * (1 + mult)) - 1.0
    return {"available": True, "months": months, "column": column,
            "price_start": p0, "price_end": p1,
            "driver": driver, "multiple": mult, "residual": residual, "total": total}


def rerating_bridge_chart(decomp: dict, metric_label: str, height: int = 360) -> go.Figure:
    if not decomp.get("available"):
        return _empty("Multiple Re-Rating Bridge", "Not enough price/multiple history.")
    p0 = decomp["price_start"]
    steps = [("Price 12m ago", p0, "absolute"),
             ("Fundamental / share", p0 * decomp["driver"], "relative"),
             (f"{metric_label} change", p0 * (1 + decomp["driver"]) * decomp["multiple"], "relative")]
    if abs(decomp["residual"]) > 0.005:
        base_after = p0 * (1 + decomp["driver"]) * (1 + decomp["multiple"])
        steps.append(("Residual (debt/shares/cross)", base_after * decomp["residual"], "relative"))
    steps.append(("Price today", decomp["price_end"], "total"))
    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps], y=[s[1] for s in steps],
        measure=[s[2] for s in steps],
        connector=dict(line=dict(color=PALETTE["line"], width=1)),
        increasing=dict(marker=dict(color=SAGE)),
        decreasing=dict(marker=dict(color=COPPER)),
        totals=dict(marker=dict(color=GRAPHITE)),
        text=[f"{s[1]:,.1f}" for s in steps], textposition="outside",
        textfont=dict(size=10.5, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
    ))
    fig = _style(fig, "Multiple Re-Rating Bridge",
                 f"APPROXIMATE 12m split ({metric_label}): fundamentals {decomp['driver']:+.0%} "
                 f"x multiple {decomp['multiple']:+.0%} = price {decomp['total']:+.0%}", height)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(showgrid=False, tickangle=-14)
    fig.update_yaxes(title="Share price")
    return fig
