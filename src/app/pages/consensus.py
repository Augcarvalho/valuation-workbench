"""Actual vs Consensus: beats/misses and revision momentum."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store
from src.modeling.assessment import Kpi, build_assessment
from src.reporting.charts import consensus_beat_chart, guidance_vs_consensus_chart, revision_momentum_chart


def render(df: pd.DataFrame, company_id: str) -> None:
    from src.modeling.consensus import build_consensus_read

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    ui.header_band(row, DEMO_MODE)

    read = build_consensus_read(row)

    def _tone_ct(v, invert=False):
        if v is None:
            return "n/a"
        good = v > 0 if not invert else v < 0
        return "green" if good else "red"

    rev = read.revisions
    ui.section("Consensus Snapshot", f"{read.comparison_label} | NTM revisions")
    beat_by = {r["metric"]: r for r in read.rows}
    cards = []
    for metric in ["Revenue", "EBITDA"]:
        b = beat_by.get(metric)
        cards.append(Kpi(metric[:3].lower(), f"{metric} vs Consensus",
                         f"{b['delta_pct']:+.1%}" if b else "n/a",
                         b["status"].upper() if b else "consensus not populated",
                         _tone_ct(b["delta_pct"]) if b else "n/a"))
    cards.append(Kpi("r30", "NTM Revenue Revision (30d)",
                     f"{rev['revenue']['d30']:+.1%}" if rev["revenue"]["d30"] is not None else "n/a",
                     "consensus momentum", _tone_ct(rev["revenue"]["d30"])))
    cards.append(Kpi("r90", "NTM Revenue Revision (90d)",
                     f"{rev['revenue']['d90']:+.1%}" if rev["revenue"]["d90"] is not None else "n/a",
                     "consensus momentum", _tone_ct(rev["revenue"]["d90"])))
    cards.append(Kpi("ne", "Next Earnings", read.next_earnings or "n/a",
                     f"{read.num_analysts:.0f} analysts" if read.num_analysts else "coverage n/a",
                     "n/a"))
    ui.kpi_grid(cards, columns=5)

    beat_fig = consensus_beat_chart(read.rows, currency=str(row.get("currency", "")),
                                    true_surprise=read.true_surprise)
    momentum_fig = revision_momentum_chart(rev)
    if beat_fig is not None or momentum_fig is not None:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            if beat_fig is not None:
                st.plotly_chart(beat_fig, use_container_width=True, config=PLOTLY_CONFIG)
        with c2:
            if momentum_fig is not None:
                st.plotly_chart(momentum_fig, use_container_width=True, config=PLOTLY_CONFIG)

    if read.rows:
        note = ("Point-in-time consensus immediately before the release"
                if read.true_surprise else
                "Current IQ_FQ estimate; directional comparison only, not an earnings surprise")
        ui.section(read.comparison_label, note)
        estimate_header = "Pre-Report Consensus" if read.true_surprise else "Current IQ_FQ Estimate"
        ui.html_table(["Metric", "Reported Actual (Latest Q)", estimate_header,
                       "Absolute Delta", "Delta %", "Status"],
                      [[r["metric"], f"{r['actual']:,.1f}", f"{r['consensus']:,.1f}",
                        f"{r['delta']:+,.1f}", f"{r['delta_pct']:+.1%}",
                        ui.cell_pill(r["status"].upper(),
                                     "green" if r["delta"] > 0 else
                                     ("red" if r["delta"] < 0 else "n/a"))]
                       for r in read.rows], numeric_from=1)

    ui.section("Revision Momentum", "NTM consensus vs 30 and 90 days ago")
    rows = []
    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("eps", "EPS")]:
        d30, d90 = rev[metric]["d30"], rev[metric]["d90"]
        rows.append([label,
                     f"{d30:+.1%}" if d30 is not None else "n/a",
                     f"{d90:+.1%}" if d90 is not None else "n/a"])
    ui.html_table(["NTM metric", "vs 30d ago", "vs 90d ago"], rows, numeric_from=1)

    if read.guidance:
        g = read.guidance
        ui.section("Guidance vs Consensus")
        guide_fig = guidance_vs_consensus_chart(g)
        if guide_fig is not None:
            st.plotly_chart(guide_fig, use_container_width=True, config=PLOTLY_CONFIG)
        ui.kpi_grid([
            Kpi("gl", "Guidance Range", f"{g['low']:,.0f} - {g['high']:,.0f}", g["metric"], "n/a"),
            Kpi("gm", "Midpoint", f"{g['midpoint']:,.0f}", "", "n/a"),
            Kpi("gc", "Midpoint vs Consensus",
                f"{g['vs_consensus']:+.1%}" if g["vs_consensus"] is not None else "n/a",
                "above = implicit raise", _tone_ct(g["vs_consensus"])),
        ], columns=3)

    if read.missing:
        ui.footnote("Not available in the current export: " + "; ".join(sorted(set(read.missing)))
                    + ". Optional fields are documented in data/templates - no values are faked.")
