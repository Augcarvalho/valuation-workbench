from __future__ import annotations

import sys
from html import escape
from pathlib import Path

# Ensure the project root is importable when launched via `streamlit run`,
# which otherwise only puts the script's own directory on sys.path.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.app import components as ui
from src.app.theme import inject_theme
from src.config import (
    DEFAULT_PROCESSED_DATASET,
    DEFAULT_SOURCE_LOG,
    PRIVATE_PROCESSED_DATASET,
    PRIVATE_SOURCE_LOG,
    PRIVATE_THESES_DIR,
)
from src.ingestion.store import load_store
from src.modeling.assessment import Kpi, build_assessment, watchlist_summary
from src.modeling.metrics import latest_rows
from src.modeling.scenarios import cases_from_thesis, implied_expectations, run_cases, sensitivity_grid
from src.pipeline.build_dataset import build_dataset
from src.reporting.board_pack import generate_board_pack
from src.reporting.charts import (
    audit_findings_by_check_chart,
    audit_severity_chart,
    cash_conversion_chart,
    consensus_beat_chart,
    guidance_vs_consensus_chart,
    leverage_chart,
    margin_trend_chart,
    peer_scatter,
    peer_valuation_scatter,
    revenue_ebitda_chart,
    revision_momentum_chart,
    valuation_chart,
)
from src.reporting.ic_memo import generate_ic_memo
from src.utils import fmt_money, fmt_multiple, fmt_ordinal, fmt_pct, fmt_signed_pct

DEMO_MODE = "--demo" in sys.argv

st.set_page_config(
    page_title="Investment Watchlist",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

PAGES = {
    "WATCHLIST": ["Watchlist Home", "Compare"],
    "COMPANY": ["Company Situation", "Peer Benchmarking", "Actual vs Consensus",
                "Company Financials", "Capital Structure"],
    "VALUATION": ["Valuation Case", "Valuation & Expectations"],
    "OUTPUT": ["IC Memo Export", "Data Audit", "Data & Refresh"],
}


# --- data -------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _read_dataset(path_str: str, mtime: float) -> pd.DataFrame:
    # mtime keys the cache so a rebuilt dataset is picked up without restart.
    df = pd.read_csv(path_str, parse_dates=["period"])
    return df.sort_values(["company_id", "period"])


def _dataset_path(demo: bool) -> Path:
    if demo or not PRIVATE_PROCESSED_DATASET.exists():
        return DEFAULT_PROCESSED_DATASET
    return PRIVATE_PROCESSED_DATASET


def load_data(demo: bool) -> pd.DataFrame:
    if demo or not DEFAULT_PROCESSED_DATASET.exists():
        build_dataset("public-demo")
    path = _dataset_path(demo)
    return _read_dataset(str(path), path.stat().st_mtime)


def get_store(demo: bool):
    return load_store(demo)


@st.cache_data(show_spinner="Ranking the watchlist…")
def _summary_cached(demo: bool, dataset_mtime: float, side_key: str) -> pd.DataFrame:
    df = load_data(demo)
    return watchlist_summary(df, store=get_store(demo))


def load_summary(demo: bool) -> pd.DataFrame:
    path = _dataset_path(demo)
    store = get_store(demo)
    side_key = f"{len(store.valuation_history)}-{len(store.estimates)}-{store.theses_dir}"
    return _summary_cached(demo, path.stat().st_mtime, side_key)


def load_source_log(demo: bool) -> pd.DataFrame:
    source_path = DEFAULT_SOURCE_LOG if demo else PRIVATE_SOURCE_LOG
    if source_path.exists():
        return pd.read_csv(source_path)
    if DEFAULT_SOURCE_LOG.exists():
        return pd.read_csv(DEFAULT_SOURCE_LOG)
    return pd.DataFrame(columns=["table_name", "source_name", "source_url", "retrieved_at", "notes"])


# --- sidebar ----------------------------------------------------------------

def sidebar(df: pd.DataFrame) -> tuple[str, str]:
    st.sidebar.markdown(
        '<div class="sb-brand">Investment Watchlist</div><div class="sb-brand-rule"></div>'
        '<div class="sb-sub">Thesis-Driven Coverage</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown('<div class="sb-group">Company</div>', unsafe_allow_html=True)
    latest = latest_rows(df)
    labels = {
        f"{row.ticker.replace('.SA', '')} | {row.company_name}": row.company_id
        for row in latest.sort_values("ticker").itertuples()
    }
    selection = st.sidebar.selectbox("Select company", list(labels.keys()), label_visibility="collapsed")
    company_id = labels[selection]

    st.sidebar.markdown('<div class="sb-group">Views</div>', unsafe_allow_html=True)
    flat_pages = [p for group in PAGES.values() for p in group]
    page = st.sidebar.radio("Views", flat_pages, label_visibility="collapsed")

    row = latest[latest["company_id"] == company_id].iloc[0]
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    mode = "Public Demo" if DEMO_MODE else "Capital IQ - Private"
    st.sidebar.markdown(
        f'<div class="sb-sub">Data mode<br><b style="color:#fff">{mode}</b></div>'
        f'<div class="sb-sub" style="margin-top:10px">As of {ui.as_of_label(row["period"])}</div>'
        f'<div class="sb-sub" style="margin-top:14px;color:#7f96ad;font-size:10.5px;line-height:1.5">'
        f'Illustrative watchlist artifact. Not investment advice. '
        f'Licensed Capital IQ exports stay in <code>data_private/</code>.</div>',
        unsafe_allow_html=True,
    )
    return company_id, page


# --- shared building blocks -------------------------------------------------

def _tone(text: str, good: bool | None) -> str:
    if good is True:
        return f'<span class="tone-green">{text}</span>'
    if good is False:
        return f'<span class="tone-red">{text}</span>'
    return text


def _verdict_pill(verdict_key: str, label: str) -> str:
    from src.branding import PALETTE, VERDICT_COLORS

    color = VERDICT_COLORS.get(verdict_key, PALETTE["muted_2"])
    soft = {
        "do_work": PALETTE["amber_soft"],
        "constructive": PALETTE["green_soft"],
        "avoid": PALETTE["red_soft"],
    }.get(verdict_key, PALETTE["panel_alt"])
    return (
        f'<span class="cell-pill" style="background:{soft};color:{color};white-space:nowrap">{label}</span>'
    )


def _snapshot_financials(row: pd.Series, currency: str) -> None:
    def pct_tone(v):
        return _tone(fmt_pct(v), (v > 0) if pd.notna(v) else None)

    rows = [
        ["Revenue", fmt_money(row.get("revenue"), currency), fmt_money(row.get("revenue_ttm"), currency),
         pct_tone(row.get("revenue_yoy_growth"))],
        ["Gross profit", fmt_money(row.get("gross_profit"), currency), fmt_money(row.get("gross_profit_ttm"), currency),
         fmt_pct(row.get("gross_margin_ttm"))],
        ["EBITDA", fmt_money(row.get("ebitda"), currency), fmt_money(row.get("ebitda_ttm"), currency),
         fmt_pct(row.get("ebitda_margin_ttm"))],
        ["Net income", fmt_money(row.get("net_income"), currency), fmt_money(row.get("net_income_ttm"), currency),
         fmt_pct(row.get("net_income_margin_ttm"))],
        ["CFO", fmt_money(row.get("cfo"), currency), fmt_money(row.get("cfo_ttm"), currency), "--"],
        ["Free cash flow", fmt_money(row.get("fcf"), currency), fmt_money(row.get("fcf_ttm"), currency),
         fmt_pct(row.get("fcf_conversion_ttm"))],
    ]
    if pd.notna(row.get("sbc_ttm")):
        rows.append(["Stock-based comp", fmt_money(row.get("sbc"), currency), fmt_money(row.get("sbc_ttm"), currency),
                     fmt_pct(row.get("sbc_pct_of_fcf_ttm"))])
    ui.html_table(["Metric", "Latest Qtr", "TTM", "Margin / YoY"], rows)


def _snapshot_valuation(row: pd.Series, currency: str) -> None:
    rows = [
        ["Market cap", fmt_money(row.get("market_cap"), currency)],
        ["Net debt", fmt_money(row.get("net_debt"), currency)],
        ["Enterprise value", fmt_money(row.get("enterprise_value"), currency)],
        ["EV / Revenue", fmt_multiple(row.get("ev_to_revenue_ttm"))],
        ["EV / EBITDA", fmt_multiple(row.get("ev_to_ebitda_ttm"))],
        ["P / E", fmt_multiple(row.get("pe_ttm"))],
        ["Net debt / EBITDA", fmt_multiple(row.get("net_debt_to_ebitda_ttm"))],
        ["ROIC (TTM)", fmt_pct(row.get("roic_ttm"))],
    ]
    ui.html_table(["Trading & Valuation", "Current"], rows)


# --- pages ------------------------------------------------------------------

def page_watchlist_home(df: pd.DataFrame, company_id: str) -> None:
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
              <div class="pe-meta-value">{as_of_note}</div></div>
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

    headers = ["#", "Attn", "Ticker", "Company", "Peer Group", "Verdict", "Stage", "Rev YoY", "Profit.", "Multiple", "vs Peers", "vs Hist", "Revisions", "Flags", "As Of"]
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
            _verdict_pill(r["verdict_key"], r["verdict_label"]),
            str(r.get("thesis_stage", "") or "—"),
            _tone(fmt_signed_pct(g), (g > 0) if pd.notna(g) else None),
            ui.cell_pill(prof_txt, prof_sig) if prof_sig in {"green", "yellow", "red"} else prof_txt,
            mult,
            _tone(fmt_signed_pct(prem), (prem < 0) if pd.notna(prem) else None) if pd.notna(prem) else "n/a",
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
        "Profitability = TTM EBITDA margin (operating) or TTM net income margin (financials). "
        "vs Hist = current multiple's percentile within its own history (low = cheap vs itself). "
        "Per-name as-of dates differ because fiscal calendars differ."
    )

    picks = summary.head(5)
    ui.section("Why These Names First", "Verdict rationale for the top of the attention ranking")
    ui.bullet_list(
        "Attention Queue",
        [f"{r['ticker']} ({r['attention_score']:.0f}): {r['verdict_rationale']}" for _, r in picks.iterrows()],
        "q",
    )


def page_company_situation(df: pd.DataFrame, company_id: str) -> None:
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


def page_company_financials(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    ui.header_band(row, DEMO_MODE)

    ui.section("Financial Snapshot", f"As reported | {ui.quarter_label(row['period'])}")
    fcol, vcol = st.columns([1.25, 1.0], gap="medium")
    with fcol:
        _snapshot_financials(row, currency)
    with vcol:
        _snapshot_valuation(row, currency)

    ui.section("Quarterly Performance", "Latest reported quarter highlighted")
    history = df[df["company_id"] == company_id].sort_values("period").tail(8)
    headers = ["Period", "Revenue", "Rev YoY", "EBITDA", "EBITDA mgn", "FCF", "FCF conv"]
    rows, classes = [], []
    for _, h in history.iterrows():
        g = h.get("revenue_yoy_growth")
        rows.append([
            ui.quarter_label(h["period"]),
            fmt_money(h.get("revenue"), currency),
            _tone(fmt_signed_pct(g), (g > 0) if pd.notna(g) else None),
            fmt_money(h.get("ebitda"), currency),
            fmt_pct(h.get("ebitda_margin")),
            fmt_money(h.get("fcf"), currency),
            fmt_pct(h.get("fcf_conversion_ttm")),
        ])
        classes.append("anchor" if h["period"] == row["period"] else "")
    ui.html_table(headers, rows, classes)

    ui.section("Operating Profile")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(revenue_ebitda_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(margin_trend_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Cash, Working Capital & Leverage")
    cards = [
        Kpi("cfo", "CFO (TTM)", fmt_money(row.get("cfo_ttm"), currency), "Operating cash flow"),
        Kpi("fcf", "FCF (TTM)", fmt_money(row.get("fcf_ttm"), currency), "CFO less capex"),
        Kpi("conv", "FCF Conversion", fmt_pct(row.get("fcf_conversion_ttm")), "FCF / EBITDA",
            row.get("fcf_conversion_ttm_signal", "n/a")),
        Kpi("roic", "ROIC (TTM)", fmt_pct(row.get("roic_ttm")), "NOPAT / invested capital",
            row.get("roic_ttm_signal", "n/a")),
        Kpi("ccc", "Cash Conversion Cycle",
            f"{row.get('cash_conversion_cycle'):.0f}d" if pd.notna(row.get("cash_conversion_cycle")) else "n/a",
            "DSO + DIO − DPO"),
        Kpi("lev", "Net Debt / EBITDA", fmt_multiple(row.get("net_debt_to_ebitda_ttm")), "Leverage",
            row.get("net_debt_to_ebitda_ttm_signal", "n/a")),
    ]
    ui.kpi_grid(cards, columns=6)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(cash_conversion_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(leverage_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)


def page_valuation_case(df: pd.DataFrame, company_id: str) -> None:
    import numpy as np

    from src.branding import PALETTE
    from src.modeling.valuation_case import (
        CaseNotApplicableError,
        build_valuation_case,
        case_warnings,
    )
    from src.reporting import valuation_charts as vch
    from src.reporting.valuation_case import generate_valuation_case

    store = get_store(DEMO_MODE)
    a_head = build_assessment(df, company_id, store=store)
    ui.header_band(a_head.row, DEMO_MODE)

    # --- Applicability gate: never crash, degrade gracefully ------------------
    try:
        case = build_valuation_case(df, company_id, store=store)
    except CaseNotApplicableError as exc:
        st.markdown(
            f"""
            <div class="pe-verdict">
              <div class="pe-verdict-flag" style="background:{PALETTE['muted_2']}"></div>
              <div class="pe-verdict-body">
                <div class="pe-verdict-kicker">Valuation Case</div>
                <div class="pe-verdict-label" style="color:{PALETTE['slate']}">Not applicable - {exc.reason}</div>
                <div class="pe-verdict-rationale">{exc.detail}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # --- Financials-specific valuation (banks / lenders / platforms) --------
        a_gate = build_assessment(df, company_id, store=store)
        if str(a_gate.business_model) == "financial":
            from src.modeling.financials_valuation import build_financials_valuation
            from src.modeling.valuation_assumptions import load_wacc_params
            from src.modeling.wacc import build_wacc

            params = load_wacc_params(str(a_gate.row.get("currency", "USD")))
            w = build_wacc(a_gate.row, params, peers=a_gate.peers)
            fv = build_financials_valuation(a_gate.row, cost_of_equity=w.cost_of_equity)

            ui.section("Financials Valuation", "The framework banks and lenders are actually valued on")
            if fv.book_value is not None:
                roe_tone = ("green" if (fv.roe or 0) > w.cost_of_equity
                            else ("red" if fv.roe is not None else "n/a"))
                ui.kpi_grid([
                    Kpi("pe", "P/E (TTM)", f"{fv.pe:.1f}x" if fv.pe else "n/m",
                        "negative earnings" if fv.pe is None else "", "n/a"),
                    Kpi("pb", fv.pb_label, f"{fv.pb:.2f}x" if fv.pb else "n/a",
                        f"book source: {fv.book_source}", "n/a"),
                    Kpi("roe", "ROE vs COE",
                        f"{fv.roe:.1%} vs {w.cost_of_equity:.1%}" if fv.roe is not None else "n/a",
                        "value created only when ROE > COE", roe_tone),
                    Kpi("jpb", "Justified P/B",
                        f"{fv.justified_pb:.2f}x" if fv.justified_pb else "n/a",
                        f"(ROE - g) / (COE - g), g = {fv.growth:.1%}", "n/a"),
                    Kpi("erv", "Excess-Return Value",
                        f"{fv.excess_return_value:,.0f}" if fv.excess_return_value else "n/a",
                        (f"{fv.excess_return_upside:+.0%} vs market cap"
                         if fv.excess_return_upside is not None else "residual income model"),
                        ("green" if (fv.excess_return_upside or 0) > 0.15
                         else ("red" if (fv.excess_return_upside or 0) < -0.15 else "yellow"))
                        if fv.excess_return_upside is not None else "n/a"),
                ], columns=5)
                if fv.pb is not None and fv.justified_pb is not None:
                    verdict = "trades BELOW" if fv.pb < fv.justified_pb else "trades ABOVE"
                    ui.memo("Reading", f"At {fv.pb:.2f}x {fv.pb_label} vs a justified "
                            f"{fv.justified_pb:.2f}x, the market says this franchise {verdict} the "
                            f"multiple its ROE/COE spread supports. The excess-return model "
                            f"(book value + PV of returns above the cost of equity) is the "
                            f"cross-check - both collapse to book value when ROE = COE.")
            for wmsg in fv.warnings:
                ui.footnote(wmsg)
            ui.footnote("Limitations: TTM ROE (not normalized through the credit cycle), "
                        "growth is an assumption, and dividend-discount needs payout data "
                        "(dividends_paid exported but sparse). This is calibration, not a rating.")
        else:
            ui.section("What you can use instead")
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                ui.bullet_list("Available now", [
                    "Valuation & Expectations page: P/E vs peers and vs own history, revision momentum.",
                    "Peer Benchmarking: growth / profitability / multiple quartiles on the true comp set.",
                    "Company Situation: qualitative thesis case and journal.",
                ], "q")
            with c2:
                ui.bullet_list("Missing input", [
                    exc.detail,
                ], "con")
        return

    a = case.assessment
    row = a.row
    currency = row.get("currency", "USD")
    base = case.base

    # --- Status card (prominent, its own block) ---------------------------------
    status_key, status_label = vch.assumptions_status(case)
    badge_color = {"auto": PALETTE["red"], "illustrative": PALETTE["amber"],
                   "draft": PALETTE["amber"], "final": PALETTE["green"]}.get(status_key, PALETTE["muted_2"])
    if status_key != "final":
        from src.modeling.valuation_assumptions import assumptions_filename
        target_file = assumptions_filename(company_id)
        folder_name = Path(str(store.assumptions_dir)).name if store.assumptions_dir else "assumptions"
        detail = {
            "auto": (f"Every driver was derived mechanically from TTM data - no analyst file exists. "
                     f"Create <code>{folder_name}/{target_file}</code> from the template to set a real view."),
            "illustrative": "The analyst assumptions behind this case are labeled placeholders pending diligence.",
            "draft": "Analyst assumptions are in draft; numbers are directional.",
        }.get(status_key, "")
        st.markdown(
            f"""
            <div class="pe-memo" style="border-left-color:{badge_color};margin-bottom:10px">
              <h4 style="color:{badge_color}">{status_label}</h4>
              <p style="font-family:var(--font-sans);font-size:12.5px">{detail}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Recommendation banner ----------------------------------------------------
    rec_color = {"BUY": PALETTE["green"], "SELL": PALETTE["red"], "HOLD": PALETTE["gold"],
                 "INDICATIVE": PALETTE["muted_2"]}.get(case.recommendation.stance, PALETTE["muted_2"])
    target_txt = f" - target {base.target_price:,.2f} vs {base.current_price:,.2f}" if base.target_price else ""
    st.markdown(
        f"""
        <div class="pe-verdict">
          <div class="pe-verdict-flag" style="background:{rec_color}"></div>
          <div class="pe-verdict-body">
            <div class="pe-verdict-kicker">DCF {'Calibration' if status_key == 'auto' else 'Recommendation'} | WACC {case.wacc.wacc:.1%} | Exit {case.exit_multiple:g}x ({case.exit_multiple_source})</div>
            <div class="pe-verdict-label" style="color:{rec_color}">{case.recommendation.stance}{target_txt}</div>
            <div class="pe-verdict-rationale">{case.recommendation.headline} {case.recommendation.reconciliation}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Model-quality warnings ------------------------------------------------------
    warnings = case_warnings(case)
    tv_note = vch.terminal_value_divergence(case)
    if tv_note:
        warnings.append({"severity": "medium", "text": tv_note})
    if a.peer_warning:
        warnings.append({"severity": "high", "text": a.peer_warning})
    if not a.peer_reviewed:
        if a.peer_source == "capiq_comp_set":
            warnings.append({"severity": "low",
                             "text": "Comp set is S&P Capital IQ's official peer list (not yet analyst-reviewed) - "
                                     "approve it on the Peer Benchmarking page to sign off."})
        elif a.peer_source == "fallback":
            warnings.append({"severity": "low",
                             "text": "Comp set is the CapIQ-attribute scored set (not yet analyst-reviewed) - "
                                     "approve or edit it on the Peer Benchmarking page."})
        else:
            warnings.append({"severity": "medium",
                             "text": f"Comp set is the {a.peer_source.replace('_', ' ')} (not analyst-reviewed) - "
                                     f"approve a peer set on the Peer Benchmarking page to firm up the exit multiple."})
    if warnings:
        flags = [{"severity": w["severity"].title(), "area": "Model quality",
                  "observation": w["text"], "management_question": ""} for w in warnings]
        ui.section("Model-Quality Warnings", "Read these before trusting the target")
        ui.flag_list(flags)

    # --- Row 1: scenario targets | sensitivity heatmap --------------------------------
    ui.section("Valuation Range", "Where the DCF, comps, and history place the share price")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.scenario_target_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.sensitivity_heatmap(case), use_container_width=True, config=PLOTLY_CONFIG)

    c3, c4 = st.columns(2, gap="medium")
    with c3:
        st.plotly_chart(vch.tornado_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c4:
        st.plotly_chart(vch.implied_growth_heatmap(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 2: football field (full width) ---------------------------------------------
    _vh = store.valuation_history
    _own_hist = _vh[_vh["company_id"] == company_id] if (_vh is not None and not _vh.empty) else None
    st.plotly_chart(vch.football_field_chart(case, price_history=_own_hist),
                    use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 3: forecast | FCF bridge ----------------------------------------------------
    ui.section("From Assumptions to Cash Flow")
    pick = st.radio("Scenario", ["base", "bear", "bull"], horizontal=True, label_visibility="collapsed")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.forecast_chart(case, pick), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.fcf_bridge_chart(case, pick), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 4: equity bridge + current EV bridge ------------------------------------------
    from src.modeling.capital_structure import ev_bridge as _ev_bridge

    ui.section("Valuation Mechanics")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.equity_bridge_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        bridge = _ev_bridge(row)
        st.plotly_chart(vch.current_ev_bridge_chart(bridge), use_container_width=True, config=PLOTLY_CONFIG)
        if bridge.get("mismatch"):
            ui.footnote(f"Calculated EV vs reported CapIQ TEV: {bridge['gap']:+.0%} gap - "
                        f"leases/pensions/share-count detail not fully exported.")

    # --- Row 5: WACC | terminal value ------------------------------------------------------
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(vch.wacc_build_chart(case), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(vch.terminal_value_chart(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 6: PE lens - LBO returns -------------------------------------------------------
    from src.modeling.lbo import lbo_from_case

    ui.section("PE Lens - LBO Returns",
               "Levered IRR/MOIC on the same operating forecast | entry is negotiated, not the screen price")
    row_lbo = case.assessment.row
    own_mult = row_lbo.get("ev_to_ebitda_ttm")
    default_entry = float(own_mult) if pd.notna(own_mult) and own_mult > 0 else float(case.exit_multiple)
    kd_default = float(case.wacc.cost_of_debt_pretax or 0.08)
    lc1, lc2, lc3, lc4 = st.columns(4)
    with lc1:
        entry_m = st.number_input("Entry EV/EBITDA (x)", min_value=2.0, max_value=40.0,
                                  value=round(default_entry, 1), step=0.5)
    with lc2:
        exit_m = st.number_input("Exit EV/EBITDA (x)", min_value=2.0, max_value=40.0,
                                 value=round(default_entry, 1), step=0.5)
    with lc3:
        debt_pct = st.slider("Debt at entry (% of EV)", 0, 80, 50, 5) / 100.0
    with lc4:
        kd_in = st.number_input("Pre-tax cost of debt (%)", min_value=1.0, max_value=25.0,
                                value=round(kd_default * 100, 1), step=0.5) / 100.0

    lbo = lbo_from_case(case, entry_multiple=entry_m, exit_multiple=exit_m,
                        debt_pct=debt_pct, cost_of_debt=kd_in)
    if lbo.valid:
        moic_tone = "green" if (lbo.moic or 0) >= 2.0 else ("yellow" if (lbo.moic or 0) >= 1.5 else "red")
        exit_lev = (lbo.exit_debt / lbo.exit_ebitda) if lbo.exit_ebitda > 0 else None
        ui.kpi_grid([
            Kpi("chk", "Equity Check", f"{lbo.equity_check:,.0f}",
                f"{(1 - lbo.debt_pct):.0%} of EV + fees", "n/a"),
            Kpi("moic", "MOIC", f"{lbo.moic:.2f}x" if lbo.moic else "n/a",
                f"{lbo.horizon}-year hold", moic_tone),
            Kpi("irr", "Sponsor IRR", f"{lbo.irr:.1%}" if lbo.irr is not None else "n/a",
                "no interim distributions", moic_tone),
            Kpi("lev", "Entry -> Exit Leverage",
                f"{(lbo.entry_debt / lbo.entry_ebitda):.1f}x -> {exit_lev:.1f}x" if exit_lev is not None else "n/a",
                "debt / EBITDA", "n/a"),
            Kpi("xeq", "Exit Equity", f"{lbo.exit_equity:,.0f}",
                f"exit EV {lbo.exit_ev:,.0f} - debt {lbo.exit_debt:,.0f}", "n/a"),
        ], columns=5)
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(vch.value_creation_bridge_chart(lbo), use_container_width=True, config=PLOTLY_CONFIG)
        with c2:
            st.plotly_chart(vch.debt_paydown_chart(lbo), use_container_width=True, config=PLOTLY_CONFIG)
        for note in lbo.notes:
            ui.footnote(note)
        ui.footnote("Simple-LBO conventions: 100% cash sweep, no interim dividends, fees 2% of EV, "
                    "UFCF as pre-interest free cash flow. Base-scenario forecast; flex the assumptions "
                    "file for segment-driven builds.")
    else:
        st.info(lbo.notes[0] if lbo.notes else "LBO not applicable for this name.")
        if tv_note:
            ui.footnote(tv_note)

    # --- Row 6: peer quartiles (full width) --------------------------------------------------
    ui.section("Market Context")
    st.plotly_chart(vch.peer_quartile_panels(case), use_container_width=True, config=PLOTLY_CONFIG)

    # --- Row 7: revisions | working capital ---------------------------------------------------
    rev_fig = vch.revision_momentum_chart(case)
    wc_fig = vch.working_capital_chart(df, case)
    if rev_fig is not None or wc_fig is not None:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            if rev_fig is not None:
                st.plotly_chart(rev_fig, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                ui.footnote("Estimate revisions not populated for this name.")
        with c2:
            if wc_fig is not None:
                st.plotly_chart(wc_fig, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                ui.footnote("Working-capital days not populated for this name.")

    # --- Provenance --------------------------------------------------------------------------
    ui.section("Assumptions Provenance", "Every input classified - no black box")
    prov = vch.assumptions_provenance(case)
    pill = {"analyst": ("Analyst", "yellow"), "anchored": ("Anchored TTM", "green"), "default": ("Default", "red")}
    rows = [[r["item"], r["value"], ui.cell_pill(*pill.get(r["source"], (r["source"], "na")))]
            for _, r in prov.iterrows()]
    ui.html_table(["Input", "Value", "Source"], rows, numeric_from=99)
    ui.footnote("Analyst = set in the assumptions YAML. Anchored = derived from the company's own TTM data "
                "or the peer group. Default = generic fallback pending better data - treat with caution."
                + (f" File: <code>{Path(str(case.assumptions.path)).name}</code>" if case.assumptions.from_file else ""))

    # --- Detail tables (kept, collapsed) --------------------------------------------------------
    with st.expander("Forecast, WACC, and terminal value detail tables"):
        res = case.scenarios[pick]
        f = res.forecast
        headers = ["Line"] + [f"Y{int(y)}" for y in f["year"]]
        rows = [
            ["Revenue"] + [fmt_money(v, currency) for v in f["revenue"]],
            ["  growth"] + [f"{v:+.1%}" for v in f["revenue_growth"]],
            ["EBITDA"] + [fmt_money(v, currency) for v in f["ebitda"]],
            ["  margin"] + [f"{v:.1%}" for v in f["ebitda_margin"]],
            ["NOPAT"] + [fmt_money(v, currency) for v in f["nopat"]],
            ["Capex"] + [fmt_money(v, currency) for v in f["capex"]],
            ["Change in NWC"] + [fmt_money(v, currency) for v in f["delta_nwc"]],
            ["UFCF"] + [fmt_money(v, currency) for v in f["ufcf"]],
        ]
        ui.html_table(headers, rows)
        w = case.wacc
        if w.notes:
            ui.footnote(" | ".join(w.notes))

    # --- Export -----------------------------------------------------------------------------------
    ui.section("Export")
    with st.spinner("Rendering valuation case (with charts)..."):
        path = generate_valuation_case(demo=DEMO_MODE, company_id=company_id)
    st.download_button("Download Valuation Case (HTML)", data=Path(path).read_bytes(),
                       file_name=Path(path).name, mime="text/html", use_container_width=False)
    ui.footnote(f"Written to <code>{Path(path).parent.name}/</code>"
                + (" - private outputs never enter version control." if not DEMO_MODE else "."))


def page_valuation_expectations(df: pd.DataFrame, company_id: str) -> None:
    from src.modeling.comps import comps_spread
    from src.modeling.multiples import (
        MULTIPLE_SPECS,
        multiple_history,
        multiple_momentum,
        multiples_summary,
        valuation_commentary,
    )
    from src.reporting import multiples_charts as mch

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    val = a.valuation
    financial = a.business_model == "financial"
    ui.header_band(row, DEMO_MODE)

    ui.section("Valuation Snapshot", "Multiples vs the peer-group median and vs the company's own history")
    hc = a.history_context
    cards = [
        Kpi("mc", "Market Cap", fmt_money(row.get("market_cap"), currency), "Equity value"),
        Kpi("ev", "Enterprise Value", fmt_money(row.get("enterprise_value"), currency), "EV = mkt cap + net debt"),
        Kpi("mult", val["multiple_name"], val["pe"] if financial else val["ev_to_ebitda"],
            f"vs {val['pe_median'] if financial else val['ev_to_ebitda_median']} peer median",
            row.get(("pe_ttm" if financial else "ev_to_ebitda_ttm") + "_signal", "n/a"),
            delta=(f"{val['premium_label']} vs peers" if val.get("premium") is not None else None),
            delta_dir=("up" if (val.get("premium") or 0) > 0 else "down")),
        Kpi("hist", "vs Own History", fmt_ordinal(hc.get("percentile")) + " pctile" if hc.get("available") else "n/a",
            (f"z {hc.get('z_score'):+.1f} · median {fmt_multiple(hc.get('median'))}" if hc.get("available")
             else "history not populated"), "n/a"),
        Kpi("revs", "Estimate Momentum", a.revisions.get("direction", "n/a").title(),
            (f"NTM rev {fmt_signed_pct(a.revisions.get('revenue_30d'))} / 30d"
             if a.revisions.get("revenue_30d") is not None else "consensus not populated"),
            {"cutting": "red", "raising": "green"}.get(a.revisions.get("direction"), "n/a")),
    ]
    ui.kpi_grid(cards, columns=5)

    # --- Multi-multiple framework -------------------------------------------------
    spread = comps_spread(a.peers, store.estimates)
    summary = multiples_summary(row, spread, company_id, store.valuation_history)
    ui.section("Multi-Multiple Scorecard",
               "Which multiple matters for this business model, and what each one says")
    ui.multiple_scorecard(summary)
    m1, m2 = st.columns([1.05, 1.0], gap="medium")
    with m1:
        ui.business_model_map(summary, a.business_model)
    with m2:
        hist_metrics = [m for m, s in MULTIPLE_SPECS.items() if s["hist_col"]]
        peer_ids = list(a.peers["company_id"])
        momentum = {m: multiple_momentum(store.valuation_history, company_id, peer_ids,
                                         MULTIPLE_SPECS[m]["hist_col"]) for m in hist_metrics}
        notes = valuation_commentary(summary, momentum, row)
        if notes:
            ui.bullet_list("Valuation Read-Out", notes, "q")

    ui.section("Historical Multiples", "Company vs peer median | is the multiple high vs its own range?")
    label_by_metric = {m: MULTIPLE_SPECS[m]["label"] for m in hist_metrics}
    pick_hist = st.radio("Multiple", [label_by_metric[m] for m in hist_metrics],
                         horizontal=True, label_visibility="collapsed", key="hist_multiple")
    metric_pick = next(m for m in hist_metrics if label_by_metric[m] == pick_hist)
    hist = multiple_history(store.valuation_history, company_id, peer_ids,
                            MULTIPLE_SPECS[metric_pick]["hist_col"])
    st.plotly_chart(mch.multiple_history_chart(hist, pick_hist),
                    use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Multiple Momentum", "Re-rating, de-rating, or moving with the sector?")
    # Approximate price decomposition through the primary multiple lens.
    primary_hist = next((m["metric"] for m in summary
                         if m["role"] == "primary" and MULTIPLE_SPECS[m["metric"]]["hist_col"]
                         and m["interpretation"] != "not meaningful"), None)
    decomp = mch.rerating_decomposition(store.valuation_history, company_id,
                                        MULTIPLE_SPECS[primary_hist]["hist_col"]) \
        if primary_hist else {"available": False}
    h1, h2 = st.columns([1.0, 1.15], gap="medium")
    with h1:
        st.plotly_chart(mch.momentum_heatmap(momentum), use_container_width=True, config=PLOTLY_CONFIG)
    with h2:
        if decomp.get("available"):
            st.plotly_chart(mch.rerating_bridge_chart(decomp, MULTIPLE_SPECS[primary_hist]["label"]),
                            use_container_width=True, config=PLOTLY_CONFIG)

    by_metric = {m["metric"]: m for m in summary}
    _short = {"re-rating - company-specific": "re-rating (company-specific)",
              "de-rating - company-specific": "de-rating (company-specific)",
              "re-rating - sector-driven": "re-rating (sector-driven)",
              "de-rating - sector-driven": "de-rating (sector-driven)",
              "insufficient history": "short history"}
    mrows = []
    for metric in hist_metrics:
        mom = momentum[metric]
        if not mom.get("available"):
            continue
        fmt_chg = lambda v: f"{v:+.0%}" if v is not None else "n/a"
        verdict = mom.get("verdict") or "n/a"
        sm = by_metric.get(metric, {})
        mrows.append([
            MULTIPLE_SPECS[metric]["label"],
            f"{mom['current']:.1f}x",
            fmt_chg(mom["chg"].get(3)), fmt_chg(mom["chg"].get(6)), fmt_chg(mom["chg"].get(12)),
            f"P{mom['percentile'] * 100:.0f}" if mom.get("percentile") is not None else "n/a",
            fmt_chg(sm.get("premium")),
            _short.get(verdict, verdict),
        ])
    if mrows:
        ui.html_table(["Multiple", "Current", "3M", "6M", "12M", "Own pctile",
                       "vs peers", "Read"], mrows, numeric_from=1)
        ui.footnote("Monthly closes from the valuation-history export (its LTM multiples can "
                    "differ slightly from the dataset's TTM computation). Own pctile = current vs "
                    "own history; 'vs peers' = premium/discount to the adjusted peer median today; "
                    "Read compares the company's 12m multiple move with the peer median's move.")
    else:
        ui.footnote("Momentum requires populated valuation history.")

    ui.section("Valuation in Context")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(valuation_chart(df, None, company_id), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(peer_valuation_scatter(df, None, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    # Scenario engine.
    thesis_scen = a.thesis.scenarios if a.thesis else None
    results = run_cases(row, thesis_scen)
    ui.section("Scenarios & Sponsor-Style Returns",
               "Exit value = exit-year profit × exit multiple; IRR vs today's market cap")
    srows = []
    for res in results:
        srows.append([
            res.case.name.title(),
            fmt_signed_pct(res.case.revenue_cagr),
            fmt_pct(res.case.exit_margin),
            f"{res.case.exit_multiple:g}x",
            f"{res.moic:.2f}x" if res.valid else "n/a",
            _tone(f"{res.irr:+.1%}", res.irr >= 0) if res.valid else "n/a",
            res.case.source,
        ])
    ui.html_table(["Case", "Rev CAGR", "Exit Margin", "Exit Multiple", "MOIC", f"IRR ({results[0].case.horizon_years}y)", "Source"], srows)

    base_case = cases_from_thesis(row, thesis_scen)[1]
    grid = sensitivity_grid(row, base_case)
    grid_rows = [[idx] + [("n/a" if pd.isna(v) else _tone(f"{v:+.0%}", v >= 0)) for v in grid.loc[idx]]
                 for idx in grid.index]
    g1, g2 = st.columns([1.15, 1.0], gap="medium")
    with g1:
        ui.section("IRR Sensitivity", "Revenue CAGR (rows) × exit multiple (columns), base-case margin held")
        ui.html_table(["Rev CAGR \\ Exit"] + list(grid.columns), grid_rows)
    with g2:
        fair_mult = a.peer_median.get("pe_ttm") if financial else a.peer_median.get("ev_to_ebitda_ttm")
        ie = implied_expectations(row, fair_mult)
        ui.section("What Is Priced In", f"Exit at peer-median {ie['multiple_name']}")
        if ie["available"]:
            items = [
                f"To earn {r['return']:.0%} a year, {ie['metric']} must compound at {r['implied_profit_cagr']:+.1%} for {ie['horizon_years']} years."
                for r in ie["required"]
            ]
            ui.bullet_list("Implied Expectations", items, "q")
        else:
            ui.footnote("Insufficient data (needs positive current profit, value, and a peer-median multiple).")
        st.write("")
        ui.memo("Valuation Commentary", val.get("commentary", ""))

    ui.footnote("Scenario model: today's net debt held constant, interim FCF ignored (conservative for cash generators); "
                "financial institutions run on net income × P/E instead of EBITDA × EV/EBITDA.")


def page_peer_benchmarking(df: pd.DataFrame, company_id: str) -> None:
    from src.branding import PALETTE
    from src.modeling.peer_sets import (
        MIN_VALID_PEERS,
        WEIGHTS,
        log_suggestions,
        rejected_suggestions,
        save_peer_set,
        suggest_peers,
    )

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    ui.header_band(row, DEMO_MODE)

    # --- Peer provenance ---------------------------------------------------------
    source_labels = {
        "capiq_comp_set": ("Capital IQ comp set", "green"),
        "manual": ("Analyst-approved set", "green"),
        "fallback": ("Scored comps (approved)", "green") if a.peer_reviewed
                    else ("Scored comps (generated, unreviewed)", "yellow"),
        "peer_group": ("Static peer-group mapping (unreviewed)", "yellow"),
        "universe": ("FULL UNIVERSE fallback", "red"),
    }
    src_label, src_tone = source_labels.get(a.peer_source, (a.peer_source, "na"))
    n_peers = max(len(a.peers) - 1, 0)
    st.markdown(
        f'<div style="margin:4px 0 2px">'
        f'{ui.cell_pill(src_label, src_tone)} &nbsp;'
        f'{ui.cell_pill("Reviewed" if a.peer_reviewed else "Not reviewed", "green" if a.peer_reviewed else "yellow")} &nbsp;'
        f'<span class="pe-foot">{n_peers} peers | set: {a.peer_set_name}</span></div>',
        unsafe_allow_html=True,
    )
    if a.peer_warning:
        st.warning(a.peer_warning)

    # --- Review actions for THIS company's set -------------------------------------
    from src.modeling.peer_sets import (
        approve_peer_set,
        get_approved_peer_set,
        reject_peers,
        reset_to_generated,
    )

    current_set = get_approved_peer_set(company_id)
    rc1, rc2, rc3 = st.columns([1.4, 1.4, 1.0])
    with rc1:
        note = st.text_input("Reviewer note", value=current_set.get("reviewer_note", "") if current_set else "",
                             placeholder="e.g. checked vs 10-K competitors list")
        if st.button("Mark set analyst-approved", type="primary", disabled=current_set is None):
            approve_peer_set(company_id, reviewer_note=note)
            st.success("Peer set marked analyst-approved.")
            st.rerun()
    with rc2:
        member_ids = current_set["members"] if current_set else []
        member_labels = {m: str(m).split(":")[-1] for m in member_ids}
        to_reject = st.multiselect("Reject members", list(member_labels.keys()),
                                   format_func=lambda m: member_labels[m])
        if st.button("Reject selected", disabled=not to_reject):
            reject_peers(company_id, to_reject)
            st.success(f"Rejected {len(to_reject)} member(s) - kept in file for audit, "
                       f"excluded from analytics.")
            st.rerun()
    with rc3:
        if current_set and current_set.get("rejected"):
            ui.footnote("Rejected: " + ", ".join(str(x).split(":")[-1]
                                                 for x in current_set["rejected"]))
        if st.button("Reset to generated"):
            reset_to_generated(company_id, latest_rows(df))
            st.info("Set reset to the scored suggestion (unreviewed).")
            st.rerun()

    # --- Review queue across the universe -------------------------------------------
    with st.expander("Peer review queue - status of every name"):
        latest_all_q = latest_rows(df)
        qrows = []
        for _, r in latest_all_q.sort_values("ticker").iterrows():
            cid = r["company_id"]
            s = get_approved_peer_set(cid)
            if s:
                src, reviewed = str(s["source"]), s["reviewed"]
                n_peers = len(s["members"])
                reviewed_at = s.get("reviewed_at") or "-"
            else:
                src, reviewed, n_peers, reviewed_at = "peer_group/universe", False, 0, "-"
            warns = []
            if not s:
                warns.append("fallback only")
            if s and n_peers < 3:
                warns.append("fewer than 3 peers")
            if s and not reviewed:
                warns.append("unreviewed")
            qrows.append([
                str(r.get("ticker", "")).replace(".SA", ""),
                str(r.get("company_name", ""))[:24],
                str(r.get("peer_group", ""))[:24],
                src.replace("_", " "),
                str(n_peers),
                ui.cell_pill("REVIEWED", "green") if reviewed else ui.cell_pill("UNREVIEWED", "yellow"),
                str(reviewed_at)[:10],
                ", ".join(warns) or "-",
            ])
        ui.html_table(["Ticker", "Company", "Peer group", "Source", "# Peers",
                       "Status", "Reviewed", "Warnings"], qrows, numeric_from=99)
        n_rev = sum(1 for q in qrows if "REVIEWED</" in q[5] or "REVIEWED" in q[5] and "UNREVIEWED" not in q[5])
        ui.footnote(f"{n_rev} of {len(qrows)} names analyst-approved. Approval is always an "
                    f"explicit action - generated and official CapIQ sets stay flagged until you sign off.")

    # --- Peer set editor -----------------------------------------------------------
    with st.expander("Peer set editor - suggest, approve, save"):
        latest_all = latest_rows(df)
        if st.button("Suggest peers (scored on CapIQ attributes)"):
            st.session_state["peer_suggestions"] = suggest_peers(latest_all, company_id)
        sugg = st.session_state.get("peer_suggestions")
        if sugg is not None and not sugg.empty:
            options = {
                f"{r['ticker']} | {str(r['company_name'])[:24]} | score {r['score']:.0f} | {r['reasons']}": r["company_id"]
                for _, r in sugg.iterrows()
            }
            default = [k for k, cid in options.items()
                       if sugg.set_index("company_id").loc[cid, "score"] >= 40][:8]
            picked = st.multiselect("Approve suggested peers", list(options.keys()), default=default)
            approved_ids = [options[p] for p in picked]

            others = latest_all[~latest_all["company_id"].isin(approved_ids + [company_id])]
            manual_options = {
                f"{str(r.ticker).replace('.SA','')} | {r.company_name}": r.company_id
                for r in others.itertuples()
            }
            manual_picked = st.multiselect("Add peers manually (from the exported universe)",
                                           list(manual_options.keys()))
            approved_ids += [manual_options[p] for p in manual_picked]

            set_name = st.text_input("Peer set name", value=f"{str(row.get('ticker','')).replace('.SA','')} comps")
            small_ok = st.checkbox(f"Override: allow fewer than {MIN_VALID_PEERS} peers (results directional)")
            if st.button("Save approved peer set", type="primary",
                         disabled=len(approved_ids) < MIN_VALID_PEERS and not small_ok):
                try:
                    members = []
                    for cid in approved_ids:
                        srow = sugg[sugg["company_id"] == cid]
                        members.append({
                            "company_id": cid,
                            "score": float(srow["score"].iloc[0]) if not srow.empty else None,
                            "rationale": srow["reasons"].iloc[0] if not srow.empty else "manual add",
                        })
                    save_peer_set(company_id, set_name, members,
                                  source="fallback" if picked else "manual",
                                  allow_small=small_ok)
                    log_suggestions(company_id, sugg, approved_ids)
                    st.success("Peer set saved. Benchmarks, percentiles, and the valuation case now use it.")
                    st.session_state.pop("peer_suggestions", None)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        rej = rejected_suggestions(company_id)
        if not rej.empty:
            ui.footnote("Previously rejected suggestions: " +
                        ", ".join(str(x).split(":")[-1] for x in rej["suggested_company_id"].head(10)))
        ui.footnote("Drop a Capital IQ Pro comp-set export at "
                    f"<code>data_private/capiq_exports/comp_sets/{company_id.replace(':', '_')}.csv</code> "
                    "(company_id or ticker column) to import it as the top-priority source.")

    expansion_path = _ROOT / "data_private" / "capiq_exports" / "peer_expansion_candidates.csv"
    if expansion_path.exists():
        with st.expander("Universe expansion candidates (from official CapIQ peer lists)"):
            exp = pd.read_csv(expansion_path)
            st.markdown(
                "Names S&P lists as peers of your watchlist companies but that are "
                "not in the universe yet - ranked by how many of your anchors "
                "reference them. Add the top ones via **Data & Refresh -> Add Company** "
                "to make the official comp sets usable end-to-end."
            )
            ui.html_table(["CapIQ ticker", "Company", "Referenced by (# anchors)"],
                          [[str(r.capiq_ticker), str(r.name), str(int(r.referenced_by))]
                           for r in exp.head(15).itertuples()], numeric_from=2)

    with st.expander("Peer methodology"):
        st.markdown(
            "**Hierarchy:** 1) Capital IQ comp-set import (analyst-approved) -> 2) scored comp sets "
            "(analyst-approved, or batch-generated and labeled *not reviewed* until approved) -> "
            "3) static peer-group mapping -> 4) full universe (flagged).\n\n"
            "**Suggestion scoring (0-100):** " +
            ", ".join(f"{k.replace('_', ' ')} {v}pts" for k, v in WEIGHTS.items()) +
            "; cross-business-model candidates are penalized 20pts. Size uses log market-cap proximity "
            "(USD-normalized); margin/growth use absolute proximity bands. Candidates are limited to the "
            "exported universe - add outside names via Data & Refresh first."
        )

    ui.section("Peer Universe", f"{a.peer_set_name} | {src_label.lower()}")
    peers = a.peers.sort_values("ev_to_ebitda_ttm")
    headers = ["Ticker", "Company", "Growth", "EBITDA mgn", "FCF conv", "ND/EBITDA", "EV/Rev", "EV/EBITDA", "As Of"]
    rows, classes = [], []
    for _, p in peers.iterrows():
        g = p.get("revenue_yoy_growth")
        rows.append([
            p["ticker"].replace(".SA", ""),
            str(p.get("company_name", ""))[:26],
            _tone(fmt_pct(g), (g > 0) if pd.notna(g) else None),
            fmt_pct(p.get("ebitda_margin_ttm")),
            fmt_pct(p.get("fcf_conversion_ttm")),
            fmt_multiple(p.get("net_debt_to_ebitda_ttm")),
            fmt_multiple(p.get("ev_to_revenue_ttm")),
            ui.cell_pill(fmt_multiple(p.get("ev_to_ebitda_ttm")), p.get("ev_to_ebitda_ttm_signal", "n/a")),
            ui.quarter_label(p["period"]),
        ])
        classes.append("anchor" if p["company_id"] == company_id else "")
    med = a.peer_median
    rows.append([
        "--", "Peer median",
        fmt_pct(med.get("revenue_yoy_growth")),
        fmt_pct(med.get("ebitda_margin_ttm")),
        fmt_pct(med.get("fcf_conversion_ttm")),
        fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
        fmt_multiple(med.get("ev_to_revenue_ttm")),
        fmt_multiple(med.get("ev_to_ebitda_ttm")),
        "",
    ])
    classes.append("median")
    ui.html_table(headers, rows, classes)
    ui.footnote("Per-name as-of dates differ because fiscal year ends differ; medians mix the latest reported quarter of each peer.")

    # --- IB-style valuation spread ------------------------------------------------
    from src.modeling.comps import comps_spread, quartile_stats
    from src.reporting import multiples_charts as mch

    spread = comps_spread(a.peers, store.estimates)
    stats = quartile_stats(spread)
    ui.section("Valuation Spread", "LTM and NTM multiples per peer | N/M = negative base, never in a median")

    spread_cols = [("ev_to_revenue_ttm", "EV/Rev LTM"), ("ev_to_revenue_ntm", "EV/Rev NTM"),
                   ("ev_to_ebitda_ttm", "EV/EBITDA LTM"), ("ev_to_ebitda_ntm", "EV/EBITDA NTM"),
                   ("pe_ttm", "P/E LTM"), ("pe_ntm", "P/E NTM"), ("p_tbv", "P/TBV")]
    from src.modeling.outliers import multiple_outlier_reason as _outlier_reason

    def _mult_cell(metric: str, v) -> str:
        if v is None or pd.isna(v) or v <= 0:
            return "<span style='color:var(--muted-2)'>n/m</span>"
        reason = _outlier_reason(metric, float(v))
        cell = f"{v:.1f}x"
        return f"{cell} <span style='color:var(--copper)'>*</span>" if reason else cell

    vrows, vclasses = [], []
    for _, p in spread.sort_values("ev_to_ebitda_ttm", na_position="last").iterrows():
        vrows.append([str(p.get("ticker", "")).replace(".SA", "")]
                     + [_mult_cell(mcol, p.get(mcol)) for mcol, _ in spread_cols])
        vclasses.append("anchor" if p.get("company_id") == company_id else "")
    for stat, slabel in [("mean", "Mean"), ("median", "Median"), ("q1", "25th pct"),
                         ("q3", "75th pct"), ("high", "High"), ("low", "Low"),
                         ("adjusted_median", "Median ex-outliers")]:
        srow = [slabel]
        for mcol, _ in spread_cols:
            v = stats.loc[mcol, stat] if mcol in stats.index else float("nan")
            srow.append(f"{v:.1f}x" if pd.notna(v) else "n/a")
        vrows.append(srow)
        vclasses.append("median")
    ui.html_table(["Ticker"] + [lbl for _, lbl in spread_cols], vrows, vclasses, numeric_from=1)
    excl_notes = []
    for mcol, lbl in spread_cols:
        if mcol in stats.index and stats.loc[mcol, "n_excluded"]:
            names = ", ".join(t for t, _ in stats.loc[mcol, "excluded"][:4])
            excl_notes.append(f"{lbl}: {names}")
    ui.footnote("* flagged outlier (extreme multiple), excluded from the ex-outlier median. "
                + ("Excluded - " + " | ".join(excl_notes) if excl_notes else "No outliers flagged.")
                + " Negative EBITDA/earnings/tangible book show n/m and never enter medians.")

    dist_metrics = ["ev_to_revenue_ttm", "ev_to_ebitda_ttm", "pe_ttm"]
    if a.business_model == "financial":
        dist_metrics.append("p_tbv")
    st.plotly_chart(mch.peer_distribution_panels(spread, dist_metrics, company_id),
                    use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Is the Multiple Earned?", "Valuation against the fundamental that should drive it")
    s1, s2 = st.columns(2, gap="medium")
    with s1:
        st.plotly_chart(mch.fundamental_vs_multiple_scatter(
            spread, company_id, "revenue_yoy_growth", "ev_to_revenue_ttm",
            "Revenue growth (YoY)", "EV / Revenue",
            "Growth vs EV/Revenue", "Growth should command the revenue multiple"),
            use_container_width=True, config=PLOTLY_CONFIG)
    with s2:
        st.plotly_chart(mch.fundamental_vs_multiple_scatter(
            spread, company_id, "ebitda_margin_ttm", "ev_to_ebitda_ttm",
            "EBITDA margin (TTM)", "EV / EBITDA",
            "Margin vs EV/EBITDA", "Margin quality should support the EBITDA multiple"),
            use_container_width=True, config=PLOTLY_CONFIG)
    s3, s4 = st.columns(2, gap="medium")
    roe_spread = a.peers[["company_id", "ticker", "roe_ttm", "pe_ttm", "p_tbv"]].copy() \
        if "roe_ttm" in a.peers.columns else pd.DataFrame()
    with s3:
        if not roe_spread.empty:
            st.plotly_chart(mch.fundamental_vs_multiple_scatter(
                roe_spread, company_id, "roe_ttm", "pe_ttm",
                "ROE (TTM)", "P / E",
                "ROE vs P/E", "Return on equity should earn the earnings multiple"),
                use_container_width=True, config=PLOTLY_CONFIG)
    with s4:
        if not roe_spread.empty and a.business_model == "financial":
            st.plotly_chart(mch.fundamental_vs_multiple_scatter(
                roe_spread, company_id, "roe_ttm", "p_tbv",
                "ROE (TTM)", "P / TBV",
                "ROE vs P/TBV", "The justified-P/B logic: higher ROE earns a book premium"),
                use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Positioning", "Where the anchor sits on growth, margin, and the multiple it commands")
    peer_ids = list(a.peers["company_id"])
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(peer_scatter(df, None, company_id, peer_ids=peer_ids), use_container_width=True, config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(peer_valuation_scatter(df, None, company_id, peer_ids=peer_ids), use_container_width=True, config=PLOTLY_CONFIG)

    st.plotly_chart(valuation_chart(df, None, company_id, peer_ids=peer_ids), use_container_width=True, config=PLOTLY_CONFIG)
    ui.memo("Is the Multiple Earned?", a.valuation.get("commentary", ""))


def page_compare(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    latest = latest_rows(df)
    labels = {
        f"{r.ticker.replace('.SA', '')} | {r.company_name}": r.company_id
        for r in latest.sort_values("ticker").itertuples()
    }
    default_label = next((k for k, v in labels.items() if v == company_id), list(labels.keys())[0])

    st.markdown(
        f"""
        <div class="pe-header">
          <div class="pe-header-top">
            <div>
              <div class="kicker">Investment Watchlist | Side-by-Side</div>
              <h1>Compare</h1>
            </div>
            <span class="pe-mode-pill {'pe-mode-demo' if DEMO_MODE else 'pe-mode-private'}">
              {'Public Demo Data' if DEMO_MODE else 'Capital IQ - Private'}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    picks = st.multiselect("Companies (2–4)", list(labels.keys()), default=[default_label], max_selections=4)
    if len(picks) < 2:
        ui.footnote("Pick at least two names to compare.")
        return

    assessments = [build_assessment(df, labels[p], store=store) for p in picks]

    def metric_row(label, getter, formatter=lambda v: v):
        return [label] + [formatter(getter(a)) for a in assessments]

    headers = ["Metric"] + [a.row["ticker"].replace(".SA", "") for a in assessments]
    rows = [
        metric_row("Verdict", lambda a: _verdict_pill(a.verdict_key, a.verdict_label)),
        metric_row("Attention score", lambda a: f"{a.attention_score:.0f}"),
        metric_row("Peer group", lambda a: str(a.peer_group)[:28]),
        metric_row("Thesis stage", lambda a: a.thesis.stage_label if (a.thesis and a.thesis.exists) else "—"),
        metric_row("Revenue (TTM)", lambda a: fmt_money(a.row.get("revenue_ttm"), a.row.get("currency", "USD"))),
        metric_row("Revenue YoY", lambda a: fmt_signed_pct(a.row.get("revenue_yoy_growth"))),
        metric_row("Profitability (TTM)", lambda a: fmt_pct(a.row.get(
            "net_income_margin_ttm" if a.business_model == "financial" else "ebitda_margin_ttm"))),
        metric_row("FCF conversion", lambda a: fmt_pct(a.row.get("fcf_conversion_ttm"))),
        metric_row("ROIC / ROE", lambda a: fmt_pct(a.row.get("roe_ttm" if a.business_model == "financial" else "roic_ttm"))),
        metric_row("Net debt / EBITDA", lambda a: fmt_multiple(a.row.get("net_debt_to_ebitda_ttm"))),
        metric_row("Multiple", lambda a: f"{fmt_multiple(a.row.get('pe_ttm' if a.business_model == 'financial' else 'ev_to_ebitda_ttm'))} {a.valuation.get('multiple_name')}"),
        metric_row("vs peer median", lambda a: a.valuation.get("premium_label", "n/a")),
        metric_row("vs own history", lambda a: fmt_ordinal(a.history_context.get("percentile")) + " pctile"
                   if a.history_context.get("available") else "n/a"),
        metric_row("Estimate momentum", lambda a: a.revisions.get("direction", "n/a").title()),
        metric_row("Open flags", lambda a: str(sum(1 for f in a.red_flags if f.get("severity") in {"High", "Medium"}))),
        metric_row("As of", lambda a: ui.quarter_label(a.row["period"])),
    ]
    ui.section("Side-by-Side")
    ui.html_table(headers, rows, numeric_from=1)

    ui.section("Verdict Rationale")
    for a in assessments:
        ui.memo(a.row["ticker"].replace(".SA", ""), a.verdict_rationale)


def page_ic_memo(df: pd.DataFrame, company_id: str) -> None:
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
    out_dir = Path(memo_path).parent
    ui.footnote(f"Written to <code>{out_dir}</code>"
                + (" — private outputs never enter version control." if not DEMO_MODE else "."))

    with st.expander("Preview IC memo", expanded=True):
        components.html(Path(memo_path).read_text(encoding="utf-8"), height=900, scrolling=True)


def page_data_refresh(df: pd.DataFrame, company_id: str) -> None:
    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    ui.header_band(row, DEMO_MODE)

    latest = latest_rows(df)
    dataset_path = _dataset_path(DEMO_MODE)
    refreshed = pd.Timestamp(dataset_path.stat().st_mtime, unit="s").strftime("%d %b %Y %H:%M")
    mode = "Public Demo" if DEMO_MODE else "Capital IQ - Private"

    ui.section("Data Governance", "Mode, freshness, and side-table population")
    cards = [
        Kpi("m", "Data Mode", mode, "Source environment", "green" if not DEMO_MODE else "yellow"),
        Kpi("r", "Dataset", f"{len(df):,} rows", f"{latest.shape[0]} companies · rebuilt {refreshed}"),
        Kpi("v", "Valuation History",
            f"{len(store.valuation_history):,} rows" if store.has_valuation_history else "Not populated",
            "Powers multiple-vs-history percentiles",
            "green" if store.has_valuation_history else "red"),
        Kpi("e", "Consensus Estimates",
            f"{len(store.estimates):,} rows" if store.has_estimates else "Not populated",
            "Powers revisions & beats/misses",
            "green" if store.has_estimates else "red"),
        Kpi("q", "Avg Completeness", fmt_pct(latest["data_quality_score"].mean()), "Required fields populated",
            "green" if latest["data_quality_score"].mean() >= 0.9 else "yellow"),
    ]
    ui.kpi_grid(cards, columns=5)
    ui.footnote(f"Dataset path: <code>{dataset_path}</code>")

    if not DEMO_MODE:
        ui.section("CapIQ Refresh Log")
        if not store.refresh_log.empty:
            log = store.refresh_log.tail(5)
            ui.html_table(list(log.columns), [[str(c) for c in r] for r in log.itertuples(index=False)], numeric_from=1)
        else:
            ui.footnote("No refresh log yet. Run <code>scripts\\export_capiq_watchlist.ps1</code> with Excel + the "
                        "Capital IQ add-in open, then rebuild the dataset.")

    ui.section("Coverage by Company")
    cov_headers = ["Ticker", "Company", "Period", "Completeness", "Deep Fields", "Financials"]
    cov_rows, cov_cls = [], []
    deep_cols = [c for c in ["sbc", "total_equity", "ar"] if c in df.columns]
    for _, r in latest.sort_values("data_quality_score", ascending=False).iterrows():
        score = r.get("data_quality_score", 0)
        deep = sum(1 for c in deep_cols if pd.notna(r.get(c)))
        cov_rows.append([
            r["ticker"].replace(".SA", ""), str(r.get("company_name", ""))[:26],
            ui.quarter_label(r["period"]),
            ui.cell_pill(fmt_pct(score), "green" if score >= 0.9 else "yellow" if score >= 0.7 else "red"),
            f"{deep}/{len(deep_cols)}" if deep_cols else "—",
            str(r.get("financial_source", "n/a"))[:24],
        ])
        cov_cls.append("anchor" if r["company_id"] == company_id else "")
    ui.html_table(cov_headers, cov_rows, cov_cls, numeric_from=2)

    ui.section("Validation Checks", f"{row.get('company_name')} | latest quarter")
    checks = {
        "Revenue reported": pd.notna(row.get("revenue")),
        "EBITDA reported": pd.notna(row.get("ebitda")),
        "Cash flow (CFO/Capex)": pd.notna(row.get("cfo")) and pd.notna(row.get("capex")),
        "Balance sheet (cash/debt)": pd.notna(row.get("cash")) and pd.notna(row.get("total_debt")),
        "Market data (cap/EV)": pd.notna(row.get("market_cap")) and pd.notna(row.get("enterprise_value")),
        "Deep fields (SBC/equity/AR)": any(pd.notna(row.get(c)) for c in ["sbc", "total_equity", "ar"]),
        "Consensus / estimates": store.has_estimates,
        "Valuation history": store.has_valuation_history,
        "TTM window complete": bool(row.get("ttm_complete", False)),
    }
    vrows = [[k, ui.cell_pill("Pass" if v else "Missing", "green" if v else "red")] for k, v in checks.items()]
    ui.html_table(["Check", "Status"], vrows)

    # --- Add Company (private mode: queries Capital IQ through Excel) -----------
    if not DEMO_MODE:
        import subprocess

        from src.ingestion.universe import (
            add_company,
            company_exists,
            ensure_universe,
            parse_lookup_result,
        )

        ui.section("Add Company", "Look up a Capital IQ identifier and add it to the private universe")
        st.markdown(
            "Enter an identifier like `NASDAQ:LULU`, `NYSE:NKE`, or `BOVESPA:GMAT3`. "
            "The lookup runs through the **Capital IQ Excel Add-In** - Excel must be open and signed in."
        )
        lookup_id = st.text_input("Capital IQ identifier", key="add_company_id",
                                  placeholder="EXCHANGE:TICKER").strip().upper()
        if st.button("Look up via Capital IQ", disabled=not lookup_id):
            script = _ROOT / "scripts" / "lookup_capiq_company.ps1"
            with st.spinner("Querying Capital IQ through Excel (up to ~90s)..."):
                try:
                    proc = subprocess.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Id", lookup_id],
                        capture_output=True, text=True, timeout=180,
                    )
                    json_path = _ROOT / "data_private" / "capiq_exports" / "company_lookup.json"
                    payload = json_path.read_text(encoding="utf-8-sig") if json_path.exists() else proc.stdout
                    st.session_state["add_company_preview"] = parse_lookup_result(payload).__dict__
                except subprocess.TimeoutExpired:
                    st.session_state["add_company_preview"] = {
                        "company_id": lookup_id, "resolved": False,
                        "error": "Lookup timed out - is Excel open with the Capital IQ add-in signed in?",
                    }

        preview = st.session_state.get("add_company_preview")
        if preview:
            if not preview.get("resolved"):
                st.error(f"Lookup failed for `{preview.get('company_id') or lookup_id}`: {preview.get('error')}")
            else:
                universe = ensure_universe()
                already = company_exists(universe, preview["company_id"],
                                         preview["company_id"].split(":")[-1])
                ui.html_table(["Field", "Value"], [
                    ["Company", preview.get("company_name") or "n/a"],
                    ["Identifier", preview.get("company_id")],
                    ["Exchange", preview.get("exchange") or "n/a"],
                    ["CapIQ industry", preview.get("industry") or "n/a"],
                    ["Filing currency", preview.get("currency") or "n/a"],
                    ["Already in universe", ui.cell_pill("Yes" if already else "No",
                                                          "red" if already else "green")],
                ], numeric_from=99)
                if already:
                    st.warning("This company is already in the private universe.")
                else:
                    latest_all = latest_rows(df)
                    groups = sorted(latest_all["peer_group"].dropna().unique()) if "peer_group" in latest_all.columns else []
                    c1, c2 = st.columns(2)
                    with c1:
                        group_pick = st.selectbox("Peer group", groups + ["(new peer group...)"])
                        group_val = st.text_input("New peer group name") if group_pick == "(new peer group...)" else group_pick
                    with c2:
                        bm = st.selectbox("Business model", ["operating", "financial", "insurer"])
                        ccy = st.text_input("Currency", value=preview.get("currency") or "USD", max_chars=3)

                    # --- Suggested Peers step (approve before saving) --------------
                    from src.modeling.peer_sets import MIN_VALID_PEERS, save_peer_set

                    st.markdown("**Suggested peers** - approve the comp set now "
                                "(financial similarity scoring unlocks after the next export refresh):")
                    if group_val in groups and "peer_group" in latest_all.columns:
                        same_group = latest_all[latest_all["peer_group"] == group_val]
                    else:
                        same_group = latest_all.iloc[0:0]
                    if "currency" in latest_all.columns:
                        same_ccy = latest_all[(latest_all["currency"] == ccy.upper())
                                              & (~latest_all["company_id"].isin(same_group["company_id"]))]
                    else:
                        same_ccy = latest_all.iloc[0:0]
                    peer_opts = {}
                    for r in same_group.itertuples():
                        peer_opts[f"{str(r.ticker).replace('.SA','')} | {r.company_name} | same peer group"] = r.company_id
                    for r in same_ccy.head(15).itertuples():
                        peer_opts[f"{str(r.ticker).replace('.SA','')} | {r.company_name} | same currency"] = r.company_id
                    default_peers = [k for k in peer_opts if "same peer group" in k]
                    picked_peers = st.multiselect("Approve peers for the new company",
                                                  list(peer_opts.keys()), default=default_peers)
                    small_ok = st.checkbox(f"Override: allow fewer than {MIN_VALID_PEERS} peers")
                    can_save = len(picked_peers) >= MIN_VALID_PEERS or small_ok
                    if not can_save:
                        st.caption(f"Select at least {MIN_VALID_PEERS} peers (or tick the override) to enable saving.")
                    if st.button("Add to private universe", type="primary", disabled=not can_save):
                        try:
                            ticker = preview["company_id"].split(":")[-1]
                            add_company(
                                company_id=preview["company_id"], ticker=ticker,
                                theme=group_val, currency=ccy,
                                peer_group=group_val, business_model=bm,
                                company_name=preview.get("company_name", ""),
                            )
                            members = [{"company_id": peer_opts[p],
                                        "rationale": p.split(" | ")[-1]} for p in picked_peers]
                            if members:
                                save_peer_set(preview["company_id"], f"{ticker} comps", members,
                                              source="manual", allow_small=True)
                            st.success(
                                f"{preview.get('company_name')} added to data_private/universe.csv "
                                f"with a {len(members)}-peer approved comp set."
                            )
                            st.session_state["add_company_fetch"] = {
                                "id": preview["company_id"],
                                "name": preview.get("company_name", ""),
                                "theme": group_val,
                                "currency": ccy.upper(),
                            }
                            st.session_state.pop("add_company_preview", None)
                        except ValueError as exc:
                            st.error(str(exc))

        # --- Auto-fetch step: pull the new company's CapIQ data immediately ------
        fetch = st.session_state.get("add_company_fetch")
        if fetch:
            st.markdown(
                f"**Fetch Capital IQ data for `{fetch['id']}` now?** Pulls 20 quarters of "
                "financials, 36 months of valuation history, the market snapshot, and "
                "consensus estimates for this one name only - the rest of the universe is "
                "not re-queried. Excel must be open and signed in (takes ~2-5 min)."
            )
            col_fetch, col_later = st.columns(2)
            run_fetch = col_fetch.button("Fetch data now via Excel", type="primary")
            if col_later.button("Later (the next full refresh will include it)"):
                st.session_state.pop("add_company_fetch", None)
                st.rerun()
            if run_fetch:
                from src.ingestion.single_import import merge_single_export
                from src.pipeline.build_dataset import build_dataset

                script = _ROOT / "scripts" / "export_capiq_single.ps1"
                with st.status(f"Fetching {fetch['name'] or fetch['id']} from Capital IQ...",
                               expanded=True) as status:
                    try:
                        st.write("Driving the Excel add-in (single-name workbook, staged output)...")
                        subprocess.run(
                            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
                             "-Id", fetch["id"], "-Sector", fetch["theme"],
                             "-Currency", fetch["currency"]],
                            capture_output=True, text=True, timeout=900,
                        )
                        merged = merge_single_export(fetch["id"])
                        st.write("Merged into the main exports: "
                                 + ", ".join(f"{k.replace('.csv', '')} +{v}"
                                             for k, v in merged.rows_merged.items()))
                        st.write("Rebuilding the monitoring dataset...")
                        build_dataset(
                            "capiq",
                            _ROOT / "data_private" / "capiq_exports",
                            _ROOT / "data_private" / "processed" / "monitoring_dataset.csv",
                        )
                        st.cache_data.clear()
                        status.update(
                            label=f"{merged.company_name or fetch['id']} loaded - every page "
                                  "now includes it (financials, peers, valuation).",
                            state="complete",
                        )
                        st.session_state.pop("add_company_fetch", None)
                    except subprocess.TimeoutExpired:
                        status.update(label="Fetch timed out - is Excel open with the "
                                            "Capital IQ add-in signed in?", state="error")
                    except (ValueError, OSError) as exc:
                        status.update(label=f"Fetch failed (main exports untouched): {exc}",
                                      state="error")

    ui.section("Source Log")
    log = load_source_log(DEMO_MODE)
    if not log.empty:
        ui.html_table(list(log.columns), [[str(c) for c in r] for r in log.itertuples(index=False)], numeric_from=99)
    st.markdown(
        '<div class="pe-memo" style="border-left-color:var(--amber);margin-top:14px">'
        '<h4 style="color:var(--amber)">Confidentiality</h4>'
        '<p style="font-family:var(--font-sans);font-size:12.5px">Licensed Capital IQ exports, private processed '
        'datasets, analyst theses, and private reports are excluded from version control via <code>.gitignore</code> '
        '(<code>data_private/</code>, <code>reports/private/</code>). The public repository ships only the '
        'synthetic public-demo dataset.</p></div>',
        unsafe_allow_html=True,
    )


def page_capital_structure(df: pd.DataFrame, company_id: str) -> None:
    import src.reporting.valuation_charts as vch

    from src.modeling.capital_structure import build_capital_structure, ev_bridge, leverage_history

    store = get_store(DEMO_MODE)
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    ui.header_band(row, DEMO_MODE)

    cs = build_capital_structure(row)
    if not cs.applicable:
        ui.section("Capital Structure", "Financial institution")
        st.info(cs.warnings[0])
        st.markdown("See the **Financials Valuation** section on the Valuation Case page "
                    "for the applicable framework (P/E, P/B, ROE vs COE, excess returns).")
        return

    ui.section("Leverage Today", f"{currency} millions | TTM basis")
    ui.kpi_grid([
        Kpi("nd", "Net Debt", f"{cs.net_debt:,.0f}" if cs.net_debt is not None else "n/a",
            f"gross {cs.gross_debt:,.0f} - cash {cs.cash:,.0f}" if cs.gross_debt is not None else "",
            "n/a"),
        Kpi("lev", "Net Leverage", f"{cs.net_leverage:.1f}x" if cs.net_leverage is not None else "n/a",
            "net debt / EBITDA",
            "green" if (cs.net_leverage or 9) < 2 else ("yellow" if (cs.net_leverage or 9) < 3.5 else "red")),
        Kpi("cov", "Interest Coverage", f"{cs.interest_coverage:.1f}x" if cs.interest_coverage else "n/a",
            "EBITDA / cash interest",
            "green" if (cs.interest_coverage or 0) > 4 else ("yellow" if (cs.interest_coverage or 0) > 2 else "red")),
        Kpi("ltv", "Net Debt % of EV", f"{cs.net_debt_pct_ev:.0%}" if cs.net_debt_pct_ev is not None else "n/a",
            "illustrative LTV", "n/a"),
        Kpi("cash", "Cash % of Debt", f"{cs.cash_pct_debt:.0%}" if cs.cash_pct_debt is not None else "n/a",
            "liquidity vs gross debt", "n/a"),
    ], columns=5)

    ui.section("Debt Capacity", "What the business supports at standard leverage multiples")
    rows = []
    for turns in sorted(cs.capacity):
        rows.append([f"{turns:.1f}x EBITDA", f"{cs.capacity[turns]:,.0f}",
                     f"{cs.incremental[turns]:+,.0f}"])
    ui.html_table(["Leverage level", f"Total debt supported ({currency}m)",
                   "Incremental vs today"], rows, numeric_from=1)
    ui.kpi_grid([
        Kpi("hl", "Covenant Headroom (Leverage)",
            f"{cs.leverage_headroom:+.1f}x" if cs.leverage_headroom is not None else "n/a",
            "vs 4.0x net-leverage covenant proxy",
            "green" if (cs.leverage_headroom or -1) > 1 else ("yellow" if (cs.leverage_headroom or -1) > 0 else "red")),
        Kpi("hc", "Covenant Headroom (Coverage)",
            f"{cs.coverage_headroom:+.1f}x" if cs.coverage_headroom is not None else "n/a",
            "vs 2.0x interest-coverage floor",
            "green" if (cs.coverage_headroom or -1) > 1 else ("yellow" if (cs.coverage_headroom or -1) > 0 else "red")),
        Kpi("sp", "Sponsor Debt Capacity",
            f"{cs.sponsor_capacity:,.0f}" if cs.sponsor_capacity is not None else "n/a",
            "incremental to 4.0x EBITDA", "n/a"),
    ], columns=3)

    ui.section("Current EV Bridge", "Calculated vs reported enterprise value")
    bridge = ev_bridge(row)
    st.plotly_chart(vch.current_ev_bridge_chart(bridge), use_container_width=True, config=PLOTLY_CONFIG)
    if bridge.get("mismatch"):
        st.warning(f"Calculated EV differs from the reported CapIQ TEV by {bridge['gap']:+.0%} - "
                   "CapIQ TEV includes items not yet exported (leases, pensions, exact share counts).")

    hist = leverage_history(df, company_id)
    if not hist.empty and "net_debt" in hist.columns:
        ui.section("Leverage Trend")
        st.plotly_chart(leverage_chart(df, company_id), use_container_width=True, config=PLOTLY_CONFIG)

    for w in cs.warnings:
        ui.footnote(w)
    ui.footnote("Covenant thresholds (4.0x leverage, 2.0x coverage) are market-standard proxies, "
                "not the company's actual covenants. Debt capacity is illustrative senior capacity, "
                "before market conditions and rating constraints.")


def page_consensus(df: pd.DataFrame, company_id: str) -> None:
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
    ui.section("Consensus Snapshot", "Latest reported quarter vs current consensus | NTM revisions")
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

    beat_fig = consensus_beat_chart(read.rows, currency=str(row.get("currency", "")))
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
        ui.section("Actual vs Consensus", "Approximation: consensus is the current-quarter "
                                          "estimate as of the last refresh")
        ui.html_table(["Metric", "Actual", "Consensus", "Delta", "Delta %", "Status"],
                      [[r["metric"], f"{r['actual']:,.1f}", f"{r['consensus']:,.1f}",
                        f"{r['delta']:+,.1f}", f"{r['delta_pct']:+.1%}",
                        ui.cell_pill(r["status"].upper(),
                                     "green" if r["status"] == "beat" else
                                     ("red" if r["status"] == "miss" else "n/a"))]
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


def page_data_audit(df: pd.DataFrame, company_id: str) -> None:
    from src.config import PRIVATE_CAPIQ_DIR
    from src.modeling.data_audit import audit_scores, run_audit

    store = get_store(DEMO_MODE)
    latest = latest_rows(df)

    exports: dict = {}
    if not DEMO_MODE:
        for key, stem in [("financials", "financials_quarterly"), ("market_data", "market_data"),
                          ("estimates", "estimates"), ("valuation_history", "valuation_history")]:
            path = PRIVATE_CAPIQ_DIR / f"{stem}.csv"
            if path.exists():
                try:
                    exports[key] = pd.read_csv(path)
                except Exception:
                    pass
    refresh_log = getattr(store, "refresh_log", None)

    issues = run_audit(df, latest, exports, refresh_log)
    scores = audit_scores(issues, latest)

    mode_txt = "Public Demo Data" if DEMO_MODE else "Capital IQ - Private"
    n_high = int((issues["severity"] == "high").sum()) if not issues.empty else 0
    affected = issues[issues["severity"].isin(["high", "medium"])]["company_id"].nunique() if not issues.empty else 0
    clean = int((scores[["high", "medium"]].sum(axis=1) == 0).sum()) if not scores.empty else 0
    last_refresh = "n/a"
    if refresh_log is not None and not refresh_log.empty and "refreshed_at" in refresh_log.columns:
        last_refresh = str(refresh_log["refreshed_at"].iloc[-1])[:16]
    st.markdown(
        f"""
        <div class="pe-header">
          <div class="pe-header-top">
            <div>
              <div class="kicker">Investment Watchlist | Quality Control</div>
              <h1>Data Audit<span class="ticker">{latest['company_id'].nunique()} names</span></h1>
            </div>
            <span class="pe-mode-pill {'pe-mode-demo' if DEMO_MODE else 'pe-mode-private'}">{mode_txt}</span>
          </div>
          <div class="pe-header-meta">
            <div class="pe-meta-item"><div class="pe-meta-label">Principle</div>
              <div class="pe-meta-value">Trust the data before trusting the valuation</div></div>
            <div class="pe-meta-item"><div class="pe-meta-label">Latest Dataset Period</div>
              <div class="pe-meta-value">{pd.to_datetime(latest['period']).max().date()}</div></div>
            <div class="pe-meta-item"><div class="pe-meta-label">Last Full Refresh</div>
              <div class="pe-meta-value">{last_refresh}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ui.kpi_grid([
        Kpi("t", "Total Findings", str(len(issues)), "all severities", "n/a"),
        Kpi("h", "High Severity", str(n_high), "fix before trusting outputs",
            "red" if n_high else "green"),
        Kpi("a", "Names Affected", str(affected), "high/medium findings",
            "yellow" if affected else "green"),
        Kpi("c", "Clean Names", str(clean), "no high/medium findings", "green"),
        Kpi("s", "Median Audit Score", f"{scores['score'].median():.0f}" if not scores.empty else "n/a",
            "100 = clean", "n/a"),
    ], columns=5)

    if not issues.empty:
        ui.section("Findings Overview", "Which checks fire, and how severe")
        v1, v2 = st.columns([1.4, 1.0], gap="medium")
        with v1:
            st.plotly_chart(audit_findings_by_check_chart(issues),
                            use_container_width=True, config=PLOTLY_CONFIG)
        with v2:
            st.plotly_chart(audit_severity_chart(issues),
                            use_container_width=True, config=PLOTLY_CONFIG)

    ui.section("Most Urgent Fixes", "High severity first - each finding names the source table")
    urgent = issues[issues["severity"] == "high"].head(10) if not issues.empty else pd.DataFrame()
    if urgent.empty:
        st.success("No high-severity data issues detected.")
    else:
        ui.html_table(["Ticker", "Check", "Source", "Detail"],
                      [[r.ticker, r.check, r.source_table, escape(str(r.detail))]
                       for r in urgent.itertuples()], numeric_from=99, wrap=True)

    ui.section("All Findings")
    if issues.empty:
        st.success("Audit ran clean across all checks.")
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            sev_pick = st.multiselect("Severity", ["high", "medium", "low", "info"],
                                      default=["high", "medium"])
        with f2:
            check_pick = st.multiselect("Check", sorted(issues["check"].unique()))
        with f3:
            comp_pick = st.multiselect("Company", sorted(issues["ticker"].unique()))
        view = issues
        if sev_pick:
            view = view[view["severity"].isin(sev_pick)]
        if check_pick:
            view = view[view["check"].isin(check_pick)]
        if comp_pick:
            view = view[view["ticker"].isin(comp_pick)]
        sev_pill = {"high": "red", "medium": "yellow", "low": "n/a", "info": "n/a"}
        ui.html_table(["Sev", "Ticker", "Check", "Source", "Detail"],
                      [[ui.cell_pill(r.severity.upper(), sev_pill.get(r.severity, "n/a")),
                        r.ticker, r.check, r.source_table, escape(str(r.detail))]
                       for r in view.head(200).itertuples()], numeric_from=99, wrap=True)
        st.download_button("Export audit report (CSV)", issues.to_csv(index=False),
                           file_name="data_audit_report.csv", mime="text/csv")

    ui.section("Company Audit Scores", "100 = clean | high -15 | medium -5 | low -1")
    if not scores.empty:
        worst = scores.head(15)
        ui.html_table(["Ticker", "Score", "High", "Medium", "Low"],
                      [[r.ticker, str(int(r.score)), str(int(r.high)), str(int(r.medium)),
                        str(int(r.low))] for r in worst.itertuples()], numeric_from=1)

    with st.expander("Audit methodology"):
        st.markdown(
            "- **Market-cap bridge**: price x shares vs reported cap; <5% pass, 5-15% low, "
            "15-30% medium, >30% high.\n"
            "- **EV bridge**: cap + debt + minority + preferred - cash vs reported TEV. Cash "
            "means cash & ST investments (CapIQ's TEV basis) when exported, else cash & "
            "equivalents (disclosed). Bridges without minority/preferred are labeled *partial*.\n"
            "- **Unit sanity**: cross-table ratios (cap/revenue, EV/EBITDA) beyond physical limits "
            "signal currency or millions-vs-units mismatches.\n"
            "- **Sign conventions**: pipeline stores capex as positive outflow, FCF = CFO - capex. "
            "Violations are FLAGGED, never silently flipped.\n"
            "- **TTM completeness**: 4 reported quarters required; financials are exempt from "
            "EBITDA-frame fields by design.\n"
            "- **Stale periods**: real dates vs the universe's latest period; 1 quarter medium, "
            "2+ high.\n"
            "- **Refresh consistency**: dataset vs export vs refresh_log counts (single-name "
            "fetches accumulate between full refreshes - expected, but disclosed).\n"
            "- **Outliers**: same rules as the comps engine; excluded from adjusted medians, "
            "never hidden."
        )


# --- router -----------------------------------------------------------------

ROUTES = {
    "Watchlist Home": page_watchlist_home,
    "Compare": page_compare,
    "Company Situation": page_company_situation,
    "Actual vs Consensus": page_consensus,
    "Company Financials": page_company_financials,
    "Capital Structure": page_capital_structure,
    "Data Audit": page_data_audit,
    "Valuation Case": page_valuation_case,
    "Valuation & Expectations": page_valuation_expectations,
    "Peer Benchmarking": page_peer_benchmarking,
    "IC Memo Export": page_ic_memo,
    "Data & Refresh": page_data_refresh,
}


def main() -> None:
    df = load_data(DEMO_MODE)
    company_id, page = sidebar(df)
    ROUTES.get(page, page_watchlist_home)(df, company_id)


if __name__ == "__main__":
    main()
