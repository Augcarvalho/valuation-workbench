"""Institutional CSS theme for the Streamlit dashboard.

All visual tokens come from :data:`src.branding.PALETTE` so the dashboard,
charts, and board pack stay in lock-step. The goal is a dense investment
watchlist surface: charcoal chrome, warm paper, sage/copper data colors, and
subtle gold rules instead of a blue corporate dashboard.
"""

from __future__ import annotations

import streamlit as st

from src.branding import FONT_MONO, FONT_SANS, FONT_SERIF, PALETTE


def _root_vars() -> str:
    tokens = "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in PALETTE.items())
    fonts = (
        f"  --font-sans: {FONT_SANS};\n"
        f"  --font-serif: {FONT_SERIF};\n"
        f"  --font-mono: {FONT_MONO};\n"
    )
    return ":root{\n" + tokens + "\n" + fonts + "}"


# Plain (non-f) string: CSS braces are literal here.
_CSS_BODY = """
/* ---- Canvas ---------------------------------------------------------- */
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-sans);
}
[data-testid="stAppViewContainer"] .block-container {
  max-width: 1260px;
  padding-top: 1.1rem;
  padding-bottom: 2.4rem;
  padding-left: 2.2rem;
  padding-right: 2.2rem;
}
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none; }

* { font-variant-numeric: tabular-nums; }

/* ---- Native Streamlit controls -------------------------------------- */
button[kind], .stDownloadButton button, div[data-testid="stButton"] button {
  border-radius: 5px;
  border: 1px solid rgba(168,132,63,.42);
  background: var(--navy);
  color: #f7f2e7;
  font-weight: 700;
  letter-spacing: .02em;
  box-shadow: none;
}
button[kind]:hover, .stDownloadButton button:hover, div[data-testid="stButton"] button:hover {
  border-color: var(--gold);
  background: #2a302b;
  color: #ffffff;
}
button[kind]:focus-visible, .stDownloadButton button:focus-visible,
div[data-testid="stButton"] button:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 1px;
}
button[kind]:disabled, .stDownloadButton button:disabled,
div[data-testid="stButton"] button:disabled {
  background: var(--panel-alt);
  border-color: var(--line);
  color: var(--muted-2);
  cursor: not-allowed;
}
/* Button labels live inside stMarkdownContainer, so the global contrast guard
   ([data-testid="stMain"] ... p { color: var(--ink) }) outranks the plain
   `button p` selector and paints dark ink on the navy button. Inherit wins. */
button[kind] p, .stDownloadButton button p, div[data-testid="stButton"] button p,
[data-testid="stMain"] button[kind] p,
[data-testid="stMain"] div[data-testid="stButton"] button p { color: inherit !important; }
[data-baseweb="select"] > div {
  border-radius: 5px;
  border-color: var(--line);
  background: var(--panel);
}

/* ---- Sidebar --------------------------------------------------------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--navy) 0%, var(--navy-2) 62%, #181b19 100%);
  border-right: 1px solid rgba(168,132,63,.24);
}
[data-testid="stSidebar"] * { color: #eee8dd; }
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
.sb-brand {
  font-family: var(--font-sans);
  font-weight: 750;
  font-size: 17px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #fffaf0;
  line-height: 1.25;
}
.sb-brand-rule { height: 2px; width: 38px; background: var(--gold); margin: 10px 0 4px; }
.sb-sub { font-size: 11.5px; color: #bdb5a6; letter-spacing: .04em; }
.sb-group {
  font-size: 10.5px; font-weight: 750; letter-spacing: .16em;
  text-transform: uppercase; color: #a88e55;
  margin: 18px 0 4px;
}
[data-testid="stSidebar"] hr { border-color: rgba(216,208,193,.20); margin: 12px 0; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: #191d1a; border-color: rgba(168,132,63,.40); color: #fffaf0;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] input {
  color: #fffaf0;
}
[data-testid="stSidebar"] label { color: #d7d0c3; font-size: 13px; }
[data-testid="stSidebar"] code {
  background: rgba(255,255,255,.08);
  color: #f2e7ce;
  border-radius: 3px;
  padding: 1px 4px;
}

/* Radio -> vertical nav rail */
[data-testid="stSidebar"] [role="radiogroup"] { gap: 1px; }
[data-testid="stSidebar"] [role="radiogroup"] > label {
  display: flex; align-items: center;
  padding: 7px 10px; margin: 0; border-radius: 5px;
  border-left: 2px solid transparent;
  font-size: 13.5px; color: #d4cdc0;
  transition: background .12s ease, border-color .12s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] > label:hover { background: rgba(168,132,63,.10); }
[data-testid="stSidebar"] [role="radiogroup"] > label[data-checked="true"],
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
  background: rgba(168,132,63,.16);
  border-left: 2px solid var(--gold);
  color: #fffaf0; font-weight: 650;
}
[data-testid="stSidebar"] [role="radiogroup"] svg { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child { display: none; }

/* ---- Top header band ------------------------------------------------- */
.pe-header {
  background: linear-gradient(104deg, var(--navy) 0%, var(--navy-2) 68%, var(--sage) 155%);
  border: 1px solid #171a18;
  border-radius: 8px;
  padding: 16px 22px;
  margin-bottom: 6px;
  color: #fffaf0;
  box-shadow: 0 8px 22px rgba(31,36,33,.12);
}
.pe-header-top { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; }
.pe-header h1 { margin: 0; font-size: 23px; font-weight: 750; letter-spacing: 0; color: #fffaf0; }
.pe-header .ticker {
  font-family: var(--font-mono); font-size: 13px; color: #e7ddc8;
  background: rgba(255,253,247,.08); border: 1px solid rgba(255,253,247,.12);
  padding: 2px 8px; border-radius: 4px; margin-left: 10px;
}
.pe-header .kicker { font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: #c2ad73; margin-bottom: 6px; }
.pe-header-meta { display: flex; flex-wrap: wrap; gap: 0; margin-top: 14px; border-top: 1px solid rgba(255,253,247,.14); padding-top: 10px; }
.pe-meta-item { padding-right: 26px; margin-right: 22px; border-right: 1px solid rgba(255,253,247,.13); }
.pe-meta-item:last-child { border-right: none; }
.pe-meta-label { font-size: 9.5px; letter-spacing: .14em; text-transform: uppercase; color: #b4aa9a; }
.pe-meta-value { font-size: 13.5px; font-weight: 650; color: #f7f2e7; margin-top: 2px; }
.pe-mode-pill {
  font-size: 10.5px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase;
  padding: 3px 9px; border-radius: 999px; align-self: flex-start;
}
.pe-mode-demo { background: rgba(168,132,63,.22); color: #eed7a1; border: 1px solid rgba(168,132,63,.55); }
.pe-mode-private { background: rgba(104,122,97,.24); color: #cddcc6; border: 1px solid rgba(104,122,97,.58); }

/* ---- Section headers ------------------------------------------------- */
.pe-section { display: flex; align-items: center; gap: 10px; margin: 22px 0 10px; }
.pe-section-bar { width: 4px; height: 17px; background: var(--gold); border-radius: 2px; }
.pe-section h2 { margin: 0; font-size: 15px; font-weight: 750; letter-spacing: .04em; text-transform: uppercase; color: var(--navy); }
.pe-section .pe-section-note { font-size: 12px; color: var(--muted); font-weight: 500; letter-spacing: .01em; }

/* ---- KPI cards ------------------------------------------------------- */
.pe-kpi-grid {
  display: grid;
  gap: 12px;
  align-items: stretch;
}
.pe-kpi-grid.cols-1 { grid-template-columns: 1fr; }
.pe-kpi-grid.cols-2 { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.pe-kpi-grid.cols-3 { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.pe-kpi-grid.cols-4,
.pe-kpi-grid.cols-5,
.pe-kpi-grid.cols-6,
.pe-kpi-grid.cols-auto { grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); }
.pe-kpi {
  background: linear-gradient(180deg, var(--panel) 0%, #fbf7ee 100%);
  border: 1px solid var(--line);
  border-top: 3px solid var(--line);
  border-radius: 7px;
  padding: 13px 15px 14px;
  min-height: 132px;
  display: flex; flex-direction: column;
  box-shadow: 0 1px 2px rgba(31,36,33,.06);
}
.pe-kpi.sig-green { border-top-color: var(--green); }
.pe-kpi.sig-yellow { border-top-color: var(--amber); }
.pe-kpi.sig-red { border-top-color: var(--red); }
.pe-kpi.sig-na { border-top-color: var(--muted-2); }
.pe-kpi-label { font-size: 10.5px; font-weight: 750; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.pe-kpi-value {
  font-size: clamp(18px, 1.8vw, 23px);
  font-weight: 750;
  color: var(--ink);
  line-height: 1.08;
  margin-top: 8px;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}
.pe-kpi-context { font-size: 11.5px; color: var(--muted); margin-top: 5px; line-height: 1.3; }
.pe-kpi-foot { display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: 10px; gap: 6px; }
.pe-pill {
  display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: .08em;
  text-transform: uppercase; padding: 3px 8px; border-radius: 4px;
}
.pe-pill.sig-green { background: var(--green-soft); color: var(--green); }
.pe-pill.sig-yellow { background: var(--amber-soft); color: var(--amber); }
.pe-pill.sig-red { background: var(--red-soft); color: var(--red); }
.pe-pill.sig-na { background: var(--panel-alt); color: var(--muted); }
.pe-delta { font-size: 11.5px; font-weight: 750; font-family: var(--font-mono); }
.pe-delta.good { color: var(--green); }
.pe-delta.bad { color: var(--red); }
.pe-delta.flat { color: var(--muted); }
.pe-kpi-pctile { font-size: 10.5px; color: var(--muted-2); margin-top: 6px; letter-spacing: .02em; }

/* ---- Verdict banner -------------------------------------------------- */
.pe-verdict {
  display: flex; align-items: stretch; gap: 0;
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden;
  background: var(--panel); box-shadow: 0 1px 2px rgba(31,36,33,.06); margin-top: 4px;
}
.pe-verdict-flag { width: 6px; }
.pe-verdict-body { padding: 13px 18px; flex: 1; }
.pe-verdict-kicker { font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: var(--muted); }
.pe-verdict-label { font-size: 19px; font-weight: 800; letter-spacing: 0; margin-top: 2px; }
.pe-verdict-rationale { font-size: 13px; color: var(--slate); margin-top: 3px; line-height: 1.4; }

/* ---- Memo / commentary boxes ---------------------------------------- */
.pe-memo {
  background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--sage);
  border-radius: 6px; padding: 15px 18px; margin-top: 4px;
}
.pe-memo h4 { margin: 0 0 7px; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: var(--navy); font-weight: 750; }
.pe-memo p { font-family: var(--font-serif); font-size: 14.5px; line-height: 1.55; color: var(--slate); margin: 0; }

.pe-list { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px 12px 14px; height: 100%; }
.pe-list h4 { margin: 0 0 9px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; font-weight: 750; }
.pe-list.pos h4 { color: var(--green); }
.pe-list.con h4 { color: var(--red); }
.pe-list.q h4 { color: var(--navy); }
.pe-list ul { margin: 0; padding: 0; list-style: none; }
.pe-list li { font-size: 12.8px; color: var(--slate); line-height: 1.4; padding: 6px 0 6px 16px; border-bottom: 1px solid var(--line-soft); position: relative; }
.pe-list li:last-child { border-bottom: none; }
.pe-list li:before { content: ""; position: absolute; left: 2px; top: 12px; width: 5px; height: 5px; border-radius: 50%; }
.pe-list.pos li:before { background: var(--green); }
.pe-list.con li:before { background: var(--red); }
.pe-list.q li:before { background: var(--sage); }
.pe-list.q li { counter-increment: q; padding-left: 24px; }
.pe-list.q li:before { display: none; }
.pe-list.q li:after { content: "Q" counter(q); position: absolute; left: 0; top: 6px; font-family: var(--font-mono); font-size: 10.5px; font-weight: 750; color: var(--sage); }

/* ---- Flag rows ------------------------------------------------------- */
.pe-flag { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--muted-2); border-radius: 6px; padding: 10px 13px; margin-bottom: 8px; }
.pe-flag.sev-high { border-left-color: var(--red); }
.pe-flag.sev-medium { border-left-color: var(--amber); }
.pe-flag.sev-monitor { border-left-color: var(--green); }
.pe-flag-head { display: flex; align-items: center; gap: 8px; }
.pe-flag-sev { font-size: 9.5px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; padding: 2px 6px; border-radius: 3px; color: #fffaf0; }
.pe-flag.sev-high .pe-flag-sev { background: var(--red); }
.pe-flag.sev-medium .pe-flag-sev { background: var(--amber); }
.pe-flag.sev-monitor .pe-flag-sev { background: var(--green); }
.pe-flag-area { font-size: 12.5px; font-weight: 750; color: var(--ink); }
.pe-flag-obs { font-size: 12.5px; color: var(--slate); margin: 5px 0 3px; line-height: 1.4; }
.pe-flag-q { font-size: 12.5px; color: var(--sage); font-style: italic; line-height: 1.4; }

/* ---- Dense HTML tables ---------------------------------------------- */
.pe-table-wrap { background: var(--panel); border: 1px solid var(--line); border-radius: 7px; overflow-x: auto; }
table.pe-table { width: 100%; border-collapse: collapse; font-size: 12.6px; }
table.pe-table th, table.pe-table td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
table.pe-table th { background: var(--panel-alt); color: var(--muted); font-weight: 750; font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; border-bottom: 1px solid var(--line); }
table.pe-table th:first-child, table.pe-table td:first-child { text-align: left; }
table.pe-table td.num { font-family: var(--font-mono); }
table.pe-table.wrap th, table.pe-table.wrap td { white-space: normal; }
table.pe-table.wrap td { line-height: 1.45; max-width: 520px; }
/* Prose columns read left-aligned; wrap tables carry text, not figures. */
table.pe-table.wrap td:not(.num), table.pe-table.wrap th { text-align: left; }
table.pe-table tr.anchor td { background: var(--sage-soft); font-weight: 750; color: var(--navy); }
table.pe-table tr.median td { background: #f3eadb; font-style: italic; color: var(--slate); }
table.pe-table td .cell-pill { font-size: 10px; font-weight: 800; padding: 1px 6px; border-radius: 3px; }
.cell-green { background: var(--green-soft); color: var(--green); }
.cell-yellow { background: var(--amber-soft); color: var(--amber); }
.cell-red { background: var(--red-soft); color: var(--red); }
.tone-green { color: var(--green); font-weight: 750; }
.tone-red { color: var(--red); font-weight: 750; }

/* ---- Multi-multiple valuation scorecard ------------------------------ */
.pe-mult-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 6px 0 4px; }
@media (max-width: 1100px) { .pe-mult-grid { grid-template-columns: repeat(2, 1fr); } }
.pe-mult-tile { background: var(--panel); border: 1px solid var(--line); border-left-width: 4px;
  border-radius: 7px; padding: 12px 14px 10px; }
.pe-mult-tile.mult-cheap { border-left-color: var(--green); }
.pe-mult-tile.mult-fair { border-left-color: var(--sage); }
.pe-mult-tile.mult-expensive { border-left-color: var(--amber); }
.pe-mult-tile.mult-distorted { border-left-color: var(--red); }
.pe-mult-tile.mult-nm { border-left-color: var(--line); opacity: .78; }
.pe-mult-head { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; }
.pe-mult-name { font-size: 11px; font-weight: 800; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.pe-mult-role { font-size: 9px; font-weight: 800; letter-spacing: .05em; text-transform: uppercase;
  padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
.role-primary { background: var(--navy); color: #f7f2e7; }
.role-secondary { background: var(--sage-soft); color: var(--navy); }
.role-cross-check { background: var(--panel-alt); color: var(--muted); border: 1px solid var(--line); }
.role-not_meaningful { background: var(--panel-alt); color: var(--muted-2); border: 1px dashed var(--line); }
.pe-mult-value { font-size: 26px; font-weight: 800; color: var(--navy); font-family: var(--font-mono);
  margin: 4px 0 0; line-height: 1.15; }
.pe-mult-peers { font-size: 11.5px; color: var(--slate); margin: 2px 0 8px; min-height: 16px; }
.pe-mult-peers b { color: var(--ink); }
.pe-mult-interp { font-size: 10px; font-weight: 800; letter-spacing: .08em; color: var(--muted); margin-top: 8px; }
.mult-cheap .pe-mult-interp { color: var(--green); }
.mult-expensive .pe-mult-interp { color: var(--amber); }
.mult-distorted .pe-mult-interp { color: var(--red); }
.pe-regime { position: relative; display: flex; height: 8px; border-radius: 4px; overflow: hidden; }
.pe-regime-q { flex: 1; background: var(--panel-alt); border-right: 1px solid var(--line); }
.pe-regime-q.q2, .pe-regime-q.q3 { background: var(--sage-soft); }
.pe-regime-q:last-child { border-right: none; }
.pe-regime-marker { position: absolute; top: -2px; width: 3px; height: 12px; background: var(--navy);
  border-radius: 1px; transform: translateX(-50%); }
.pe-regime-label { font-size: 10px; color: var(--muted-2); margin-top: 3px; }
.pe-regime-empty { font-size: 10px; color: var(--muted-2); margin: 6px 0 3px; }
/* Business-model multiple map */
.pe-mmap { background: var(--panel); border: 1px solid var(--line); border-radius: 7px; padding: 12px 14px; }
.pe-mmap-title { font-size: 11px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 8px; }
.pe-mmap-row { display: flex; align-items: baseline; gap: 10px; padding: 5px 0; border-top: 1px solid var(--line-soft); }
.pe-mmap-row .pe-mult-role { flex: 0 0 96px; text-align: center; }
.pe-mmap-name { flex: 0 0 96px; font-size: 12.5px; font-weight: 750; color: var(--ink); }
.pe-mmap-why { font-size: 12px; color: var(--slate); line-height: 1.4; }

/* ---- Caption / footnotes -------------------------------------------- */
.pe-foot { font-size: 11px; color: var(--muted-2); margin-top: 8px; line-height: 1.5; }
.pe-tag { display:inline-block; font-size:10px; font-weight:750; letter-spacing:.06em; text-transform:uppercase; padding:2px 7px; border-radius:4px; background:var(--panel-alt); color:var(--muted); border:1px solid var(--line); }

/* ---- Contrast guard: dark text on light surfaces (main area) --------- */
/* Sidebar stays dark-chrome; everything in the main container must render
   ink-on-cream regardless of the user's OS/browser dark-mode preference. */
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"] > div,
[data-testid="stMain"] input, [data-testid="stMain"] textarea {
  background: var(--panel) !important;
  color: var(--ink) !important;
  border-color: var(--line) !important;
}
[data-testid="stMain"] [data-baseweb="select"] svg { fill: var(--muted); }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li,
[data-baseweb="menu"] ul, [data-baseweb="menu"] li {
  background: var(--panel) !important;
  color: var(--ink) !important;
}
[data-baseweb="popover"] li:hover, [data-baseweb="menu"] li:hover { background: var(--panel-alt) !important; }
[data-testid="stMain"] label, [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [role="radiogroup"] label p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p { color: var(--ink); }
[data-testid="stMain"] [data-testid="stExpander"] summary,
[data-testid="stMain"] [data-testid="stExpander"] summary p { color: var(--ink) !important; }
[data-testid="stMain"] button[kind="secondary"], [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {
  background: var(--panel); color: var(--ink); border: 1px solid var(--line);
}
[data-testid="stMain"] [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
  background: var(--sage-soft) !important; color: var(--ink) !important;
}
[data-testid="stMain"] [data-testid="stAlert"] p { color: var(--ink); }
"""


def inject_theme() -> None:
    """Inject the global stylesheet. Call once near the top of the app."""
    st.markdown(f"<style>{_root_vars()}{_CSS_BODY}</style>", unsafe_allow_html=True)
