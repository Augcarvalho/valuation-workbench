"""Board-pack-quality Plotly charts.

Every figure runs through :func:`_style` so titles, subtitles, fonts, gridlines,
margins, and colors are identical across the dashboard. Colors come from the
shared :mod:`src.branding` palette.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.branding import FONT_SANS, FONT_SERIF, PALETTE, signal_hex
from src.modeling.outliers import EV_EBITDA_MAX, adjusted_stats, multiple_outlier_reason

COLOR_REVENUE = PALETTE["series_revenue"]
COLOR_EBITDA = PALETTE["series_ebitda"]
COLOR_CASH = PALETTE["series_cash"]
COLOR_MARGIN = PALETTE["series_margin"]
COLOR_SECONDARY = PALETTE["series_secondary"]
COLOR_DEBT = PALETTE["series_debt"]
COLOR_ANCHOR = PALETTE["anchor"]
COLOR_PEER = PALETTE["peer"]
# Generic paired bars outside the operating-history charts.
COLOR_BLUE = COLOR_REVENUE
COLOR_BLUE_2 = COLOR_EBITDA
COLOR_GREEN = PALETTE["green"]
COLOR_AMBER = PALETTE["amber"]
COLOR_RED = PALETTE["red"]
COLOR_INK = PALETTE["ink"]
COLOR_GRAY = PALETTE["muted"]
COLOR_LINE = PALETTE["line"]
COLOR_GOLD = PALETTE["gold"]

_AXIS = dict(
    showgrid=True,
    gridcolor=PALETTE["line_soft"],
    gridwidth=1,
    zeroline=True,
    zerolinecolor=PALETTE["line"],
    linecolor=PALETTE["line"],
    ticks="outside",
    tickcolor=PALETTE["line"],
    ticklen=4,
    tickfont=dict(size=11, color=PALETTE["slate"]),
    title_font=dict(size=11.5, color=PALETTE["muted"]),
)


def signal_color(signal: str) -> str:
    return signal_hex(signal)


def company_history(df: pd.DataFrame, company_id: str) -> pd.DataFrame:
    return df[df["company_id"] == company_id].sort_values("period")


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["company_id", "period"]).groupby("company_id", as_index=False).tail(1)


def _currency_label(history: pd.DataFrame) -> str:
    if "currency" in history.columns and history["currency"].notna().any():
        return f"{history['currency'].dropna().iloc[-1]}m"
    return "Local currency (m)"


def _style(fig: go.Figure, title: str, subtitle: str = "", height: int = 380) -> go.Figure:
    # Editorial pairing: serif display title (matches the app chrome), sans
    # kicker-style subtitle and data labels. Native title.subtitle carries its
    # own font — plotly's pseudo-HTML <span> cannot hold a quoted font stack.
    # Top margin reserves distinct bands: title (~30px), subtitle (~18px), then
    # the legend strip sits above the plot area without touching either.
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0, xanchor="left", y=0.98, yanchor="top",
                   font=dict(size=17, color=PALETTE["navy"], family=FONT_SANS),
                   subtitle=dict(text=subtitle or None,
                                 font=dict(size=11.5, color=PALETTE["muted"], family=FONT_SANS))),
        font=dict(family=FONT_SANS, color=PALETTE["slate"], size=12),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        colorway=[PALETTE["teal"], PALETTE["navy"], PALETTE["line"], PALETTE["navy_3"]],
        height=height,
        margin=dict(l=24, r=20, t=94 if subtitle else 66, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    font=dict(size=11, color=PALETTE["slate"]), bgcolor="rgba(0,0,0,0)",
                    itemwidth=30, tracegroupgap=4),
        hoverlabel=dict(font_size=12, font_family=FONT_SANS,
                        bordercolor=PALETTE["line"], bgcolor=PALETTE["panel"],
                        font_color=PALETTE["ink"]),
    )
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def _q_labels(history: pd.DataFrame) -> list[str]:
    return [f"Q{pd.Timestamp(p).quarter} {pd.Timestamp(p).year % 100:02d}" for p in history["period"]]


def stamp_period(fig: go.Figure, text: str) -> go.Figure:
    """Tiny bottom-right caption naming the data window (e.g. "Jan 25 - Jun 26").

    Anchored a fixed pixel distance below the plot area (yshift, not a paper
    fraction) so it never lands on the x-axis tick labels; the bottom margin
    is widened to guarantee the room. Sits at x=1 (right-aligned) so it never
    collides with any bottom-LEFT footnote (x=0) such as the auto-anchored
    assumptions disclosure or the outlier disclosure in valuation_chart.
    """
    fig.add_annotation(
        x=1.0, y=0, xref="paper", yref="paper", xanchor="right", yanchor="top",
        yshift=-34, text=text, showarrow=False,
        font=dict(size=9, color=PALETTE["muted_2"]),
    )
    fig.update_layout(margin=dict(b=max(fig.layout.margin.b or 34, 56)))
    return fig


# Quarterly company charts show at most this many periods so the x-axis
# stays readable at half-page width.
MAX_QUARTERS = 12


def _quarter_range_label(x: list[str]) -> str | None:
    """"Q3 23 - Q2 26" style range from a list of _q_labels-formatted strings."""
    return f"{x[0]} - {x[-1]}" if len(x) >= 2 else None


# --- charts -----------------------------------------------------------------

def revenue_ebitda_chart(df: pd.DataFrame, company_id: str, height: int = 390) -> go.Figure:
    history = company_history(df, company_id).tail(MAX_QUARTERS)
    x = _q_labels(history)
    fig = go.Figure()
    fig.add_bar(x=x, y=history["revenue"], name="Revenue (quarter)", marker_color=COLOR_REVENUE,
                marker_line_width=0, opacity=0.95,
                hovertemplate="Revenue: %{y:,.0f}<extra></extra>")
    fig.add_bar(x=x, y=history["ebitda"], name="EBITDA (quarter)", marker_color=COLOR_EBITDA,
                marker_line_width=0, opacity=0.9,
                hovertemplate="EBITDA: %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=history["ebitda_margin"], name="EBITDA margin", mode="lines+markers",
                    line=dict(color=COLOR_MARGIN, width=2.6), marker=dict(size=6),
                    yaxis="y2", hovertemplate="Margin: %{y:.1%}<extra></extra>")
    fig = _style(fig, "Reported Quarterly Revenue &amp; EBITDA",
                 f"Standalone quarters in {_currency_label(history)} | line = quarterly EBITDA margin (RHS)", height)
    fig.update_layout(
        barmode="group", bargap=0.32, bargroupgap=0.08,
        yaxis=dict(title=_currency_label(history), **_AXIS),
        yaxis2=dict(title="EBITDA margin", overlaying="y", side="right", tickformat=".0%",
                    showgrid=False, zeroline=False, linecolor=PALETTE["line"],
                    tickfont=dict(size=11, color=COLOR_MARGIN),
                    title_font=dict(size=11, color=COLOR_MARGIN)),
    )
    # Annotate the latest margin reading.
    if len(history) and pd.notna(history["ebitda_margin"].iloc[-1]):
        fig.add_annotation(x=x[-1], y=history["ebitda_margin"].iloc[-1], yref="y2",
                           text=f"{history['ebitda_margin'].iloc[-1]:.1%}", showarrow=False,
                           yshift=14, font=dict(size=11, color=COLOR_MARGIN))
    period_label = _quarter_range_label(x)
    if period_label:
        fig = stamp_period(fig, period_label)
    return fig


def margin_trend_chart(df: pd.DataFrame, company_id: str, height: int = 320) -> go.Figure:
    history = company_history(df, company_id).tail(MAX_QUARTERS)
    x = _q_labels(history)
    fig = go.Figure()
    fig.add_scatter(x=x, y=history["gross_margin"], name="Gross margin", mode="lines+markers",
                    line=dict(color=COLOR_SECONDARY, width=2.4), marker=dict(size=6),
                    hovertemplate="Gross: %{y:.1%}<extra></extra>")
    fig.add_scatter(x=x, y=history["ebitda_margin"], name="EBITDA margin", mode="lines+markers",
                    line=dict(color=COLOR_ANCHOR, width=2.8), marker=dict(size=6),
                    hovertemplate="EBITDA: %{y:.1%}<extra></extra>")
    fig = _style(fig, "Reported Quarterly Margin Profile",
                 "Standalone-quarter gross margin and EBITDA margin", height)
    fig.update_yaxes(tickformat=".0%")
    period_label = _quarter_range_label(x)
    if period_label:
        fig = stamp_period(fig, period_label)
    return fig


def cash_conversion_chart(df: pd.DataFrame, company_id: str, height: int = 360) -> go.Figure:
    history = company_history(df, company_id).tail(MAX_QUARTERS)
    x = _q_labels(history)
    fig = go.Figure()
    fig.add_bar(x=x, y=history["cfo_ttm"], name="CFO (LTM)", marker_color=COLOR_REVENUE, opacity=0.95)
    fig.add_bar(x=x, y=history["fcf_ttm"], name="FCF (LTM)", marker_color=COLOR_CASH, opacity=0.95)
    fig.add_scatter(x=x, y=history["fcf_conversion_ttm"], name="FCF conversion", mode="lines+markers",
                    line=dict(color=COLOR_MARGIN, width=2.6), marker=dict(size=6), yaxis="y2",
                    hovertemplate="Conversion: %{y:.0%}<extra></extra>")
    fig = _style(fig, "LTM Cash Conversion",
                 f"Rolling four-quarter cash flows in {_currency_label(history)} | line = LTM FCF / EBITDA (RHS)", height)
    fig.update_layout(
        barmode="group", bargap=0.3,
        yaxis=dict(title=_currency_label(history), **_AXIS),
        yaxis2=dict(title="FCF / EBITDA", overlaying="y", side="right", tickformat=".0%",
                    showgrid=False, zeroline=False, range=[0, 1.2],
                    tickfont=dict(size=11, color=COLOR_MARGIN),
                    title_font=dict(size=11, color=COLOR_MARGIN)),
    )
    period_label = _quarter_range_label(x)
    if period_label:
        fig = stamp_period(fig, period_label)
    return fig


def leverage_chart(df: pd.DataFrame, company_id: str, height: int = 360) -> go.Figure:
    history = company_history(df, company_id).tail(MAX_QUARTERS)
    x = _q_labels(history)
    fig = go.Figure()
    # Comfort / caution bands for net leverage (left axis only).
    fig.add_hrect(y0=0, y1=2.0, line_width=0, fillcolor=PALETTE["green_soft"], opacity=0.5, layer="below")
    fig.add_hrect(y0=2.0, y1=3.5, line_width=0, fillcolor=PALETTE["amber_soft"], opacity=0.5, layer="below")
    fig.add_scatter(x=x, y=history["net_debt_to_ebitda_ttm"], name="Net debt / EBITDA (LHS)", mode="lines+markers",
                    line=dict(color=COLOR_DEBT, width=2.8), marker=dict(size=6),
                    hovertemplate="ND/EBITDA: %{y:.1f}x<extra></extra>")
    # Coverage lives on its own right-hand axis: 1-3x leverage and 10-40x
    # coverage cannot share a scale without flattening one of them.
    fig.add_scatter(x=x, y=history["interest_coverage_ttm"], name="Interest coverage (RHS)", mode="lines+markers",
                    line=dict(color=COLOR_CASH, width=2.4), marker=dict(size=6), yaxis="y2",
                    hovertemplate="Coverage: %{y:.1f}x<extra></extra>")
    fig = _style(fig, "LTM Leverage &amp; Interest Coverage",
                 "Rolling four-quarter basis | bands (LHS): <=2.0x comfortable, 2.0-3.5x watch | coverage on RHS", height)
    fig.update_layout(
        yaxis=dict(title="Net debt / EBITDA", ticksuffix="x", **_AXIS),
        yaxis2=dict(title="EBITDA / interest", overlaying="y", side="right", ticksuffix="x",
                    showgrid=False, zeroline=False, rangemode="tozero",
                    linecolor=PALETTE["line"],
                    tickfont=dict(size=11, color=COLOR_CASH),
                    title_font=dict(size=11, color=COLOR_CASH)),
    )
    period_label = _quarter_range_label(x)
    if period_label:
        fig = stamp_period(fig, period_label)
    return fig


def _peer_frame(df: pd.DataFrame, period, company_id: str, peer_ids: list | None = None) -> pd.DataFrame:
    if period is None:
        latest = latest_snapshot(df).copy()
    else:
        latest = df[df["period"] == period].copy()
    # An approved peer set (passed by the caller) wins over the static mapping.
    if peer_ids:
        ids = set(peer_ids) | {company_id}
        subset = latest[latest["company_id"].isin(ids)]
        if len(subset) >= 2:
            return subset.copy()
    group_col = "peer_group" if "peer_group" in latest.columns else "sector"
    anchor_group = latest.loc[latest["company_id"] == company_id, group_col]
    if not anchor_group.empty:
        same = latest[latest[group_col] == anchor_group.iloc[0]]
        if len(same) >= 3:
            latest = same.copy()
    return latest


def _scatter_label_text(latest: pd.DataFrame, xcol: str, ycol: str, company_id: str,
                        max_labels: int = 8) -> pd.Series:
    """Label only the anchor and the clearest outliers; the rest stay hover-only.

    Labeling every peer turns a 15-name scatter into overlapping ink. The
    anchor is always labeled; remaining slots go to the highest combined
    |z-score| across both plotted dimensions.
    """
    tickers = latest["ticker"].astype(str).str.replace(".SA", "", regex=False)
    if len(latest) <= max_labels:
        return tickers
    score = pd.Series(0.0, index=latest.index)
    for col in (xcol, ycol):
        s = pd.to_numeric(latest[col], errors="coerce")
        std = s.std(skipna=True)
        if pd.notna(std) and std > 0:
            score = score + ((s - s.mean(skipna=True)) / std).abs().fillna(0)
    show = latest["company_id"].eq(company_id)
    n_extra = max(0, max_labels - int(show.sum()))
    show.loc[score[~show].nlargest(n_extra).index] = True
    return tickers.where(show, "")


def peer_scatter(df: pd.DataFrame, period, company_id: str, height: int = 440, peer_ids: list | None = None) -> go.Figure:
    latest = _peer_frame(df, period, company_id, peer_ids)
    peer_reference = latest.loc[latest["company_id"].astype(str) != str(company_id)]
    med_x = peer_reference["revenue_yoy_growth"].median(skipna=True)
    med_y = peer_reference["ebitda_margin_ttm"].median(skipna=True)
    labels = _scatter_label_text(latest, "revenue_yoy_growth", "ebitda_margin_ttm", company_id)

    fig = go.Figure()
    for is_anchor, sub in latest.groupby(latest["company_id"].eq(company_id)):
        fig.add_scatter(
            x=sub["revenue_yoy_growth"], y=sub["ebitda_margin_ttm"], mode="markers+text",
            text=labels.loc[sub.index], textposition="top center",
            textfont=dict(size=10, color=PALETTE["slate"]),
            customdata=[t.replace(".SA", "") for t in sub["ticker"]],
            marker=dict(size=(18 if is_anchor else 13), color=(COLOR_ANCHOR if is_anchor else COLOR_PEER),
                        line=dict(width=(1.6 if is_anchor else 0.6), color="#ffffff"),
                        opacity=0.95),
            name=("Anchor" if is_anchor else "Peers"),
            hovertemplate="%{customdata}<br>Growth %{x:.1%}<br>Margin %{y:.1%}<extra></extra>",
        )
    if pd.notna(med_x):
        fig.add_vline(x=med_x, line=dict(color=PALETTE["muted_2"], width=1, dash="dash"))
    if pd.notna(med_y):
        fig.add_hline(y=med_y, line=dict(color=PALETTE["muted_2"], width=1, dash="dash"))
    fig = _style(fig, "Peer Positioning - Growth vs Margin",
                 "Latest-quarter growth vs LTM margin | selected company highlighted | dashed lines = peer medians (ex-company)", height)
    fig.update_xaxes(title="Revenue growth (latest quarter YoY)", tickformat=".0%")
    fig.update_yaxes(title="EBITDA margin (LTM)", tickformat=".0%")
    return fig


def peer_valuation_scatter(df: pd.DataFrame, period, company_id: str, height: int = 420, peer_ids: list | None = None) -> go.Figure:
    """EV/EBITDA against growth — the 'is the multiple earned?' view."""
    latest = _peer_frame(df, period, company_id, peer_ids).dropna(subset=["ev_to_ebitda_ttm"])
    # Names beyond the comps outlier cap distort the whole y-axis; keep them
    # out of the picture (disclosed) unless the anchor itself is the outlier.
    extreme = latest["ev_to_ebitda_ttm"].map(
        lambda v: multiple_outlier_reason("ev_to_ebitda_ttm", v) is not None)
    excluded = latest[extreme & ~latest["company_id"].eq(company_id)]
    latest = latest[~extreme | latest["company_id"].eq(company_id)]
    peer_reference = latest.loc[latest["company_id"].astype(str) != str(company_id)]
    med_x = peer_reference["revenue_yoy_growth"].median(skipna=True)
    med_y = peer_reference["ev_to_ebitda_ttm"].median(skipna=True)
    labels = _scatter_label_text(latest, "revenue_yoy_growth", "ev_to_ebitda_ttm", company_id)
    fig = go.Figure()
    for is_anchor, sub in latest.groupby(latest["company_id"].eq(company_id)):
        fig.add_scatter(
            x=sub["revenue_yoy_growth"], y=sub["ev_to_ebitda_ttm"], mode="markers+text",
            text=labels.loc[sub.index], textposition="top center",
            textfont=dict(size=10, color=PALETTE["slate"]),
            customdata=[t.replace(".SA", "") for t in sub["ticker"]],
            marker=dict(size=(18 if is_anchor else 13), color=(COLOR_ANCHOR if is_anchor else COLOR_PEER),
                        line=dict(width=(1.6 if is_anchor else 0.6), color="#ffffff"), opacity=0.95),
            name=("Anchor" if is_anchor else "Peers"),
            hovertemplate="%{customdata}<br>Growth %{x:.1%}<br>EV/EBITDA %{y:.1f}x<extra></extra>",
        )
    if pd.notna(med_x):
        fig.add_vline(x=med_x, line=dict(color=PALETTE["muted_2"], width=1, dash="dash"))
    if pd.notna(med_y):
        fig.add_hline(y=med_y, line=dict(color=PALETTE["muted_2"], width=1, dash="dash"))
    if len(excluded):
        names = ", ".join(t.replace(".SA", "") for t in excluded["ticker"].head(4))
        subtitle = f"Off-scale outliers excluded: {names} (see peer benchmark bars)"
    else:
        subtitle = "Latest-quarter growth vs LTM valuation | upper-right = paying up for growth"
    fig = _style(fig, "Valuation vs Growth", subtitle, height)
    fig.update_xaxes(title="Revenue growth (latest quarter YoY)", tickformat=".0%")
    fig.update_yaxes(title="EV / EBITDA (LTM)", ticksuffix="x")
    return fig


def valuation_chart(df: pd.DataFrame, period, company_id: str, height: int = 400, peer_ids: list | None = None) -> go.Figure:
    latest = _peer_frame(df, period, company_id, peer_ids).dropna(subset=["ev_to_ebitda_ttm"]).sort_values("ev_to_ebitda_ttm")
    peer_reference = latest.loc[latest["company_id"].astype(str) != str(company_id)]
    stats = adjusted_stats(peer_reference if not peer_reference.empty else latest, "ev_to_ebitda_ttm")

    # Negative-EBITDA names cannot be drawn on a multiple axis; drop + disclose.
    negative = latest[latest["ev_to_ebitda_ttm"] < 0]
    latest = latest[latest["ev_to_ebitda_ttm"] >= 0]

    values = latest["ev_to_ebitda_ttm"].astype(float)
    tickers = [t.replace(".SA", "") for t in latest["ticker"]]
    capped = values > EV_EBITDA_MAX
    shown = values.clip(upper=EV_EBITDA_MAX)
    colors = [COLOR_ANCHOR if cid == company_id else (PALETTE["copper"] if is_cap else COLOR_PEER)
              for cid, is_cap in zip(latest["company_id"], capped)]
    fig = go.Figure(go.Bar(
        x=tickers, y=shown, marker_color=colors, marker_line_width=0,
        text=[f"{v:.0f}x ↑" if is_cap else f"{v:.1f}x" for v, is_cap in zip(values, capped)],
        textposition="outside", textfont=dict(size=11, color=PALETTE["slate"]),
        customdata=values, cliponaxis=False,
        hovertemplate="%{x}: %{customdata:.1f}x<extra></extra>",
    ))
    adj_med, raw_med = stats["adjusted_median"], stats["raw_median"]
    if pd.notna(adj_med):
        fig.add_hline(y=adj_med, line=dict(color=PALETTE["gold"], width=1.4, dash="dash"),
                      annotation_text=f"Adj. median {adj_med:.1f}x", annotation_position="top left",
                      annotation_yshift=8,
                      annotation_font=dict(size=10.5, color=PALETTE["gold"]))
    subtitle = "Company highlighted; dashed line = peer median excluding company and flagged outliers"
    if pd.notna(adj_med) and pd.notna(raw_med) and abs(raw_med - adj_med) > 0.05:
        subtitle = (f"Anchor highlighted | median excl. outliers {adj_med:.1f}x "
                    f"(raw incl. outliers {raw_med:.1f}x)")
    fig = _style(fig, "EV / EBITDA (LTM) - Peer Benchmark", subtitle, height)
    fig.update_yaxes(title="EV / EBITDA (LTM)", ticksuffix="x",
                     range=[0, EV_EBITDA_MAX * 1.14] if capped.any() else None)

    # Outlier disclosure sits in the bottom margin, clear of the tick labels.
    notes = []
    if capped.any():
        notes.append("bars capped at " + f"{EV_EBITDA_MAX:.0f}x (true value labeled): "
                     + ", ".join(t for t, c in zip(tickers, capped) if c))
    if len(negative):
        notes.append("negative EBITDA excluded: "
                     + ", ".join(t.replace(".SA", "") for t in negative["ticker"]))
    if notes:
        fig.add_annotation(x=0, y=0, xref="paper", yref="paper", xanchor="left",
                           yanchor="top", yshift=-58, showarrow=False, align="left",
                           text=" | ".join(notes),
                           font=dict(size=10, color=PALETTE["muted_2"]))
        fig.update_layout(margin=dict(b=84))
    return fig


# --- Actual vs Consensus charts ----------------------------------------------

def consensus_beat_chart(rows: list[dict], currency: str = "", height: int = 340,
                         true_surprise: bool = False) -> go.Figure | None:
    """Grouped actual-vs-consensus bars for the currency metrics (Revenue/EBITDA)."""
    usable = [r for r in rows if r["metric"] in ("Revenue", "EBITDA")
              and r.get("actual") is not None and r.get("consensus") is not None]
    if not usable:
        return None
    metrics = [r["metric"] for r in usable]
    fig = go.Figure()
    estimate_name = "Pre-report consensus" if true_surprise else "Current IQ_FQ estimate"
    fig.add_bar(x=metrics, y=[r["consensus"] for r in usable], name=estimate_name,
                marker_color=COLOR_GRAY, marker_line_width=0, opacity=0.75,
                hovertemplate="Consensus: %{y:,.0f}<extra></extra>")
    fig.add_bar(x=metrics, y=[r["actual"] for r in usable], name="Reported actual (latest Q)",
                marker_color=[COLOR_GREEN if r["status"] == "beat" else
                              (COLOR_RED if r["status"] == "miss" else COLOR_BLUE)
                              for r in usable],
                marker_line_width=0,
                text=[f"{r['delta_pct']:+.1%}" for r in usable], textposition="outside",
                textfont=dict(size=11.5, color=PALETTE["slate"]), cliponaxis=False,
                hovertemplate="Actual: %{y:,.0f}<extra></extra>")
    comparison = ("True earnings surprise vs point-in-time pre-report consensus"
                  if true_surprise else "Directional comparison vs current estimate - not a historical earnings surprise")
    fig = _style(fig, "Latest Reported Quarter vs Estimate",
                 f"{comparison} | {currency}m", height)
    fig.update_layout(barmode="group", bargap=0.4, bargroupgap=0.12)
    fig.update_yaxes(title=f"{currency}m" if currency else "")
    fig.update_xaxes(showgrid=False)
    return fig


def revision_momentum_chart(revisions: dict, height: int = 340) -> go.Figure | None:
    """30d/90d NTM consensus drift by metric — the direction-of-travel view."""
    rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("eps", "EPS")]:
        r = revisions.get(metric, {})
        if r.get("d30") is not None or r.get("d90") is not None:
            rows.append((label, r.get("d30"), r.get("d90")))
    if not rows:
        return None
    labels = [r[0] for r in rows]
    fig = go.Figure()
    fig.add_bar(x=labels, y=[r[2] for r in rows], name="vs 90d ago",
                marker_color=COLOR_BLUE_2, marker_line_width=0, opacity=0.85,
                hovertemplate="90d: %{y:+.1%}<extra></extra>")
    fig.add_bar(x=labels, y=[r[1] for r in rows], name="vs 30d ago",
                marker_color=COLOR_BLUE, marker_line_width=0,
                hovertemplate="30d: %{y:+.1%}<extra></extra>")
    fig.add_hline(y=0, line=dict(color=PALETTE["line"], width=1))
    fig = _style(fig, "Revision Momentum", "NTM consensus vs 30 and 90 days ago", height)
    fig.update_layout(barmode="group", bargap=0.45, bargroupgap=0.12)
    fig.update_yaxes(tickformat="+.0%")
    fig.update_xaxes(showgrid=False)
    return fig


def guidance_vs_consensus_chart(guidance: dict, height: int = 250) -> go.Figure | None:
    """Guidance range bar with the consensus marker inside (or outside) it."""
    if not guidance or guidance.get("low") is None or guidance.get("high") is None:
        return None
    low, high, mid = guidance["low"], guidance["high"], guidance.get("midpoint")
    # Consensus level backed out of the midpoint-vs-consensus ratio.
    vs = guidance.get("vs_consensus")
    consensus = (mid / (1.0 + vs)) if (mid is not None and vs is not None and vs > -1) else None
    label = str(guidance.get("metric", "Guided metric"))
    fig = go.Figure()
    fig.add_bar(y=[label], x=[high - low], base=[low], orientation="h", width=0.4,
                marker=dict(color=PALETTE["sage_soft"], line=dict(color=PALETTE["sage"], width=1.2)),
                hovertemplate=f"Guidance {low:,.0f} - {high:,.0f}<extra></extra>", showlegend=False)
    if mid is not None:
        fig.add_scatter(y=[label], x=[mid], mode="markers", name="Midpoint",
                        marker=dict(symbol="line-ns", size=18, line=dict(color=PALETTE["charcoal"], width=2.5)),
                        hovertemplate=f"Midpoint {mid:,.0f}<extra></extra>")
    if consensus is not None:
        fig.add_scatter(y=[label], x=[consensus], mode="markers", name="Consensus",
                        marker=dict(symbol="diamond", size=12, color=COLOR_GOLD,
                                    line=dict(color=PALETTE["charcoal"], width=1)),
                        hovertemplate=f"Consensus {consensus:,.0f}<extra></extra>")
    fig = _style(fig, "Guidance vs Consensus",
                 "Band = guided range | tick = midpoint | diamond = consensus", height)
    fig.update_yaxes(showgrid=False)
    return fig


# --- Data Audit charts --------------------------------------------------------

_SEVERITY_ORDER = ["high", "medium", "low", "info"]
_SEVERITY_COLORS = {"high": COLOR_RED, "medium": COLOR_AMBER,
                    "low": COLOR_GRAY, "info": PALETTE["muted_2"]}


def audit_findings_by_check_chart(issues: pd.DataFrame, height: int | None = None) -> go.Figure:
    """Findings per check family, stacked by severity — where the data hurts."""
    counts = (issues.groupby(["check", "severity"]).size().unstack(fill_value=0)
              .reindex(columns=_SEVERITY_ORDER, fill_value=0))
    counts = counts.loc[counts.sum(axis=1).sort_values(ascending=True).index]
    height = height or max(300, 130 + 30 * len(counts))
    fig = go.Figure()
    for sev in _SEVERITY_ORDER:
        if counts[sev].sum() == 0:
            continue
        fig.add_bar(y=list(counts.index), x=counts[sev], name=sev, orientation="h",
                    marker_color=_SEVERITY_COLORS[sev], marker_line_width=0,
                    hovertemplate="%{y} | " + sev + ": %{x}<extra></extra>")
    fig = _style(fig, "Findings by Check", "Stacked by severity", height)
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(showgrid=False, automargin=True)
    fig.update_xaxes(title="findings")
    return fig


def audit_severity_chart(issues: pd.DataFrame, height: int = 300) -> go.Figure:
    """Simple severity distribution for the audit header."""
    counts = issues["severity"].value_counts().reindex(_SEVERITY_ORDER, fill_value=0)
    fig = go.Figure(go.Bar(
        x=[s.title() for s in counts.index], y=counts.values,
        marker_color=[_SEVERITY_COLORS[s] for s in counts.index], marker_line_width=0,
        text=[str(int(v)) for v in counts.values], textposition="outside",
        textfont=dict(size=12, color=PALETTE["slate"]), cliponaxis=False,
        hovertemplate="%{x}: %{y}<extra></extra>", showlegend=False,
    ))
    fig = _style(fig, "Severity Distribution", "All findings, current dataset", height)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title="findings", rangemode="tozero")
    return fig
