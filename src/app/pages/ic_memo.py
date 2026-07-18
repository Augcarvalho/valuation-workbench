"""IC Memo Export: the one-click decision document."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.app import components as ui
from src.app.context import DEMO_MODE, get_store
from src.modeling.assessment import build_assessment
from src.reporting.board_pack import generate_board_pack
from src.reporting.ic_memo import generate_ic_memo


def render(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    ui.header_band(a.row, DEMO_MODE)
    ui.section("IC Memo Export", "The decision document: machine rigor + analyst judgment in one file")

    sections = [
        "Cover & verdict", "Situation overview", "Why now", "Business quality",
        "Variant perception", "Key debate", "Financial snapshot", "Valuation & scenarios",
        "Catalysts & risks", "Diligence questions", "Decision & next steps", "Methodology appendix",
    ]
    chips = " ".join(f'<span class="pe-tag">{s}</span>' for s in sections)
    st.markdown(f'<div style="margin:2px 0 14px;line-height:2.1">{chips}</div>', unsafe_allow_html=True)

    with st.spinner("Rendering IC memo…"):
        memo_path = generate_ic_memo(demo=DEMO_MODE, company_id=company_id)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download IC Memo (HTML)", data=Path(memo_path).read_bytes(),
            file_name=Path(memo_path).name, mime="text/html", use_container_width=True,
        )
    with c2:
        with st.expander("Legacy board pack (monitoring format)"):
            outputs = generate_board_pack(demo=DEMO_MODE, company_id=company_id, output_format="html")
            bp = outputs.get("html")
            if bp and Path(bp).exists():
                st.download_button("Download board pack (HTML)", data=Path(bp).read_bytes(),
                                   file_name=Path(bp).name, mime="text/html", use_container_width=True)
    output_label = "data_private/reports/" if not DEMO_MODE else "reports/sample/"
    ui.footnote(f"Written to <code>{output_label}</code>"
                + (" — private outputs never enter version control." if not DEMO_MODE else "."))

    with st.expander("Preview IC memo", expanded=True):
        components.html(Path(memo_path).read_text(encoding="utf-8"), height=900, scrolling=True)
