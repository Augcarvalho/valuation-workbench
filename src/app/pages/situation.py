"""Company Situation: verdict, KPIs, flags, and the analyst thesis."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store
from src.config import PRIVATE_THESES_DIR
from src.modeling.assessment import Kpi, build_assessment
from src.reporting.charts import revenue_ebitda_chart
from src.utils import fmt_multiple, fmt_ordinal, fmt_signed_pct


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    ui.header_band(a.row, DEMO_MODE)
    ui.verdict_banner(a)

    ui.section("Key Performance Indicators", "Business-model-aware traffic lights | percentiles vs the true peer group")
    ui.kpi_grid(a.kpis[:5], columns=5)

    # Why-now strip.
    hc, rev = a.history_context, a.revisions
    why_cards = [
        Kpi("attn", "Attention Score", f"{a.attention_score:.0f}", "0–100 · drives Home ranking",
            "yellow" if a.attention_score >= 40 else "n/a"),
        Kpi("hist", "Multiple vs Own History",
            fmt_ordinal(hc.get("percentile")) + " pctile" if hc.get("available") else "n/a",
            (f"median {fmt_multiple(hc.get('median'))} · z {hc.get('z_score'):+.1f}" if hc.get("available")
             else "valuation history not populated"),
            "n/a"),
        Kpi("revs", "Estimate Momentum", rev.get("direction", "n/a").title(),
            (f"NTM revenue {fmt_signed_pct(rev.get('revenue_30d'))} over 30d" if rev.get("revenue_30d") is not None
             else "consensus not populated"),
            {"cutting": "red", "raising": "green"}.get(rev.get("direction"), "n/a")),
        Kpi("earn", "Next Earnings", rev.get("next_earnings_date") or "n/a", "Catalyst window", "n/a"),
        Kpi("stage", "Thesis Stage", a.thesis.stage_label if (a.thesis and a.thesis.exists) else "None",
            "From the analyst thesis file", "n/a"),
    ]
    ui.section("Why Now")
    ui.kpi_grid(why_cards, columns=5)

    left, right = st.columns([1.45, 1.0], gap="medium")
    with left:
        st.plotly_chart(revenue_ebitda_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with right:
        ui.memo("Executive Commentary", a.commentary)
        st.write("")
        ui.memo("Investment View", a.sponsor_view)

    ui.section("Investment Assessment")
    pos, con = st.columns(2, gap="medium")
    with pos:
        ui.bullet_list("Key Positives", a.positives, "pos")
    with con:
        ui.bullet_list("Key Concerns", a.concerns, "con")

    ui.section("Red Flags & Management Questions", "Business-model-aware rules; sharpen before the IC meeting")
    fcol, qcol = st.columns([1.3, 1.0], gap="medium")
    with fcol:
        ui.flag_list(a.red_flags)
    with qcol:
        ui.bullet_list("Questions for Management", a.management_questions, "q")

    # --- Analyst thesis (merged from the former Company Thesis page) --------------
    thesis = a.thesis
    if thesis is None or not thesis.exists:
        from src.modeling.thesis import thesis_filename
        target_dir = store.theses_dir or PRIVATE_THESES_DIR
        ui.section("Analyst Thesis", "No thesis on file yet")
        st.markdown(
            f"""
            <div class="pe-memo"><h4>Start the thesis</h4>
            <p style="font-family:var(--font-sans);font-size:13px">
            No analyst thesis exists for this name yet. Copy
            <code>data/templates/thesis_template.yaml</code> to
            <code>{target_dir}\\{thesis_filename(company_id)}</code>
            and fill in the variant perception, key debate, catalysts, risks, and scenario cases.
            This section, the IC memo, and the scenario engine pick it up automatically on the next rerun.</p></div>
            """,
            unsafe_allow_html=True,
        )
    else:
        ui.section("Analyst Thesis", f"Stage: {thesis.stage_label} | from the thesis file")
        ui.memo("What We Would Own", thesis.thesis or "—")
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            ui.memo("Variant Perception", thesis.variant_perception or "—")
        with c2:
            ui.memo("Key Debate", thesis.key_debate or "—")

        c1, c2 = st.columns(2, gap="medium")
        with c1:
            items = [f"{c.get('date', '')} — {c.get('event', '')}" + (f" ({c.get('note')})" if c.get("note") else "")
                     for c in thesis.catalysts] or ["No dated catalysts on file."]
            ui.bullet_list("Catalysts", items, "q")
        with c2:
            ui.bullet_list("Risks", thesis.risks or ["No analyst risks on file."], "con")

        if thesis.journal:
            entries = [f"{j.get('date', '')}: {j.get('note', '')}" for j in reversed(thesis.journal)]
            ui.bullet_list("Journal — Latest Entries", entries[:6], "q")

        ui.footnote(f"Source file: <code>{thesis.path}</code> — edit and rerun to update.")
