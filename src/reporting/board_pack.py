from __future__ import annotations

import argparse
import base64
from io import BytesIO
from pathlib import Path

import fitz
import matplotlib
import pandas as pd
from jinja2 import Template

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.branding import MPL_FONT_STACK, PALETTE, VERDICT_COLORS
from src.config import (
    DEFAULT_PROCESSED_DATASET,
    DEFAULT_SOURCE_LOG,
    PRIVATE_PROCESSED_DATASET,
    PRIVATE_SOURCE_LOG,
    REPORTS_SAMPLE_DIR,
)
from src.modeling.assessment import build_assessment
from src.modeling.metrics import latest_rows
from src.pipeline.build_dataset import build_dataset
from src.reporting.board_pack_template import HTML_TEMPLATE, board_pack_css
from src.utils import (
    fmt_money,
    fmt_multiple,
    fmt_pct,
    fmt_signed_pct,
    ensure_dir,
    write_csv,
)

plt.rcParams.update({
    "font.family": MPL_FONT_STACK,
    "font.size": 10,
    "axes.edgecolor": PALETTE["line"],
    "axes.labelcolor": PALETTE["slate"],
    "text.color": PALETTE["ink"],
    "xtick.color": PALETTE["slate"],
    "ytick.color": PALETTE["slate"],
})

GEOGRAPHY = {"B3": "Brazil", "NYSE": "United States", "NASDAQ": "United States"}

_SIG_TEXT = {"green": "Green", "yellow": "Amber", "red": "Red", "n/m": "N/M", "n/a": "n/a"}


def load_dataset(demo: bool = True) -> pd.DataFrame:
    if demo or not DEFAULT_PROCESSED_DATASET.exists():
        build_dataset("public-demo")
        dataset_path = DEFAULT_PROCESSED_DATASET
    else:
        dataset_path = PRIVATE_PROCESSED_DATASET if PRIVATE_PROCESSED_DATASET.exists() else DEFAULT_PROCESSED_DATASET
    return pd.read_csv(dataset_path, parse_dates=["period"])


def _default_company(df: pd.DataFrame) -> str:
    latest = latest_rows(df)
    return latest.sort_values(["data_quality_score", "revenue_ttm"], ascending=False)["company_id"].iloc[0]


def _signal_class(signal: str) -> str:
    s = str(signal).lower()
    return "na" if s not in {"green", "yellow", "red"} else s


def _tone_pct(value) -> str:
    if pd.isna(value):
        return "n/a"
    cls = "tone-green" if value > 0 else "tone-red"
    return f'<span class="{cls}">{fmt_signed_pct(value)}</span>'


def _png_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# --- charts (matplotlib, embedded as data URIs) -----------------------------

def _q_labels(history: pd.DataFrame) -> list[str]:
    return [f"Q{pd.Timestamp(p).quarter} {pd.Timestamp(p).year % 100:02d}" for p in history["period"]]


def _history_chart(df: pd.DataFrame, company_id: str, currency: str) -> bytes:
    history = df[df["company_id"] == company_id].sort_values("period")
    x = range(len(history))
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=150)
    fig.patch.set_facecolor("white")
    ax.bar([i - 0.2 for i in x], history["revenue"], width=0.4, color=PALETTE["blue"], label="Revenue")
    ax.bar([i + 0.2 for i in x], history["ebitda"], width=0.4, color=PALETTE["blue_2"], label="EBITDA")
    ax2 = ax.twinx()
    ax2.plot(list(x), history["ebitda_margin"], color=PALETTE["gold"], marker="o", linewidth=2.0, label="EBITDA margin")
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax2.set_ylim(bottom=min(0, history["ebitda_margin"].min()))
    ax2.tick_params(colors=PALETTE["gold"])
    ax.set_title("Quarterly Revenue & EBITDA", fontsize=12, weight="bold", color=PALETTE["navy"], loc="left")
    ax.set_ylabel(f"{currency}m")
    ax.set_xticks(list(x))
    ax.set_xticklabels(_q_labels(history), fontsize=8)
    ax.grid(True, axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, ncols=3, fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.13))
    for spine in ("top",):
        ax.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)
    fig.tight_layout()
    return _save(fig)


def _peer_chart(df: pd.DataFrame, company_id: str) -> bytes:
    peers = latest_rows(df)
    group_col = "peer_group" if "peer_group" in peers.columns else "sector"
    anchor_group = peers.loc[peers["company_id"] == company_id, group_col]
    if not anchor_group.empty:
        same = peers[peers[group_col] == anchor_group.iloc[0]]
        if len(same) >= 3:
            peers = same
    med_x = peers["revenue_yoy_growth"].median(skipna=True)
    med_y = peers["ebitda_margin_ttm"].median(skipna=True)
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=150)
    fig.patch.set_facecolor("white")
    for _, p in peers.iterrows():
        is_anchor = p["company_id"] == company_id
        ax.scatter(p["revenue_yoy_growth"], p["ebitda_margin_ttm"],
                   s=150 if is_anchor else 80,
                   c=PALETTE["green"] if is_anchor else PALETTE["blue"],
                   edgecolors="white", linewidths=1.2, zorder=3)
        ax.annotate(p["ticker"].replace(".SA", ""), (p["revenue_yoy_growth"], p["ebitda_margin_ttm"]),
                    xytext=(5, 4), textcoords="offset points", fontsize=8, color=PALETTE["slate"])
    if pd.notna(med_x):
        ax.axvline(med_x, color=PALETTE["muted_2"], linestyle="--", linewidth=1)
    if pd.notna(med_y):
        ax.axhline(med_y, color=PALETTE["muted_2"], linestyle="--", linewidth=1)
    ax.set_title("Peer Positioning — Growth vs Margin", fontsize=12, weight="bold", color=PALETTE["navy"], loc="left")
    ax.set_xlabel("Revenue YoY growth")
    ax.set_ylabel("TTM EBITDA margin")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.grid(True, alpha=0.18)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _save(fig)


def _save(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buffer.getvalue()


# --- context ----------------------------------------------------------------

def build_context(df: pd.DataFrame, company_id: str | None = None) -> dict:
    if company_id is None:
        company_id = _default_company(df)
    a = build_assessment(df, company_id)
    row = a.row
    currency = row.get("currency", "BRL")
    period = row["period"]

    kpis = []
    for k in a.kpis[:5]:
        kpis.append({
            "label": k.label, "value": k.value, "context": k.context,
            "signal": k.signal, "signal_class": _signal_class(k.signal),
            "signal_text": _SIG_TEXT.get(str(k.signal).lower(), "n/a"),
            "pctile": k.percentile_label,
        })

    # Quarterly performance rows.
    history = df[df["company_id"] == company_id].sort_values("period").tail(8)
    performance_rows = []
    for _, h in history.iterrows():
        performance_rows.append({
            "period": f"Q{pd.Timestamp(h['period']).quarter} {pd.Timestamp(h['period']).year}",
            "revenue": fmt_money(h.get("revenue"), currency),
            "rev_yoy": _tone_pct(h.get("revenue_yoy_growth")),
            "ebitda": fmt_money(h.get("ebitda"), currency),
            "ebitda_mgn": fmt_pct(h.get("ebitda_margin")),
            "fcf": fmt_money(h.get("fcf"), currency),
            "fcf_conv": fmt_pct(h.get("fcf_conversion_ttm")),
            "is_latest": h["period"] == period,
        })

    # Peer table (sorted by EV/EBITDA) + median row.
    peers_sorted = a.peers.sort_values("ev_to_ebitda_ttm")
    peers = []
    for _, p in peers_sorted.iterrows():
        sig = _signal_class(p.get("ev_to_ebitda_ttm_signal", "n/a"))
        peers.append({
            "ticker": p["ticker"].replace(".SA", ""),
            "name": str(p.get("company_name", ""))[:24],
            "growth": _tone_pct(p.get("revenue_yoy_growth")),
            "margin": fmt_pct(p.get("ebitda_margin_ttm")),
            "fcf": fmt_pct(p.get("fcf_conversion_ttm")),
            "leverage": fmt_multiple(p.get("net_debt_to_ebitda_ttm")),
            "ev_rev": fmt_multiple(p.get("ev_to_revenue_ttm")),
            "valuation": f'<span class="cell-pill cell-{sig}">{fmt_multiple(p.get("ev_to_ebitda_ttm"))}</span>',
            "cls": "anchor" if p["company_id"] == company_id else "",
        })
    med = a.peer_median
    peers.append({
        "ticker": "—", "name": "Peer median",
        "growth": fmt_pct(med.get("revenue_yoy_growth")),
        "margin": fmt_pct(med.get("ebitda_margin_ttm")),
        "fcf": fmt_pct(med.get("fcf_conversion_ttm")),
        "leverage": fmt_multiple(med.get("net_debt_to_ebitda_ttm")),
        "ev_rev": fmt_multiple(med.get("ev_to_revenue_ttm")),
        "valuation": fmt_multiple(med.get("ev_to_ebitda_ttm")),
        "cls": "median",
    })

    cashflow_rows = [
        {"label": "CFO (TTM)", "value": fmt_money(row.get("cfo_ttm"), currency)},
        {"label": "Capex (TTM)", "value": fmt_money(row.get("capex_ttm"), currency)},
        {"label": "Free cash flow (TTM)", "value": fmt_money(row.get("fcf_ttm"), currency)},
        {"label": "FCF conversion", "value": fmt_pct(row.get("fcf_conversion_ttm"))},
        {"label": "Capex intensity", "value": fmt_pct(row.get("capex_intensity_ttm"))},
        {"label": "Net debt", "value": fmt_money(row.get("net_debt"), currency)},
        {"label": "Net debt / EBITDA", "value": fmt_multiple(row.get("net_debt_to_ebitda_ttm"))},
        {"label": "Interest coverage", "value": fmt_multiple(row.get("interest_coverage_ttm"))},
    ]
    valuation_rows = [
        {"label": "Market cap", "value": fmt_money(row.get("market_cap"), currency), "median": ""},
        {"label": "Enterprise value", "value": fmt_money(row.get("enterprise_value"), currency), "median": ""},
        {"label": "EV / Revenue", "value": a.valuation["ev_to_revenue"], "median": a.valuation["ev_to_revenue_median"]},
        {"label": "EV / EBITDA", "value": a.valuation["ev_to_ebitda"], "median": a.valuation["ev_to_ebitda_median"]},
        {"label": "P / E", "value": a.valuation["pe"], "median": a.valuation["pe_median"]},
    ]

    flags = [
        {**f, "sev_class": str(f.get("severity", "monitor")).lower()
         if str(f.get("severity", "")).lower() in {"high", "medium", "monitor"} else "monitor"}
        for f in a.red_flags
    ]

    # Legacy keys kept for the PDF renderer.
    performance = [
        {"metric": "Revenue", "latest": fmt_money(row.get("revenue"), currency),
         "ttm": fmt_money(row.get("revenue_ttm"), currency), "ratio": fmt_pct(row.get("revenue_yoy_growth"))},
        {"metric": "EBITDA", "latest": fmt_money(row.get("ebitda"), currency),
         "ttm": fmt_money(row.get("ebitda_ttm"), currency), "ratio": fmt_pct(row.get("ebitda_margin_ttm"))},
        {"metric": "Free Cash Flow", "latest": fmt_money(row.get("fcf"), currency),
         "ttm": fmt_money(row.get("fcf_ttm"), currency), "ratio": fmt_pct(row.get("fcf_conversion_ttm"))},
        {"metric": "Net Debt", "latest": fmt_money(row.get("net_debt"), currency),
         "ttm": "n/a", "ratio": fmt_multiple(row.get("net_debt_to_ebitda_ttm"))},
    ]
    pdf_peers = [
        {"ticker": p["ticker"], "growth": fmt_pct(pr.get("revenue_yoy_growth")),
         "margin": fmt_pct(pr.get("ebitda_margin_ttm")), "fcf": fmt_pct(pr.get("fcf_conversion_ttm")),
         "leverage": fmt_multiple(pr.get("net_debt_to_ebitda_ttm")), "valuation": fmt_multiple(pr.get("ev_to_ebitda_ttm"))}
        for (_, pr), p in zip(peers_sorted.iterrows(), peers)
    ]

    return {
        "css": board_pack_css(),
        "company": row.to_dict(),
        "geography": GEOGRAPHY.get(str(row.get("exchange", "")), str(row.get("exchange", ""))),
        "period_label": pd.Timestamp(period).strftime("%b %Y"),
        "currency_label": f"{currency} millions",
        "as_of": pd.Timestamp(period).strftime("%d %b %Y"),
        "mode": "Capital IQ Private Export",
        "verdict": {
            "label": a.verdict_label, "rationale": a.verdict_rationale,
            "color": VERDICT_COLORS.get(a.verdict_key, PALETTE["navy_3"]),
        },
        "commentary": a.commentary,
        "sponsor_view": a.sponsor_view,
        "kpis": kpis,
        "performance_rows": performance_rows,
        "peers": peers,
        "cashflow_rows": cashflow_rows,
        "valuation_rows": valuation_rows,
        "valuation": a.valuation,
        "positives": a.positives,
        "concerns": a.concerns,
        "flags": flags,
        "questions": a.management_questions,
        "chart_history": _png_uri(_history_chart(df, company_id, currency)),
        "chart_peer": _png_uri(_peer_chart(df, company_id)),
        # Legacy keys for the PDF renderer.
        "performance": performance,
        "pdf_peers": pdf_peers,
        "dataset": df,
        "latest_row": row,
    }


def render_html(context: dict, output_path: Path) -> Path:
    ensure_dir(output_path.parent)
    html = Template(HTML_TEMPLATE).render(**context)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# --- PDF (fixed-layout fallback) --------------------------------------------

def _insert_textbox(page, rect, text, size=10, color=(0.10, 0.13, 0.20)):
    page.insert_textbox(rect, text, fontsize=size, fontname="helv", color=color, align=fitz.TEXT_ALIGN_LEFT)


def _insert_line(page, x, y, text, size=10, color=(0.10, 0.13, 0.20)):
    page.insert_text((x, y), text, fontsize=size, fontname="helv", color=color)


def _draw_metric_card(page, rect, label, value, signal):
    signal_colors = {"green": (0.11, 0.48, 0.30), "yellow": (0.69, 0.47, 0.12),
                     "red": (0.69, 0.20, 0.16), "n/a": (0.42, 0.45, 0.50)}
    page.draw_rect(rect, color=(0.84, 0.87, 0.91), fill=(1, 1, 1), width=0.8)
    page.draw_line((rect.x0, rect.y0), (rect.x1, rect.y0),
                   color=signal_colors.get(str(signal).lower(), (0.42, 0.45, 0.50)), width=2.2)
    _insert_line(page, rect.x0 + 10, rect.y0 + 22, label.upper(), 7.5, (0.36, 0.42, 0.50))
    _insert_line(page, rect.x0 + 10, rect.y0 + 48, value, 15, (0.06, 0.13, 0.20))
    _insert_line(page, rect.x0 + 10, rect.y0 + 70, _SIG_TEXT.get(str(signal).lower(), "n/a").upper(), 8,
                 signal_colors.get(str(signal).lower(), (0.42, 0.45, 0.50)))


def render_pdf(context: dict, output_path: Path) -> Path:
    ensure_dir(output_path.parent)
    navy = (0.06, 0.15, 0.26)
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)

    page.draw_rect(fitz.Rect(0, 0, 842, 92), color=navy, fill=navy)
    _insert_line(page, 36, 38, f"{context['company']['company_name']} - Investment Watchlist Board Pack", 19, (1, 1, 1))
    _insert_line(page, 36, 60, f"{context['company']['ticker']} | {context['company']['sector']} | "
                 f"{context['period_label']} | {context['currency_label']}", 9.5, (0.78, 0.85, 0.93))
    verdict = context["verdict"]
    _insert_line(page, 36, 80, f"CONCLUSION: {verdict['label'].upper()} - {verdict['rationale']}", 9,
                 (0.88, 0.78, 0.45))

    card_width = 184
    for index, kpi in enumerate(context["kpis"][:4]):
        x0 = 36 + index * (card_width + 12)
        _draw_metric_card(page, fitz.Rect(x0, 108, x0 + card_width, 190),
                          kpi["label"], kpi["value"], kpi["signal"])

    page.insert_image(fitz.Rect(36, 206, 415, 374), stream=base64.b64decode(context["chart_history"].split(",")[1]))
    page.insert_image(fitz.Rect(431, 206, 806, 374), stream=base64.b64decode(context["chart_peer"].split(",")[1]))

    _insert_textbox(page, fitz.Rect(36, 388, 405, 408), "Red Flags & Management Questions", 12, (0.09, 0.20, 0.40))
    y = 414
    for flag in context["flags"][:4]:
        text = f"{flag['severity']} - {flag['area']}: {flag['observation']} {flag['management_question']}"
        _insert_textbox(page, fitz.Rect(36, y, 405, y + 40), text, 8.5)
        y += 42

    _insert_textbox(page, fitz.Rect(431, 388, 806, 408), "Peer Snapshot (sorted by EV/EBITDA)", 12, (0.09, 0.20, 0.40))
    y = 414
    headers = f"{'Company':<12}{'Growth':>9}{'Margin':>9}{'FCF':>9}{'ND/EBITDA':>12}{'EV/EBITDA':>12}"
    _insert_textbox(page, fitz.Rect(431, y, 806, y + 14), headers, 8, (0.36, 0.42, 0.50))
    y += 16
    for peer in context["pdf_peers"][:7]:
        text = (f"{peer['ticker']:<12}{peer['growth']:>9}{peer['margin']:>9}"
                f"{peer['fcf']:>9}{peer['leverage']:>12}{peer['valuation']:>12}")
        _insert_textbox(page, fitz.Rect(431, y, 806, y + 14), text, 8)
        y += 16

    _insert_textbox(page, fitz.Rect(36, 566, 806, 584),
                    "Raw Capital IQ exports must stay in data_private/ and outside Git. Not investment advice.",
                    8, (0.42, 0.45, 0.50))
    doc.save(output_path)
    doc.close()
    return output_path


def generate_board_pack(demo: bool = True, company_id: str | None = None,
                        output_dir: Path | None = None, output_format: str = "both") -> dict[str, Path]:
    # Private outputs must never land in the committed reports/sample folder.
    if output_dir is None:
        from src.config import PRIVATE_DATA_DIR
        output_dir = REPORTS_SAMPLE_DIR if demo else PRIVATE_DATA_DIR / "reports"
    df = load_dataset(demo=demo)
    context = build_context(df, company_id)
    context["mode"] = "Public Demo Data" if demo else "Capital IQ Private Export"
    ensure_dir(output_dir)

    outputs: dict[str, Path] = {}
    if output_format in {"html", "both"}:
        outputs["html"] = render_html(context, output_dir / "board_pack.html")
    if output_format in {"pdf", "both"}:
        outputs["pdf"] = render_pdf(context, output_dir / "board_pack.pdf")

    source_log_path = DEFAULT_SOURCE_LOG if demo else PRIVATE_SOURCE_LOG
    if source_log_path.exists():
        write_csv(pd.read_csv(source_log_path), output_dir / "source_log.csv")
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an investment watchlist board pack.")
    parser.add_argument("--demo", action="store_true", help="Use public demo dataset.")
    parser.add_argument("--company", default=None, help="Optional company_id to report.")
    parser.add_argument("--format", choices=["html", "pdf", "both"], default="both")
    parser.add_argument("--output-dir", default=None, help="Defaults to reports/sample (demo) or data_private/reports (private).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = generate_board_pack(demo=args.demo, company_id=args.company,
                                  output_dir=Path(args.output_dir) if args.output_dir else None,
                                  output_format=args.format)
    for kind, path in outputs.items():
        print(f"{kind.upper()} board pack written to {path}")


if __name__ == "__main__":
    main()
