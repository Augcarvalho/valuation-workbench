"""Data & Refresh: mode, dataset, refresh log, add-company workflow."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import components as ui
from src.app.context import _dataset_path, DEMO_MODE, get_store, load_source_log
from src.config import PROJECT_ROOT
from src.modeling.assessment import Kpi, build_assessment
from src.modeling.metrics import latest_rows
from src.utils import fmt_pct


def render(df: pd.DataFrame, company_id: str) -> None:
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
    cov_headers = ["Ticker", "Company", "Financials Through", "LTM Completeness", "Deep Fields", "Financials"]
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
        "LTM window complete (4 consecutive quarters)": bool(row.get("ttm_complete", False)),
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
            script = PROJECT_ROOT / "scripts" / "lookup_capiq_company.ps1"
            with st.spinner("Querying Capital IQ through Excel (up to ~90s)..."):
                try:
                    proc = subprocess.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Id", lookup_id],
                        capture_output=True, text=True, timeout=180,
                    )
                    if proc.returncode != 0:
                        raise OSError(proc.stderr.strip() or proc.stdout.strip()
                                      or f"Capital IQ lookup exited with code {proc.returncode}")
                    json_path = PROJECT_ROOT / "data_private" / "capiq_exports" / "company_lookup.json"
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

                script = PROJECT_ROOT / "scripts" / "export_capiq_single.ps1"
                with st.status(f"Fetching {fetch['name'] or fetch['id']} from Capital IQ...",
                               expanded=True) as status:
                    try:
                        st.write("Driving the Excel add-in (single-name workbook, staged output)...")
                        proc = subprocess.run(
                            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
                             "-Id", fetch["id"], "-Sector", fetch["theme"],
                             "-Currency", fetch["currency"]],
                            capture_output=True, text=True, timeout=900,
                        )
                        if proc.returncode != 0:
                            raise OSError(proc.stderr.strip() or proc.stdout.strip()
                                          or f"Capital IQ export exited with code {proc.returncode}")
                        merged = merge_single_export(fetch["id"])
                        st.write("Merged into the main exports: "
                                 + ", ".join(f"{k.replace('.csv', '')} +{v}"
                                             for k, v in merged.rows_merged.items()))
                        st.write("Rebuilding the monitoring dataset...")
                        build_dataset(
                            "capiq",
                            PROJECT_ROOT / "data_private" / "capiq_exports",
                            PROJECT_ROOT / "data_private" / "processed" / "monitoring_dataset.csv",
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
