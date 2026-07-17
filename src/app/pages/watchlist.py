"""Watchlist Home: attention-ranked triage of the book."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, get_store, load_summary, tone, verdict_pill
from src.modeling.assessment import Kpi
from src.reporting.periods import source_as_of
from src.utils import fmt_multiple, fmt_ordinal, fmt_pct, fmt_signed_pct


def render(df: pd.DataFrame, company_id: str) -> None:
    summary = load_summary(DEMO_MODE)
    store = get_store(DEMO_MODE)

    mode_txt = "Public demo data" if DEMO_MODE else "Capital IQ private data"
    as_of_min = pd.Timestamp(summary["as_of"].min())
    as_of_max = pd.Timestamp(summary["as_of"].max())
    as_of_note = (
        f"Latest quarters span {as_of_min.strftime('%b %Y')} to {as_of_max.strftime('%d %b %Y')}"
        if as_of_min != as_of_max else f"As of {as_of_max.strftime('%d %b %Y')}"
    )
    side_note = []
    side_note.append("valuation history ✓" if store.has_valuation_history else "valuation history —")
    side_note.append("consensus ✓" if store.has_estimates else "consensus —")
    market_date = source_as_of(store.source_log, "market_data")
    market_note = (f"Market snapshot retrieved {market_date}" if market_date
                   else "Market snapshot date unavailable")

    st.markdown(
        f"""
        <div class="pe-header">
          <div class="pe-header-top">
            <div>
              <div class="kicker">Investment Watchlist | Where To Spend Time</div>
              <h1>Watchlist Home<span class="ticker">{len(summary)} names</span></h1>
            </div>
            <span class="pe-mode-pill {'pe-mode-demo' if DEMO_MODE else 'pe-mode-private'}">{mode_txt}</span>
          </div>
          <div class="pe-header-meta">
            <div class="pe-meta-item"><div class="pe-meta-label">Ranking</div>
              <div class="pe-meta-value">Attention score (valuation · revisions · inflection · flags)</div></div>
            <div class="pe-meta-item"><div class="pe-meta-label">Coverage</div>
              <div class="pe-meta-value">{summary['peer_group'].nunique()} peer groups | {' · '.join(side_note)}</div></div>
            <div class="pe-meta-item"><div class="pe-meta-label">Freshness</div>
              <div class="pe-meta-value">{market_note} | Financials: {as_of_note}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    counts = summary["verdict_key"].value_counts()
    cards = [
        Kpi("dw", "Do Work", str(int(counts.get("do_work", 0))), "Dislocation candidates: debate now", "yellow"),
        Kpi("av", "Avoid / Pass", str(int(counts.get("avoid", 0))), "Deteriorating, no valuation support", "red"),
        Kpi("wt", "Watch", str(int(counts.get("watch", 0))), "Mixed signals; no forced action", "n/a"),
        Kpi("cn", "Constructive", str(int(counts.get("constructive", 0))), "On track; monitor the thesis", "green"),
        Kpi("fl", "Open Red Flags", str(int(summary["flags"].sum())), "High / medium severity across the list", "n/a"),
    ]
    ui.kpi_grid(cards, columns=5)

    ui.section("Ranked Watchlist", "Ranked by attention score | N/M = not meaningful for that business model")
    groups = ["All peer groups"] + sorted(summary["peer_group"].dropna().unique())
    group_pick = st.selectbox("Filter by peer group", groups, label_visibility="collapsed")
    view = summary if group_pick == "All peer groups" else summary[summary["peer_group"] == group_pick]

    headers = ["#", "Attn", "Ticker", "Company", "Peer Group", "Verdict", "Stage",
               "Rev Growth (Latest Q YoY)", "Profitability (LTM)", "Current Multiple (LTM)",
               "vs Peer Median", "vs Own History", "NTM Revisions", "Flags", "Financials Through"]
    rows, classes = [], []
    for _, r in view.iterrows():
        g = r["revenue_yoy_growth"]
        prem = r["valuation_premium"]
        hist = r["history_percentile"]
        prof_sig = str(r["profitability_signal"])
        prof_txt = fmt_pct(r["profitability"]) if pd.notna(r["profitability"]) else "n/a"
        mult = f"{fmt_multiple(r['multiple_value'])} {r['multiple_name']}" if pd.notna(r["multiple_value"]) else "n/a"
        rev_dir = str(r["revision_direction"])
        rows.append([
            str(int(r["rank"])),
            f"<b>{r['attention_score']:.0f}</b>",
            str(r["ticker"]),
            str(r["company_name"])[:22],
            str(r["peer_group"])[:26],
            verdict_pill(r["verdict_key"], r["verdict_label"]),
            str(r.get("thesis_stage", "") or "—"),
            tone(fmt_signed_pct(g), (g > 0) if pd.notna(g) else None),
            ui.cell_pill(prof_txt, prof_sig) if prof_sig in {"green", "yellow", "red"} else prof_txt,
            mult,
            tone(fmt_signed_pct(prem), (prem < 0) if pd.notna(prem) else None) if pd.notna(prem) else "n/a",
            fmt_ordinal(hist) if pd.notna(hist) else "—",
            {"cutting": '<span class="tone-red">Cutting</span>', "raising": '<span class="tone-green">Raising</span>',
             "stable": "Stable"}.get(rev_dir, "—"),
            str(int(r["flags"])),
            ui.quarter_label(r["as_of"]),
        ])
        classes.append("anchor" if r["company_id"] == company_id else "")
    ui.html_table(headers, rows, classes, numeric_from=7)
    ui.footnote(
        "Attention score (0–100) weighs valuation dislocation (vs peers and vs the company's own multiple history), "
        "estimate revision momentum, operating inflection, and open red flags. "
        "Profitability = LTM EBITDA margin (operating) or LTM net income margin (financials). "
        "Current multiple uses the latest market snapshot over an LTM denominator. "
        "vs Hist = current multiple's percentile within its own history (low = cheap vs itself). "
        "Financials-through dates differ because fiscal calendars differ."
    )

    picks = summary.head(5)
    ui.section("Why These Names First", "Verdict rationale for the top of the attention ranking")
    ui.bullet_list(
        "Attention Queue",
        [f"{r['ticker']} ({r['attention_score']:.0f}): {r['verdict_rationale']}" for _, r in picks.iterrows()],
        "q",
    )
