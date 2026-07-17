"""Valuation case HTML export.

Renders the full :class:`ValuationCase` into a self-contained HTML document.
Demo output goes to ``reports/sample``; private output stays inside
``data_private/reports`` and never enters version control.

CLI:
    python -m src.reporting.valuation_case --demo --company TOTS3.SA
    python -m src.reporting.valuation_case --company "NASDAQ:LULU"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Template

from src.config import PRIVATE_DATA_DIR, REPORTS_SAMPLE_DIR
from src.ingestion.store import load_store
from src.modeling.valuation_case import (
    CaseNotApplicableError,
    ValuationCase,
    build_valuation_case,
    case_warnings,
)
from src.reporting.board_pack import load_dataset
from src.reporting.valuation_case_template import VALUATION_CASE_TEMPLATE, valuation_case_css
from src.reporting.valuation_charts import assumptions_provenance, assumptions_status, case_chart_images
from src.utils import ensure_dir, fmt_money, fmt_multiple, fmt_pct


def _pct(value, digits=1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:+.{digits}%}"


def _tone_pct(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    cls = "pos" if value >= 0 else "neg"
    return f'<span class="{cls}">{value:+.1%}</span>'


def _price(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:,.2f}"


def _grid_context(grid: pd.DataFrame, kind: str) -> dict:
    """Serialize a sensitivity DataFrame for the template, marking the center cell."""
    n_rows, n_cols = grid.shape
    center = (n_rows // 2, n_cols // 2)
    rows = []
    for i, (idx, row) in enumerate(grid.iterrows()):
        values = []
        for j, v in enumerate(row):
            if pd.isna(v):
                values.append({"text": "n/a", "cls": ""})
                continue
            if kind == "price":
                text = f"{v:,.2f}"
                cls = "grid-anchor" if (i, j) == center else ""
            else:
                text = f"{v:+.0%}"
                tone = "pos" if v >= 0 else "neg"
                cls = f"grid-anchor {tone}" if (i, j) == center else tone
            values.append({"text": text, "cls": cls})
        rows.append({"label": str(idx), "cells": values})
    return {"columns": [str(c) for c in grid.columns], "rows": rows}




def _case_warnings_with_divergence(case: ValuationCase) -> list[dict]:
    from src.reporting.valuation_charts import terminal_value_divergence

    warnings = case_warnings(case)
    note = terminal_value_divergence(case)
    if note:
        warnings.append({"severity": "medium", "text": note})
    return warnings


def build_case_context(case: ValuationCase, demo: bool, df: pd.DataFrame | None = None) -> dict:
    a = case.assessment
    row = a.row
    currency = str(row.get("currency", "USD"))
    base = case.base
    horizon = case.assumptions.horizon_years

    # Overview: thesis text when the analyst wrote one, else generated description.
    if a.thesis and a.thesis.thesis:
        overview = a.thesis.thesis
    else:
        overview = a.commentary
    thesis = a.thesis

    f = base.forecast
    money = lambda v: fmt_money(v, currency)  # noqa: E731

    def line(label, series, formatter):
        return {"label": label, "cells": [formatter(v) for v in series]}

    forecast_lines = [
        line("Revenue", f["revenue"], money),
        line("  growth", f["revenue_growth"], lambda v: f"{v:+.1%}"),
        line("EBITDA", f["ebitda"], money),
        line("  margin", f["ebitda_margin"], lambda v: f"{v:.1%}"),
        line("D&A", f["d_and_a"], money),
        line("EBIT", f["ebit"], money),
        line("Taxes", f["taxes"], money),
        line("NOPAT", f["nopat"], money),
        line("Capex", f["capex"], money),
        line("Change in NWC", f["delta_nwc"], money),
        line("UFCF", f["ufcf"], money),
    ]

    # Comps spread rows.
    spread_rows = []
    for _, p in case.spread.iterrows():
        g = p.get("revenue_yoy_growth")
        spread_rows.append({
            "name": str(p.get("ticker", "")).replace(".SA", ""),
            "market_cap": fmt_money(p.get("market_cap"), currency) if pd.notna(p.get("market_cap")) else "n/a",
            "ev": fmt_money(p.get("enterprise_value"), currency) if pd.notna(p.get("enterprise_value")) else "n/a",
            "growth": _tone_pct(g),
            "margin": fmt_pct(p.get("ebitda_margin_ttm")),
            "ev_rev": fmt_multiple(p.get("ev_to_revenue_ttm")),
            "ev_ebitda": fmt_multiple(p.get("ev_to_ebitda_ttm")),
            "ev_ebitda_ntm": fmt_multiple(p.get("ev_to_ebitda_ntm")),
            "pe": fmt_multiple(p.get("pe_ttm")),
            "is_anchor": p.get("company_id") == case.company_id,
        })
    stats = case.spread_stats

    def stat_row(label, key):
        def cell(metric, formatter):
            if metric in stats.index and pd.notna(stats.loc[metric, key]):
                return formatter(stats.loc[metric, key])
            return ""
        return {
            "label": label,
            "growth": cell("revenue_yoy_growth", fmt_pct),
            "margin": cell("ebitda_margin_ttm", fmt_pct),
            "ev_rev": cell("ev_to_revenue_ttm", fmt_multiple),
            "ev_ebitda": cell("ev_to_ebitda_ttm", fmt_multiple),
            "ev_ebitda_ntm": cell("ev_to_ebitda_ntm", fmt_multiple),
            "pe": cell("pe_ttm", fmt_multiple),
        }

    stat_rows = [stat_row("1st quartile", "q1"), stat_row("Median", "median"), stat_row("3rd quartile", "q3")]

    w = case.wacc
    wacc_rows = [
        {"label": "Risk-free rate", "value": f"{w.risk_free_rate:.2%}"},
        {"label": "Equity risk premium", "value": f"{w.equity_risk_premium:.2%}"},
        {"label": "Country risk premium", "value": f"{w.country_risk_premium:.2%}"},
        {"label": f"Beta ({w.beta_source})", "value": f"{w.beta:.2f}"},
        {"label": "Cost of equity", "value": f"{w.cost_of_equity:.2%}"},
        {"label": "Pre-tax cost of debt", "value": f"{w.cost_of_debt_pretax:.2%}"},
        {"label": f"After-tax cost of debt (t={w.tax_rate:.0%})", "value": f"{w.cost_of_debt_aftertax:.2%}"},
        {"label": "Equity / debt weights", "value": f"{w.equity_weight:.0%} / {w.debt_weight:.0%}"},
        {"label": "WACC" + (" (override)" if w.overridden else ""), "value": f"{w.wacc:.2%}"},
        {"label": f"Terminal WACC ({case.assumptions.terminal_wacc_source})",
         "value": f"{base.terminal_wacc:.2%}"},
        {"label": f"Terminal ROIC ({case.assumptions.terminal_roic_source})",
         "value": f"{base.terminal_roic:.2%}"},
        {"label": "Stable reinvestment (g / ROIC)",
         "value": f"{base.terminal_reinvestment_rate:.2%}"
         if base.terminal_reinvestment_rate is not None else "n/m"},
    ]

    market_tv = (
        float(f["ebitda"].iloc[-1]) * case.market_reference_multiple
        if case.market_reference_multiple is not None else np.nan
    )
    market_pv = (
        base.pv_terminal_exit * case.market_reference_multiple / base.exit_multiple
        if case.market_reference_multiple is not None and base.exit_multiple > 0 else np.nan
    )
    market_ev = base.pv_explicit + market_pv if not np.isnan(market_pv) else np.nan
    tv_rows = [
        {"label": "Terminal value", "exit": money(base.terminal_value_exit),
         "perp": money(base.terminal_value_perp) if not np.isnan(base.terminal_value_perp) else "n/m",
         "market": money(market_tv) if not np.isnan(market_tv) else "n/a"},
        {"label": "PV of terminal value", "exit": money(base.pv_terminal_exit),
         "perp": money(base.pv_terminal_perp) if not np.isnan(base.pv_terminal_perp) else "n/m",
         "market": money(market_pv) if not np.isnan(market_pv) else "n/a"},
        {"label": "Enterprise value", "exit": money(base.enterprise_value),
         "perp": money(base.enterprise_value_perp) if not np.isnan(base.enterprise_value_perp) else "n/m",
         "market": money(market_ev) if not np.isnan(market_ev) else "n/a"},
    ]
    cross_bits = []
    if base.implied_terminal_growth is not None:
        cross_bits.append(
            f"The {case.exit_multiple:.1f}x exit implies {base.implied_terminal_growth:+.1%} perpetual FCF growth "
            f"versus the {case.assumptions.perpetuity_growth:.1%} perpetuity anchor"
        )
    if base.implied_exit_multiple is not None:
        cross_bits.append(f"the perpetuity implies a {base.implied_exit_multiple:.1f}x exit multiple")
    if case.market_reference_multiple is not None:
        cross_bits.append(
            f"the independent market reference is {case.market_reference_multiple:.1f}x "
            f"({case.market_reference_source})"
        )
    tv_crosscheck = ("; ".join(cross_bits) + ".") if cross_bits else "Cross-checks unavailable for this scenario."

    scenario_rows = []
    for name in ("bear", "base", "bull"):
        r = case.scenarios[name]
        scen = case.assumptions.scenarios[name]
        n = len(scen.revenue_growth)
        cagr = (np.prod([1 + g for g in scen.revenue_growth]) ** (1 / n)) - 1
        scenario_rows.append({
            "name": name.title(),
            "cagr": f"{cagr:+.1%}",
            "margin": f"{scen.ebitda_margin[-1]:.1%}",
            "ev": money(r.enterprise_value),
            "equity": money(r.implied_equity),
            "target": _price(r.target_price),
            "upside": _tone_pct(r.upside),
            "source": scen.source,
        })

    analyst_count = sum(1 for s in case.assumptions.scenarios.values() if s.source == "analyst")
    provenance = (
        f"{analyst_count} of 3 scenarios analyst-specified"
        + (f" (file: {Path(str(case.assumptions.path)).name})" if case.assumptions.from_file else "")
        + "; remaining drivers anchored on LTM data. "
        + ("Notes: " + "; ".join(case.notes) + "." if case.notes else "")
    )

    return {
        "css": valuation_case_css(),
        "case_date": pd.Timestamp.today().strftime("%d %b %Y"),
        "company": row.to_dict(),
        "theme": a.theme,
        "peer_group": a.peer_group,
        "currency_label": f"{currency} millions",
        "as_of": pd.Timestamp(row["period"]).strftime("%d %b %Y"),
        "mode": "Public Demo Data" if demo else "Capital IQ Private Export",
        "rec": {"stance": case.recommendation.stance, "headline": case.recommendation.headline,
                "reconciliation": case.recommendation.reconciliation},
        "target_price": _price(base.target_price),
        "current_price": _price(base.current_price),
        "upside": _pct(base.upside),
        "bear_upside": _pct(case.scenarios["bear"].upside, 0),
        "bull_upside": _pct(case.scenarios["bull"].upside, 0),
        "wacc_pct": f"{w.wacc:.1%}",
        "exit_multiple": f"{case.exit_multiple:.1f}x",
        "exit_multiple_source": case.exit_multiple_source,
        "market_reference_multiple": (
            f"{case.market_reference_multiple:.1f}x" if case.market_reference_multiple is not None else "n/a"
        ),
        "market_reference_source": case.market_reference_source,
        "overview": overview,
        "analyst_thesis": {
            "status": thesis.analyst_status if thesis else "",
            "pillars": thesis.investment_pillars if thesis else [],
            "variant_perception": thesis.variant_perception if thesis else "",
            "key_debate": thesis.key_debate if thesis else "",
            "management_questions": thesis.management_questions if thesis else [],
            "source_deck": thesis.source_deck if thesis else "",
            "source_as_of": thesis.source_as_of if thesis else "",
            "source_notes": thesis.source_notes if thesis else "",
        },
        "snapshot": {
            "revenue": money(row.get("revenue_ttm")),
            "growth": _pct(row.get("revenue_yoy_growth")),
            "margin": fmt_pct(row.get("ebitda_margin_ttm")),
            "ebitda": money(row.get("ebitda_ttm")),
            "ev": money(row.get("enterprise_value")),
            "market_cap": money(row.get("market_cap")),
            "multiple": fmt_multiple(row.get("ev_to_ebitda_ttm")),
        },
        "spread_rows": spread_rows,
        "stat_rows": stat_rows,
        "years": list(range(1, horizon + 1)),
        "horizon": horizon,
        "base_source": case.assumptions.scenarios["base"].source,
        "forecast_lines": forecast_lines,
        "nwc_note": ("DSO/DIH/DPO day glidepaths" if case.assumptions.scenarios["base"].nwc_mode == "days"
                     else "projected as % of revenue (AR/inventory/AP days unavailable)"),
        "wacc_rows": wacc_rows,
        "wacc_notes": w.notes,
        "wacc_source_note": ("peer-informed beta" if w.beta_source == "peers" else f"{w.beta_source} beta"),
        "tv_rows": tv_rows,
        "tv_crosscheck": tv_crosscheck,
        "bridge": {
            "pv_explicit": money(base.pv_explicit),
            "pv_terminal": money(base.pv_terminal_exit),
            "ev": money(base.enterprise_value),
            "net_debt": money(base.net_debt),
            "equity": money(base.implied_equity),
            "target": _price(base.target_price),
            "market_cap": money(base.market_cap),
            "tv_pct": f"{base.terminal_pct_of_ev:.0%}" if not np.isnan(base.terminal_pct_of_ev) else "n/a",
        },
        "sens_wm": _grid_context(case.sens_wacc_multiple, "price"),
        "sens_gm": _grid_context(case.sens_growth_margin, "upside"),
        "scenario_rows": scenario_rows,
        "tax_rate": f"{case.assumptions.scenarios['base'].tax_rate:.0%}",
        "perp_growth": f"{case.assumptions.perpetuity_growth:.1%}",
        "provenance_note": provenance,
        "images": case_chart_images(case, df=df),
        "warnings": _case_warnings_with_divergence(case),
        "status_key": assumptions_status(case)[0],
        "status_label": assumptions_status(case)[1],
        "provenance_rows": [
            {"item": r["item"], "value": r["value"], "source": r["source"]}
            for _, r in assumptions_provenance(case).iterrows()
        ],
    }


def generate_valuation_case(
    demo: bool = True,
    company_id: str | None = None,
    output_dir: Path | None = None,
) -> Path | None:
    store = load_store(demo)
    df = load_dataset(demo=demo)
    if company_id is None:
        from src.modeling.metrics import latest_rows
        latest = latest_rows(df)
        company_id = latest.sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]

    if output_dir is None:
        output_dir = REPORTS_SAMPLE_DIR if demo else PRIVATE_DATA_DIR / "reports"
    ensure_dir(output_dir)

    try:
        case = build_valuation_case(df, company_id, store=store)
    except CaseNotApplicableError as exc:
        print(f"Valuation case not applicable for {company_id}: {exc.reason}")
        print(f"  {exc.detail}")
        return None
    context = build_case_context(case, demo, df=df)
    ticker = str(context["company"].get("ticker", company_id)).replace(".SA", "").replace(":", "_")
    output_path = Path(output_dir) / f"valuation_case_{ticker}.html"
    rendered = Template(VALUATION_CASE_TEMPLATE).render(**context)
    rendered = "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n"
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an IB-style valuation case for one company.")
    parser.add_argument("--demo", action="store_true", help="Use public demo dataset.")
    parser.add_argument("--company", default=None, help="company_id (defaults to best-covered name).")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    path = generate_valuation_case(
        demo=args.demo,
        company_id=args.company,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    if path is not None:
        print(f"Valuation case written to {path}")


if __name__ == "__main__":
    main()
