"""Peer Benchmarking: review workflow, valuation spread, positioning."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import DEMO_MODE, PLOTLY_CONFIG, get_store, tone
from src.config import PROJECT_ROOT
from src.modeling.assessment import build_assessment
from src.modeling.metrics import latest_rows
from src.reporting.charts import peer_scatter, peer_valuation_scatter, valuation_chart
from src.reporting.periods import peer_metric_basis_note, peer_snapshot_context
from src.utils import fmt_multiple, fmt_pct


def render(df: pd.DataFrame, company_id: str) -> None:
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
        "capiq_web_peer_comps": ("Capital IQ Web peers (suggested)", "yellow"),
        "manual": ("Manually approved set", "green"),
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
        if st.button("Mark set manually approved", type="primary", disabled=current_set is None):
            approve_peer_set(company_id, reviewer_note=note)
            st.success("Peer set marked manually approved.")
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
        ui.footnote(f"{n_rev} of {len(qrows)} names manually approved. Approval is always an "
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

    expansion_path = PROJECT_ROOT / "data_private" / "capiq_exports" / "peer_expansion_candidates.csv"
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
            "**Hierarchy:** 1) Capital IQ comp-set import (manually approved) -> 2) scored comp sets "
            "and Capital IQ Web peer-comps (batch-generated and labeled *not reviewed* until approved) -> "
            "3) static peer-group mapping -> 4) full universe (flagged).\n\n"
            "**Suggestion scoring (0-100):** " +
            ", ".join(f"{k.replace('_', ' ')} {v}pts" for k, v in WEIGHTS.items()) +
            "; cross-business-model candidates are penalized 20pts. Size uses log market-cap proximity "
            "(USD-normalized); margin/growth use absolute proximity bands. Candidates are limited to the "
            "exported universe - add outside names via Data & Refresh first."
        )

    time_context = peer_snapshot_context(store, a.peers)
    ui.section("Peer Universe", f"{a.peer_set_name} | {src_label.lower()} | {time_context}")
    peers = a.peers.sort_values("ev_to_ebitda_ttm")
    headers = ["Ticker", "Company", "Rev Growth (Latest Q YoY)", "EBITDA Margin (LTM)",
               "FCF Conv. (LTM)", "Net Debt / EBITDA (LTM)", "EV / Revenue (LTM)",
               "EV / EBITDA (LTM)", "Financials Through"]
    rows, classes = [], []
    for _, p in peers.iterrows():
        g = p.get("revenue_yoy_growth")
        rows.append([
            p["ticker"].replace(".SA", ""),
            str(p.get("company_name", ""))[:26],
            tone(fmt_pct(g), (g > 0) if pd.notna(g) else None),
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
        "--", "Peer median (ex-company)",
        fmt_pct(med.get("revenue_yoy_growth")),
        fmt_pct(med.get("ebitda_margin_ttm")),
        fmt_pct(med.get("fcf_conversion_ttm")),
        fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
        fmt_multiple(med.get("ev_to_revenue_ttm")),
        fmt_multiple(med.get("ev_to_ebitda_ttm")),
        "",
    ])
    classes.append("median")
    ui.html_table(headers, rows, classes, numeric_from=2, wrap=True, dense=True)
    ui.footnote(peer_metric_basis_note() + " Financial periods can differ because fiscal calendars differ.")

    # --- IB-style valuation spread ------------------------------------------------
    from src.modeling.comps import comps_spread, quartile_stats
    from src.reporting import multiples_charts as mch

    spread = comps_spread(a.peers, store.estimates)
    peer_spread = spread.loc[spread["company_id"].astype(str) != str(company_id)].copy()
    stats = quartile_stats(peer_spread if not peer_spread.empty else spread)
    ui.section("Valuation Spread",
               f"{time_context} | LTM = trailing four quarters; NTM = next twelve months consensus")

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
    ui.footnote("All summary statistics exclude the selected company. * flagged outlier (extreme multiple), excluded from the ex-outlier median. "
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
            "Revenue growth (latest Q YoY)", "EV / Revenue (LTM)",
            "Growth vs EV/Revenue (LTM)", "Latest-quarter growth should help explain the LTM revenue multiple"),
            use_container_width=True, config=PLOTLY_CONFIG)
    with s2:
        st.plotly_chart(mch.fundamental_vs_multiple_scatter(
            spread, company_id, "ebitda_margin_ttm", "ev_to_ebitda_ttm",
            "EBITDA margin (LTM)", "EV / EBITDA (LTM)",
            "LTM Margin vs EV/EBITDA", "LTM margin quality should support the LTM EBITDA multiple"),
            use_container_width=True, config=PLOTLY_CONFIG)
    s3, s4 = st.columns(2, gap="medium")
    # Older/demo datasets may not carry p_tbv - select only what exists.
    _roe_cols = [c for c in ("company_id", "ticker", "roe_ttm", "pe_ttm", "p_tbv")
                 if c in a.peers.columns]
    roe_spread = a.peers[_roe_cols].copy() if "roe_ttm" in _roe_cols else pd.DataFrame()
    with s3:
        if not roe_spread.empty:
            st.plotly_chart(mch.fundamental_vs_multiple_scatter(
                roe_spread, company_id, "roe_ttm", "pe_ttm",
                "ROE (LTM)", "P / E (LTM)",
                "ROE vs P/E", "Return on equity should earn the earnings multiple"),
                use_container_width=True, config=PLOTLY_CONFIG)
    with s4:
        if not roe_spread.empty and a.business_model == "financial":
            st.plotly_chart(mch.fundamental_vs_multiple_scatter(
                roe_spread, company_id, "roe_ttm", "p_tbv",
                "ROE (LTM)", "P / TBV",
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
