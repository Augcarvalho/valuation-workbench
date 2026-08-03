"""IC Memo Export: gated decision document built from the canonical case."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.app import components as ui
from src.app.context import DEMO_MODE, get_store
from src.modeling.assessment import Kpi, build_assessment
from src.modeling.valuation_case import CaseNotApplicableError, build_valuation_case
from src.reporting.board_pack import generate_board_pack
from src.reporting.ic_memo import generate_ic_memo


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    assessment = build_assessment(df, company_id, store=store)
    ui.header_band(assessment.row, DEMO_MODE)
    ui.section("IC Memo Export", "Canonical underwriting case with explicit readiness controls")

    case = None
    try:
        case = build_valuation_case(df, company_id, store=store)
    except CaseNotApplicableError:
        pass

    if case is not None:
        readiness = case.readiness
        ui.kpi_grid([
            Kpi("ready", "Case Readiness", readiness.status.replace("_", " ").title(),
                "Final IC export requires reviewed peers and final assumptions",
                "green" if readiness.can_export_final else "yellow"),
            Kpi("case", "Canonical Case ID", case.case_id, "Immutable methodology and input fingerprint", "n/a"),
            Kpi("vintage", "Data Vintage", str(case.data_vintage or "n/a"),
                f"Methodology {case.methodology_version}", "n/a"),
        ], columns=3)
        for blocker in readiness.blockers:
            st.error(f"Readiness blocker: {blocker}")
        for warning in readiness.warnings:
            st.warning(f"Review item: {warning}")
        final_ready = readiness.can_export_final
    else:
        final_ready = False
        st.info("The EBITDA DCF/LBO framework is not applicable to this business model. "
                "The memo will use the business-model-specific valuation framework.")

    sections = [
        "Cover & verdict", "Situation overview", "Why now", "Business quality",
        "Variant perception", "Key debate", "Financial snapshot", "Valuation & scenarios",
        "Catalysts & risks", "Diligence questions", "Decision & next steps", "Methodology appendix",
    ]
    chips = " ".join(f'<span class="pe-tag">{section}</span>' for section in sections)
    st.markdown(f'<div style="margin:2px 0 14px;line-height:2.1">{chips}</div>', unsafe_allow_html=True)

    state_key = f"ic_memo_export::{DEMO_MODE}::{company_id}"
    label = "Generate Final IC Memo" if final_ready else "Generate Screening Memo"
    if st.button(label, key=f"generate_memo::{DEMO_MODE}::{company_id}", use_container_width=False):
        with st.spinner("Rendering IC memo..."):
            st.session_state[state_key] = str(generate_ic_memo(demo=DEMO_MODE, company_id=company_id))
        st.success("Memo generated from the current canonical case.")

    saved = st.session_state.get(state_key)
    if not saved or not Path(saved).exists():
        ui.footnote("No report is generated when this page opens. Review the case and generate it explicitly.")
        return

    memo_path = Path(saved)
    st.download_button(
        "Download IC Memo (HTML)", data=memo_path.read_bytes(), file_name=memo_path.name,
        mime="text/html", use_container_width=False,
    )

    with st.expander("Legacy monitoring board pack"):
        if st.button("Generate Monitoring Board Pack", key=f"generate_board_pack::{company_id}"):
            outputs = generate_board_pack(demo=DEMO_MODE, company_id=company_id, output_format="html")
            board_pack = outputs.get("html")
            if board_pack and Path(board_pack).exists():
                st.download_button(
                    "Download board pack (HTML)", data=Path(board_pack).read_bytes(),
                    file_name=Path(board_pack).name, mime="text/html",
                )

    output_label = "data_private/reports/" if not DEMO_MODE else "reports/sample/"
    ui.footnote(
        f"Written to <code>{output_label}</code>"
        + (" - private outputs never enter version control." if not DEMO_MODE else ".")
    )
    with st.expander("Preview IC memo", expanded=True):
        components.html(memo_path.read_text(encoding="utf-8"), height=900, scrolling=True)
