"""IC memo generation — the decision document for one watchlist name.

Combines the machine layer (assessment, valuation history, revisions,
scenarios) with the analyst layer (thesis YAML) into a single HTML memo.
Demo output goes to ``reports/sample``; private output stays inside
``data_private/reports`` and never enters version control.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from jinja2 import Template

from src.branding import PALETTE, VERDICT_COLORS
from src.config import PRIVATE_DATA_DIR, REPORTS_SAMPLE_DIR
from src.ingestion.store import WatchlistStore, load_store
from src.modeling.assessment import build_assessment
from src.modeling.scenarios import cases_from_thesis, implied_expectations, run_cases
from src.reporting.board_pack import _history_chart, _peer_chart, _png_uri, load_dataset
from src.reporting.ic_memo_template import IC_MEMO_TEMPLATE, ic_memo_css
from src.utils import ensure_dir, fmt_money, fmt_multiple, fmt_ordinal, fmt_pct, fmt_signed_pct


def _tone_irr(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    cls = "irr-pos" if value >= 0 else "irr-neg"
    return f'<span class="{cls}">{value:+.1%}</span>'


def _tone_pct(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    cls = "tone-green" if value > 0 else "tone-red"
    return f'<span class="{cls}">{fmt_signed_pct(value)}</span>'


def build_memo_context(df: pd.DataFrame, company_id: str, store: WatchlistStore) -> dict:
    a = build_assessment(df, company_id, store=store)
    row = a.row
    currency = row.get("currency", "USD")
    financial = a.business_model == "financial"
    thesis = a.thesis
    demo = store.mode == "demo"

    # --- Situation ---------------------------------------------------------
    situation_bits = [a.commentary]
    hc = a.history_context
    if hc.get("available"):
        pct = hc["percentile"]
        situation_bits.append(
            f"The {'P/E' if financial else 'EV/EBITDA'} multiple sits in the {fmt_ordinal(pct)} percentile of its own "
            f"{hc['n_obs']}-observation history (median {fmt_multiple(hc['median'])}, range "
            f"{fmt_multiple(hc['low'])}–{fmt_multiple(hc['high'])})."
        )
    if thesis and thesis.thesis:
        situation_bits.append(thesis.thesis)
    situation = " ".join(situation_bits)

    # --- Why now -----------------------------------------------------------
    rev = a.revisions
    why_now = {
        "history": (fmt_ordinal(hc["percentile"]) + " pctile") if hc.get("available") else "n/a",
        "history_detail": (f"median {fmt_multiple(hc['median'])} · z {hc['z_score']:+.1f}" if hc.get("available")
                           else "valuation history not populated"),
        "revisions": rev.get("direction", "n/a").title(),
        "revisions_detail": (f"NTM rev {fmt_signed_pct(rev['revenue_30d'])} / 30d" if rev.get("revenue_30d") is not None
                             else "consensus not populated"),
        "premium": a.valuation.get("premium_label", "n/a"),
        "premium_detail": f"vs {a.peer_group} median {a.valuation.get('multiple_name', '')}",
        "earnings": rev.get("next_earnings_date") or "n/a",
        "flags": sum(1 for f in a.red_flags if f.get("severity") in {"High", "Medium"}),
    }

    # --- Business quality table ---------------------------------------------
    prior = a.prior
    med = a.peer_median

    def q_row(label, metric, formatter):
        cur = row.get(metric)
        pri = prior.get(metric) if prior is not None else None
        return {
            "label": label,
            "current": formatter(cur),
            "prior": formatter(pri) if pri is not None else "n/a",
            "median": formatter(med.get(metric)) if med.get(metric) is not None else "n/a",
        }

    if financial:
        quality_rows = [
            q_row("Revenue growth (YoY)", "revenue_yoy_growth", fmt_pct),
            q_row("Net income margin (TTM)", "net_income_margin_ttm", fmt_pct),
            {"label": "ROE (TTM)", "current": fmt_pct(row.get("roe_ttm")),
             "prior": fmt_pct(prior.get("roe_ttm")) if prior is not None else "n/a", "median": "n/a"},
            {"label": "P/TBV", "current": fmt_multiple(row.get("p_tbv")), "prior": "n/a", "median": "n/a"},
        ]
        profit_label = "Net Income"
    else:
        quality_rows = [
            q_row("Revenue growth (YoY)", "revenue_yoy_growth", fmt_pct),
            q_row("EBITDA margin (TTM)", "ebitda_margin_ttm", fmt_pct),
            q_row("FCF conversion (TTM)", "fcf_conversion_ttm", fmt_pct),
            {"label": "ROIC (TTM)", "current": fmt_pct(row.get("roic_ttm")),
             "prior": fmt_pct(prior.get("roic_ttm")) if prior is not None else "n/a", "median": "n/a"},
            q_row("Net debt / EBITDA", "net_debt_to_ebitda_ttm", fmt_multiple),
        ]
        if pd.notna(row.get("sbc_pct_of_fcf_ttm")):
            quality_rows.append({"label": "SBC as % of FCF (TTM)", "current": fmt_pct(row.get("sbc_pct_of_fcf_ttm")),
                                 "prior": "n/a", "median": "n/a"})
        if pd.notna(row.get("cash_conversion_cycle")):
            quality_rows.append({"label": "Cash conversion cycle (days)",
                                 "current": f"{row.get('cash_conversion_cycle'):.0f}",
                                 "prior": (f"{prior.get('cash_conversion_cycle'):.0f}"
                                           if prior is not None and pd.notna(prior.get("cash_conversion_cycle")) else "n/a"),
                                 "median": "n/a"})
        profit_label = "EBITDA"

    # --- Financial snapshot --------------------------------------------------
    history = df[df["company_id"] == company_id].sort_values("period").tail(8)
    profit_col = "net_income" if financial else "ebitda"
    margin_col = "net_income_margin" if financial else "ebitda_margin"
    performance_rows = []
    for _, h in history.iterrows():
        performance_rows.append({
            "period": f"Q{pd.Timestamp(h['period']).quarter} {pd.Timestamp(h['period']).year}",
            "revenue": fmt_money(h.get("revenue"), currency),
            "rev_yoy": _tone_pct(h.get("revenue_yoy_growth")),
            "profit": fmt_money(h.get(profit_col), currency),
            "margin": fmt_pct(h.get(margin_col)),
            "fcf": fmt_money(h.get("fcf"), currency),
            "is_latest": h["period"] == row["period"],
        })

    # --- Valuation & scenarios -----------------------------------------------
    val = a.valuation
    valuation_rows = [
        {"label": "Market cap", "value": fmt_money(row.get("market_cap"), currency), "context": ""},
        {"label": "Enterprise value", "value": fmt_money(row.get("enterprise_value"), currency), "context": ""},
        {"label": "EV / EBITDA", "value": val["ev_to_ebitda"], "context": f"median {val['ev_to_ebitda_median']}"},
        {"label": "EV / Revenue", "value": val["ev_to_revenue"], "context": f"median {val['ev_to_revenue_median']}"},
        {"label": "P / E", "value": val["pe"], "context": f"median {val['pe_median']}"},
    ]
    if hc.get("available"):
        valuation_rows.append({"label": f"Own-history percentile ({hc['column']})",
                               "value": fmt_ordinal(hc["percentile"]), "context": f"z {hc['z_score']:+.1f}"})

    thesis_scen = thesis.scenarios if thesis else None
    results = run_cases(row, thesis_scen)
    scenario_rows = []
    for res in results:
        scenario_rows.append({
            "name": res.case.name.title(),
            "cagr": fmt_signed_pct(res.case.revenue_cagr),
            "margin": fmt_pct(res.case.exit_margin),
            "multiple": f"{res.case.exit_multiple:g}x",
            "moic": f"{res.moic:.2f}x" if res.valid else "n/a",
            "irr": _tone_irr(res.irr if res.valid else None),
        })
    horizon = results[0].case.horizon_years if results else 3
    scenario_note = ("Cases from analyst thesis." if (thesis_scen) else
                     "Cases auto-derived from the company's current profile — refine in the thesis YAML.")

    fair_mult = med.get("pe_ttm") if financial else med.get("ev_to_ebitda_ttm")
    ie = implied_expectations(row, fair_mult, horizon_years=horizon)
    if ie["available"]:
        req_bits = ", ".join(
            f"{r['return']:.0%} → {r['implied_profit_cagr']:+.0%}" for r in ie["required"]
        )
        implied_text = (
            f"Assuming exit at the peer-median {ie['multiple_name']} of {fmt_multiple(ie['fair_exit_multiple'])} in "
            f"{ie['horizon_years']} years, the {ie['metric']} CAGR required to clear each return hurdle is: {req_bits}. "
            f"{val.get('commentary', '')}"
        )
    else:
        implied_text = val.get("commentary", "Insufficient data for implied expectations.")

    # --- Catalysts / risks / decision -----------------------------------------
    catalysts = [
        {"date": str(c.get("date", "")), "event": str(c.get("event", "")), "note": str(c.get("note", "") or "")}
        for c in (thesis.catalysts if thesis else [])
    ]
    risks = thesis.risks if thesis else []
    journal = list(reversed((thesis.journal if thesis else [])))[:3]
    journal = [{"date": str(j.get("date", "")), "note": str(j.get("note", ""))} for j in journal]

    decision_map = {
        "do_work": "Advance to active diligence: resolve the key debate before the next earnings date.",
        "constructive": "Maintain coverage; revisit sizing on weakness or thesis-confirming data points.",
        "watch": "No action; let the next quarter confirm direction before committing diligence hours.",
        "avoid": "Pass at the current price; re-engage only if valuation or fundamentals reset.",
    }
    decision_text = decision_map.get(a.verdict_key, "Maintain standard coverage.")

    return {
        "css": ic_memo_css(),
        "memo_date": pd.Timestamp.today().strftime("%d %b %Y"),
        "company": row.to_dict(),
        "theme": a.theme,
        "peer_group": a.peer_group,
        "currency_label": f"{currency} millions",
        "as_of": pd.Timestamp(row["period"]).strftime("%d %b %Y"),
        "mode": "Public Demo Data" if demo else "Capital IQ Private Export",
        "stage_label": thesis.stage_label if (thesis and thesis.exists) else "No Thesis On File",
        "attention_score": a.attention_score,
        "verdict": {"label": a.verdict_label, "rationale": a.verdict_rationale,
                    "color": VERDICT_COLORS.get(a.verdict_key, PALETTE["navy_3"])},
        "snapshot": {
            "price": (f"{row.get('share_price'):,.2f}" if pd.notna(row.get("share_price")) else "n/a"),
            "market_cap": fmt_money(row.get("market_cap"), currency),
            "ev": fmt_money(row.get("enterprise_value"), currency),
            "multiple": f"{val.get('pe') if financial else val.get('ev_to_ebitda')} {val.get('multiple_name')}",
        },
        "situation": situation,
        "why_now": why_now,
        "quality_rows": quality_rows,
        "profit_label": profit_label,
        "performance_rows": performance_rows,
        "chart_history": _png_uri(_history_chart(df, company_id, currency)),
        "chart_peer": _png_uri(_peer_chart(df, company_id)),
        "valuation_rows": valuation_rows,
        "implied_text": implied_text,
        "scenario_rows": scenario_rows,
        "scenario_note": scenario_note,
        "scenario_profit_label": ie["metric"],
        "horizon": horizon,
        "thesis": {
            "variant_perception": thesis.variant_perception if thesis else "",
            "key_debate": thesis.key_debate if thesis else "",
        },
        "catalysts": catalysts,
        "risks": risks,
        "concerns": a.concerns,
        "questions": a.management_questions,
        "journal": journal,
        "decision_text": decision_text,
    }


def generate_ic_memo(
    demo: bool = True,
    company_id: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    store = load_store(demo)
    df = load_dataset(demo=demo)
    if company_id is None:
        from src.modeling.metrics import latest_rows
        latest = latest_rows(df)
        company_id = latest.sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]

    if output_dir is None:
        output_dir = REPORTS_SAMPLE_DIR if demo else PRIVATE_DATA_DIR / "reports"
    ensure_dir(output_dir)

    context = build_memo_context(df, company_id, store)
    ticker = str(context["company"].get("ticker", company_id)).replace(".SA", "").replace(":", "_")
    output_path = Path(output_dir) / f"ic_memo_{ticker}.html"
    html = Template(IC_MEMO_TEMPLATE).render(**context)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an IC memo for one watchlist company.")
    parser.add_argument("--demo", action="store_true", help="Use public demo dataset.")
    parser.add_argument("--company", default=None, help="company_id to report (defaults to best-covered name).")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    path = generate_ic_memo(
        demo=args.demo,
        company_id=args.company,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(f"IC memo written to {path}")


if __name__ == "__main__":
    main()
