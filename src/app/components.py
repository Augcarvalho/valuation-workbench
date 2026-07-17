"""Reusable institutional UI components for the Streamlit dashboard.

These render the design-system classes defined in :mod:`src.app.theme`. They
take plain data (or :class:`src.modeling.assessment.Kpi` objects) and emit HTML
blocks, keeping ``streamlit_app.py`` focused on page composition.
"""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.modeling.assessment import Kpi

GEOGRAPHY = {
    "B3": "Brazil",
    "BOVESPA": "Brazil",
    "NYSE": "United States",
    "NASDAQ": "United States",
    "NasdaqGS": "United States",
    "NasdaqGM": "United States",
}


# --- small helpers ----------------------------------------------------------

def _sig_class(signal: str) -> str:
    s = str(signal).lower()
    return {"green": "green", "yellow": "yellow", "red": "red"}.get(s, "na")


def _sig_text(signal: str) -> str:
    s = str(signal).lower()
    # "n/m" = not meaningful for this business model (e.g. EV/EBITDA for a lender).
    return {"green": "Green", "yellow": "Amber", "red": "Red", "n/m": "N/M"}.get(s, "n/a")


def quarter_label(period) -> str:
    ts = pd.Timestamp(period)
    return f"Q{ts.quarter} {ts.year}"


def as_of_label(period) -> str:
    ts = pd.Timestamp(period)
    return f"{quarter_label(period)} | {ts.strftime('%d %b %Y')}"


# --- header band ------------------------------------------------------------

def header_band(row: pd.Series, demo: bool) -> None:
    name = escape(str(row.get("company_name", "Investment Candidate")))
    ticker = escape(str(row.get("ticker", "")))
    peer_group = escape(str(row.get("peer_group", row.get("sector", ""))))
    exchange = str(row.get("exchange", ""))
    currency = escape(str(row.get("currency", "LC")))
    geo = GEOGRAPHY.get(exchange, exchange or "n/a")
    period = row.get("period")

    mode_cls = "pe-mode-demo" if demo else "pe-mode-private"
    mode_txt = "Public Demo Data" if demo else "Capital IQ - Private"

    meta = [
        ("Peer Group", peer_group or "n/a"),
        ("Listing", f"{escape(exchange)} | {geo}"),
        ("Reporting Period", quarter_label(period)),
        ("Currency", f"{currency} millions"),
        ("Financials Through", pd.Timestamp(period).strftime("%d %b %Y")),
    ]
    meta_html = "".join(
        f'<div class="pe-meta-item"><div class="pe-meta-label">{escape(k)}</div>'
        f'<div class="pe-meta-value">{v}</div></div>'
        for k, v in meta
    )

    st.markdown(
        f"""
        <div class="pe-header">
          <div class="pe-header-top">
            <div>
              <div class="kicker">Investment Watchlist | Quarterly Review</div>
              <h1>{name}<span class="ticker">{ticker}</span></h1>
            </div>
            <span class="pe-mode-pill {mode_cls}">{mode_txt}</span>
          </div>
          <div class="pe-header-meta">{meta_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- section header ---------------------------------------------------------

def section(title: str, note: str = "") -> None:
    note_html = f'<span class="pe-section-note">{escape(note)}</span>' if note else ""
    st.markdown(
        f'<div class="pe-section"><div class="pe-section-bar"></div>'
        f"<h2>{escape(title)}</h2>{note_html}</div>",
        unsafe_allow_html=True,
    )


# --- KPI cards --------------------------------------------------------------

def _kpi_card_html(k: Kpi) -> str:
    sig = _sig_class(k.signal)
    pill = f'<span class="pe-pill sig-{sig}">{_sig_text(k.signal)}</span>'

    if k.delta:
        tone = "good" if k.delta_good is True else ("bad" if k.delta_good is False else "flat")
        delta_html = f'<span class="pe-delta {tone}">{escape(k.delta)}</span>'
    else:
        delta_html = '<span class="pe-delta flat">--</span>'

    pctile_html = (
        f'<div class="pe-kpi-pctile">{escape(k.percentile_label)}</div>'
        if k.percentile_label
        else '<div class="pe-kpi-pctile">&nbsp;</div>'
    )

    return (
        f'<div class="pe-kpi sig-{sig}">'
        f'<div class="pe-kpi-label">{escape(k.label)}</div>'
        f'<div class="pe-kpi-value">{escape(k.value)}</div>'
        f'<div class="pe-kpi-context">{escape(k.context)}</div>'
        f'<div class="pe-kpi-foot">{pill}{delta_html}</div>'
        f"{pctile_html}"
        f"</div>"
    )


def kpi_grid(kpis: list[Kpi], columns: int = 5) -> None:
    cards = "".join(_kpi_card_html(k) for k in kpis)
    grid_class = f"cols-{columns}" if 1 <= columns <= 6 else "cols-auto"
    st.markdown(
        f'<div class="pe-kpi-grid {grid_class}">{cards}</div>',
        unsafe_allow_html=True,
    )


# --- verdict banner ---------------------------------------------------------

def verdict_banner(assessment) -> None:
    from src.branding import PALETTE, VERDICT_COLORS

    color = VERDICT_COLORS.get(assessment.verdict_key, PALETTE["sage"])
    st.markdown(
        f"""
        <div class="pe-verdict">
          <div class="pe-verdict-flag" style="background:{color}"></div>
          <div class="pe-verdict-body">
            <div class="pe-verdict-kicker">Monitoring Conclusion</div>
            <div class="pe-verdict-label" style="color:{color}">{escape(assessment.verdict_label)}</div>
            <div class="pe-verdict-rationale">{escape(assessment.verdict_rationale)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- memo / list blocks -----------------------------------------------------

def memo(title: str, text: str) -> None:
    st.markdown(
        f'<div class="pe-memo"><h4>{escape(title)}</h4><p>{escape(text)}</p></div>',
        unsafe_allow_html=True,
    )


def bullet_list(title: str, items: list[str], kind: str = "pos") -> None:
    lis = "".join(f"<li>{escape(i)}</li>" for i in items)
    st.markdown(
        f'<div class="pe-list {kind}"><h4>{escape(title)}</h4><ul>{lis}</ul></div>',
        unsafe_allow_html=True,
    )


def flag_list(red_flags: list[dict]) -> None:
    blocks = []
    for f in red_flags:
        sev = str(f.get("severity", "Monitor")).lower()
        sev_cls = sev if sev in {"high", "medium", "monitor"} else "monitor"
        question = str(f.get("management_question", "") or "").strip()
        q_html = f'<div class="pe-flag-q">&gt; {escape(question)}</div>' if question else ""
        blocks.append(
            f'<div class="pe-flag sev-{sev_cls}">'
            f'<div class="pe-flag-head"><span class="pe-flag-sev">{escape(f.get("severity", ""))}</span>'
            f'<span class="pe-flag-area">{escape(f.get("area", ""))}</span></div>'
            f'<div class="pe-flag-obs">{escape(f.get("observation", ""))}</div>'
            f"{q_html}"
            f"</div>"
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)


def footnote(text: str) -> None:
    st.markdown(f'<div class="pe-foot">{text}</div>', unsafe_allow_html=True)


# --- dense HTML tables ------------------------------------------------------

def html_table(headers: list[str], rows: list[list[str]], row_classes: list[str] | None = None,
               numeric_from: int = 1, wrap: bool = False, dense: bool = False) -> None:
    """Render a compact board-pack table. ``rows`` cells may contain safe HTML.

    ``wrap=True`` lets long text cells wrap instead of forcing one line
    (used for audit findings and other prose-heavy columns).
    """
    thead = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = []
    row_classes = row_classes or [""] * len(rows)
    for cls, cells in zip(row_classes, rows):
        tds = []
        for i, c in enumerate(cells):
            num = " class='num'" if i >= numeric_from else ""
            tds.append(f"<td{num}>{c}</td>")
        body.append(f'<tr class="{cls}">' + "".join(tds) + "</tr>")
    classes = ["pe-table"]
    if wrap:
        classes.append("wrap")
    if dense:
        classes.append("dense")
    table_cls = " ".join(classes)
    st.markdown(
        f'<div class="pe-table-wrap"><table class="{table_cls}"><thead><tr>{thead}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def cell_pill(text: str, signal: str) -> str:
    return f'<span class="cell-pill cell-{_sig_class(signal)}">{escape(text)}</span>'


# --- multi-multiple valuation scorecard --------------------------------------

_INTERP_CLASS = {"cheap": "cheap", "fair": "fair", "expensive": "expensive",
                 "distorted": "distorted", "not meaningful": "nm"}


def regime_zone(pct: float | None) -> str:
    if pct is None:
        return "no history"
    if pct <= 0.25:
        return "bottom quartile"
    if pct < 0.45:
        return "below median"
    if pct <= 0.55:
        return "near median"
    if pct < 0.75:
        return "above median"
    return "top quartile"


def _regime_bar_html(pct: float | None) -> str:
    """Horizontal percentile bar vs own history: quartile zones + marker."""
    if pct is None:
        return '<div class="pe-regime-empty">no usable multiple history</div>'
    left = max(1.5, min(98.5, pct * 100))
    return (
        '<div class="pe-regime">'
        '<span class="pe-regime-q"></span><span class="pe-regime-q q2"></span>'
        '<span class="pe-regime-q q3"></span><span class="pe-regime-q"></span>'
        f'<span class="pe-regime-marker" style="left:{left:.1f}%"></span>'
        "</div>"
        f'<div class="pe-regime-label">{escape(regime_zone(pct))} · P{pct * 100:.0f} of own history</div>'
    )


def multiple_scorecard(summary: list[dict]) -> None:
    """Institutional tile per multiple: value, peer gap, regime bar, role."""
    tiles = []
    for m in summary:
        interp = m["interpretation"]
        cls = _INTERP_CLASS.get(interp, "nm")
        nm = interp == "not meaningful"
        value = f"{m['current']:.1f}x" if (m["current"] is not None and not nm) else "N/M"
        if m["peer_median"] is not None and m["premium"] is not None and not nm:
            peers_line = (f"vs peers {m['peer_median']:.1f}x "
                          f"<b>({m['premium']:+.0%})</b> · n={m['n_peers']}")
        elif not nm and m["peer_median"] is not None:
            peers_line = f"peer adj. median {m['peer_median']:.1f}x"
        else:
            peers_line = escape(m["role_reason"])
        regime = _regime_bar_html(m.get("hist_percentile")) if not nm else ""
        tiles.append(
            f'<div class="pe-mult-tile mult-{cls}">'
            f'<div class="pe-mult-head"><span class="pe-mult-name">{escape(m["label"])}</span>'
            f'<span class="pe-mult-role role-{m["role"]}">{escape(m["role_label"])}</span></div>'
            f'<div class="pe-mult-value">{value}</div>'
            f'<div class="pe-mult-peers">{peers_line}</div>'
            f"{regime}"
            f'<div class="pe-mult-interp">{escape(interp.upper())}</div>'
            f"</div>"
        )
    st.markdown(f'<div class="pe-mult-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)


def business_model_map(summary: list[dict], business_model: str) -> None:
    """Which multiples matter for THIS company, and why - dynamic, not generic."""
    rows = "".join(
        f'<div class="pe-mmap-row"><span class="pe-mult-role role-{m["role"]}">{escape(m["role_label"])}</span>'
        f'<span class="pe-mmap-name">{escape(m["label"])}</span>'
        f'<span class="pe-mmap-why">{escape(m["role_reason"])}</span></div>'
        for m in summary
    )
    st.markdown(
        f'<div class="pe-mmap"><div class="pe-mmap-title">Multiple selection - '
        f'{escape(business_model)} model</div>{rows}</div>',
        unsafe_allow_html=True,
    )
