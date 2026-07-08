"""Data Audit: trust the data before trusting the valuation."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store
from src.modeling.assessment import Kpi
from src.modeling.metrics import latest_rows
from src.reporting.charts import audit_findings_by_check_chart, audit_severity_chart


def render(df: pd.DataFrame, company_id: str) -> None:
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
