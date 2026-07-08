"""HTML template for the IB-style valuation case.

Mirrors the Grupo Mateus deck arc: recommendation cover -> company snapshot ->
comps -> operating forecast -> DCF (WACC, terminal value, bridge, sensitivity)
-> scenarios -> methodology appendix. Reuses the shared report stylesheet so
every artifact in the system looks like one product.
"""

from __future__ import annotations

from src.reporting.board_pack_template import board_pack_css


def valuation_case_css() -> str:
    extra = """
/* --- valuation case additions --- */
.rec-band { display:flex; gap:18px; align-items:center; margin-top:16px; }
.rec-pill { font-size:22px; font-weight:800; letter-spacing:.06em; padding:8px 22px; border-radius:6px; color:#fffaf0; }
.rec-BUY { background: var(--green); } .rec-HOLD { background: var(--gold); } .rec-SELL { background: var(--red); }
.rec-NA { background: var(--muted-2); } .rec-INDICATIVE { background: var(--muted); }
.warn-box { border:1px solid var(--amber); background: var(--amber-soft); border-radius:6px;
  padding:12px 16px; margin:14px 36px 0; }
.warn-box h4 { margin:0 0 6px; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--amber); }
.warn-box ul { margin:0; padding-left:16px; }
.warn-box li { font-size:12px; color:var(--slate); margin-bottom:4px; }
.warn-box li.sev-high { color: var(--red); font-weight:600; }
.rec-nums { font-family: var(--font-mono); font-size:14px; color:#f1eadb; }
.kv { display:grid; grid-template-columns: repeat(4,1fr); gap:11px; }
.kv .cell { background: var(--panel); border:1px solid var(--line); border-radius:6px; padding:10px 12px; }
.kv .cell .l { font-size:9.5px; font-weight:750; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.kv .cell .v { font-size:16px; font-weight:750; color:var(--ink); margin-top:5px; }
.kv .cell .s { font-size:10px; color:var(--muted-2); margin-top:2px; }
.grid-table td, .grid-table th { text-align:center; font-family: var(--font-mono); font-size:11.5px; }
.grid-table td:first-child, .grid-table th:first-child { text-align:left; font-family: var(--font-sans); }
.grid-anchor { background: var(--sage-soft); font-weight:800; }
.pos { color: var(--green); font-weight:750; } .neg { color: var(--red); font-weight:750; }
.bridge { display:flex; gap:8px; align-items:stretch; flex-wrap:wrap; }
.bridge .step { flex:1; min-width:110px; background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:9px 10px; text-align:center; }
.bridge .step .l { font-size:9px; font-weight:750; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
.bridge .step .v { font-size:14px; font-weight:750; font-family:var(--font-mono); margin-top:4px; }
.bridge .op { align-self:center; font-size:16px; color:var(--muted-2); font-weight:700; }
.assump-src { font-size:9.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; padding:1px 6px; border-radius:3px; }
.src-analyst { background: var(--amber-soft); color: var(--amber); }
.src-derived { background: var(--panel-alt); color: var(--muted); }
.src-anchored { background: var(--green-soft); color: var(--green); }
.src-default { background: var(--red-soft); color: var(--red); }
.status-pill { font-size:10.5px; font-weight:800; letter-spacing:.08em; text-transform:uppercase;
  padding:4px 12px; border-radius:999px; margin-left:12px; vertical-align:middle; }
.status-auto { background: rgba(143,47,59,.25); color:#f3c2c2; border:1px solid rgba(143,47,59,.6); }
.status-illustrative, .status-draft { background: rgba(168,132,63,.22); color:#f0d9a8; border:1px solid rgba(168,132,63,.6); }
.status-final { background: rgba(79,118,88,.25); color:#bfe3c8; border:1px solid rgba(79,118,88,.6); }
.disclosure { border:1px solid var(--red); background: var(--red-soft); border-radius:6px;
  padding:12px 16px; margin:14px 36px 0; }
.disclosure h4 { margin:0 0 5px; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--red); }
.disclosure p { margin:0; font-size:12.5px; color:var(--slate); }
.chart-full { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:8px; margin-top:10px; }
.chart-full img { width:100%; display:block; }
"""
    return board_pack_css() + extra


VALUATION_CASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ company.company_name }} - Valuation Case</title>
<style>{{ css }}</style>
</head>
<body>
<main>

  <div class="cover">
    <div class="cover-kicker">Valuation Case | DCF &amp; Trading Comparables | {{ case_date }}</div>
    <h1>{{ company.company_name }}<span class="status-pill status-{{ status_key }}">{{ status_label }}</span></h1>
    <div class="cover-sub">{{ company.ticker }} | {{ peer_group }} comps | {{ currency_label }} | As of {{ as_of }}</div>
    <div class="rec-band">
      <span class="rec-pill rec-{{ rec.stance }}">{{ rec.stance }}</span>
      <div>
        <div class="rec-nums">Target {{ target_price }} vs current {{ current_price }} &rarr; <b>{{ upside }}</b> base case</div>
        <div class="rec-nums" style="opacity:.8">Bear {{ bear_upside }} &middot; Bull {{ bull_upside }} &middot; WACC {{ wacc_pct }} &middot; Exit {{ exit_multiple }} EV/EBITDA</div>
      </div>
    </div>
    <div class="cover-foot"><span>{{ rec.headline }}</span><span>{{ mode }}</span></div>
  </div>

  {% if status_key == 'auto' %}
  <div class="disclosure">
    <h4>Auto-anchored case - not an investment view</h4>
    <p>Every driver in this case was derived mechanically from the company's trailing-twelve-month data
    because no analyst assumptions file exists. Treat the target as a calibration starting point, not a view.</p>
  </div>
  {% elif status_key in ('illustrative', 'draft') %}
  <div class="disclosure" style="border-color: var(--amber); background: var(--amber-soft);">
    <h4 style="color: var(--amber)">{{ status_label }}</h4>
    <p>The analyst assumptions behind this case are placeholders pending full diligence. Numbers are directional.</p>
  </div>
  {% endif %}

  {% if warnings %}
  <div class="warn-box">
    <h4>Model-Quality Warnings</h4>
    <ul>
      {% for w in warnings %}<li class="sev-{{ w.severity }}">{{ w.text }}</li>{% endfor %}
    </ul>
  </div>
  {% endif %}

  {% if images.scenario_targets or images.football_field %}
  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Valuation Range</h2></div>
    <div class="charts">
      {% if images.scenario_targets %}<div class="chart-card"><img src="{{ images.scenario_targets }}" alt="Scenario price targets"></div>{% endif %}
      {% if images.football_field %}<div class="chart-card"><img src="{{ images.football_field }}" alt="Football field"></div>{% endif %}
    </div>
  </section>
  {% endif %}

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>1 &middot; Company Snapshot</h2></div>
    <div class="memo"><p>{{ overview }}</p></div>
    <div class="kv" style="margin-top:12px">
      <div class="cell"><div class="l">TTM Revenue</div><div class="v">{{ snapshot.revenue }}</div><div class="s">{{ snapshot.growth }} YoY</div></div>
      <div class="cell"><div class="l">EBITDA Margin (TTM)</div><div class="v">{{ snapshot.margin }}</div><div class="s">{{ snapshot.ebitda }} EBITDA</div></div>
      <div class="cell"><div class="l">Enterprise Value</div><div class="v">{{ snapshot.ev }}</div><div class="s">Mkt cap {{ snapshot.market_cap }}</div></div>
      <div class="cell"><div class="l">Current Multiple</div><div class="v">{{ snapshot.multiple }}</div><div class="s">LTM EV/EBITDA</div></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>2 &middot; Trading Comparables</h2>
      <span class="s-note">{{ peer_group }} | NTM forwards where consensus exists | anchor highlighted</span></div>
    <table>
      <tr><th>Company</th><th>Mkt Cap</th><th>EV</th><th>Growth</th><th>EBITDA mgn</th><th>EV/Rev LTM</th><th>EV/EBITDA LTM</th><th>EV/EBITDA NTM</th><th>P/E LTM</th></tr>
      {% for p in spread_rows %}
      <tr class="{{ 'anchor' if p.is_anchor else '' }}">
        <td>{{ p.name }}</td><td class="num">{{ p.market_cap }}</td><td class="num">{{ p.ev }}</td>
        <td class="num">{{ p.growth|safe }}</td><td class="num">{{ p.margin }}</td>
        <td class="num">{{ p.ev_rev }}</td><td class="num">{{ p.ev_ebitda }}</td>
        <td class="num">{{ p.ev_ebitda_ntm }}</td><td class="num">{{ p.pe }}</td>
      </tr>
      {% endfor %}
      {% for s in stat_rows %}
      <tr class="median"><td>{{ s.label }}</td><td></td><td></td>
        <td class="num">{{ s.growth }}</td><td class="num">{{ s.margin }}</td>
        <td class="num">{{ s.ev_rev }}</td><td class="num">{{ s.ev_ebitda }}</td>
        <td class="num">{{ s.ev_ebitda_ntm }}</td><td class="num">{{ s.pe }}</td></tr>
      {% endfor %}
    </table>
    <div class="s-note" style="margin-top:6px">Exit multiple used in the DCF: <b>{{ exit_multiple }}</b> ({{ exit_multiple_source }}).</div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>3 &middot; Operating Forecast (Base Case)</h2>
      <span class="s-note">drivers <span class="assump-src src-{{ base_source }}">{{ base_source }}</span> | horizon {{ horizon }}y</span></div>
    <table>
      <tr><th>Year</th>{% for y in years %}<th>Y{{ y }}</th>{% endfor %}</tr>
      {% for line in forecast_lines %}
      <tr><td>{{ line.label }}</td>{% for v in line.cells %}<td class="num">{{ v }}</td>{% endfor %}</tr>
      {% endfor %}
    </table>
    <div class="s-note" style="margin-top:6px">Working capital: {{ nwc_note }}.</div>
    {% if images.forecast or images.fcf_bridge %}
    <div class="charts">
      {% if images.forecast %}<div class="chart-card"><img src="{{ images.forecast }}" alt="Forecast"></div>{% endif %}
      {% if images.fcf_bridge %}<div class="chart-card"><img src="{{ images.fcf_bridge }}" alt="FCF bridge"></div>{% endif %}
    </div>
    {% endif %}
  </section>

  <section>
    <div class="cols2">
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>4 &middot; WACC Build</h2></div>
        <table>
          {% for r in wacc_rows %}
          <tr><td>{{ r.label }}</td><td class="num">{{ r.value }}</td></tr>
          {% endfor %}
        </table>
        {% if wacc_notes %}<div class="s-note" style="margin-top:6px">{% for n in wacc_notes %}{{ n }}. {% endfor %}</div>{% endif %}
      </div>
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>5 &middot; Terminal Value</h2></div>
        <table>
          <tr><th></th><th>Exit Multiple</th><th>Perpetuity</th></tr>
          {% for r in tv_rows %}
          <tr><td>{{ r.label }}</td><td class="num">{{ r.exit }}</td><td class="num">{{ r.perp }}</td></tr>
          {% endfor %}
        </table>
        <div class="memo" style="margin-top:10px"><h4>Cross-check</h4><p>{{ tv_crosscheck }}</p></div>
      </div>
    </div>
    {% if images.wacc_build or images.terminal_value %}
    <div class="charts">
      {% if images.wacc_build %}<div class="chart-card"><img src="{{ images.wacc_build }}" alt="WACC build"></div>{% endif %}
      {% if images.terminal_value %}<div class="chart-card"><img src="{{ images.terminal_value }}" alt="Terminal value comparison"></div>{% endif %}
    </div>
    {% endif %}
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>6 &middot; Equity Value Bridge (Base Case)</h2></div>
    <div class="bridge">
      <div class="step"><div class="l">PV of FCF</div><div class="v">{{ bridge.pv_explicit }}</div></div>
      <div class="op">+</div>
      <div class="step"><div class="l">PV of Terminal</div><div class="v">{{ bridge.pv_terminal }}</div></div>
      <div class="op">=</div>
      <div class="step"><div class="l">Enterprise Value</div><div class="v">{{ bridge.ev }}</div></div>
      <div class="op">&minus;</div>
      <div class="step"><div class="l">Net Debt</div><div class="v">{{ bridge.net_debt }}</div></div>
      <div class="op">=</div>
      <div class="step" style="border-top:3px solid var(--gold)"><div class="l">Implied Equity</div><div class="v">{{ bridge.equity }}</div></div>
      <div class="op">&rarr;</div>
      <div class="step" style="border-top:3px solid var(--green)"><div class="l">Target Price</div><div class="v">{{ bridge.target }}</div></div>
    </div>
    <div class="s-note" style="margin-top:8px">vs market cap {{ bridge.market_cap }} &rarr; <b>{{ upside }}</b>. Terminal value is {{ bridge.tv_pct }} of EV.</div>
    {% if images.sensitivity or images.equity_bridge %}
    <div class="charts">
      {% if images.sensitivity %}<div class="chart-card"><img src="{{ images.sensitivity }}" alt="Sensitivity heatmap"></div>{% endif %}
      {% if images.equity_bridge %}<div class="chart-card"><img src="{{ images.equity_bridge }}" alt="Equity bridge waterfall"></div>{% endif %}
      {% if images.tornado %}<div class="chart-card"><img src="{{ images.tornado }}" alt="Driver tornado"></div>{% endif %}
      {% if images.implied_growth %}<div class="chart-card"><img src="{{ images.implied_growth }}" alt="Implied perpetuity growth grid"></div>{% endif %}
    </div>
    {% endif %}
  </section>

  <section>
    <div class="cols2">
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>7 &middot; Sensitivity: Target Price</h2>
          <span class="s-note">WACC (rows) x exit multiple (cols)</span></div>
        <table class="grid-table">
          <tr><th>WACC \\ Exit</th>{% for c in sens_wm.columns %}<th>{{ c }}</th>{% endfor %}</tr>
          {% for r in sens_wm.rows %}
          <tr><td>{{ r.label }}</td>{% for v in r.cells %}<td class="{{ v.cls }}">{{ v.text }}</td>{% endfor %}</tr>
          {% endfor %}
        </table>
      </div>
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>8 &middot; Sensitivity: Upside</h2>
          <span class="s-note">growth shift (rows) x margin shift (cols)</span></div>
        <table class="grid-table">
          <tr><th>Growth \\ Margin</th>{% for c in sens_gm.columns %}<th>{{ c }}</th>{% endfor %}</tr>
          {% for r in sens_gm.rows %}
          <tr><td>{{ r.label }}</td>{% for v in r.cells %}<td class="{{ v.cls }}">{{ v.text }}</td>{% endfor %}</tr>
          {% endfor %}
        </table>
      </div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>9 &middot; Scenarios</h2></div>
    <table>
      <tr><th>Case</th><th>Rev CAGR</th><th>Exit Margin</th><th>EV</th><th>Implied Equity</th><th>Target</th><th>Upside</th><th>Drivers</th></tr>
      {% for s in scenario_rows %}
      <tr><td>{{ s.name }}</td><td class="num">{{ s.cagr }}</td><td class="num">{{ s.margin }}</td>
        <td class="num">{{ s.ev }}</td><td class="num">{{ s.equity }}</td><td class="num">{{ s.target }}</td>
        <td class="num">{{ s.upside|safe }}</td><td><span class="assump-src src-{{ s.source }}">{{ s.source }}</span></td></tr>
      {% endfor %}
    </table>
    <div class="memo" style="margin-top:12px"><h4>Recommendation</h4><p>{{ rec.headline }} {{ rec.reconciliation }}</p></div>
    {% if images.peer_quartiles or images.revisions or images.working_capital %}
    <div class="charts">
      {% if images.peer_quartiles %}<div class="chart-card"><img src="{{ images.peer_quartiles }}" alt="Peer quartile panels"></div>{% endif %}
      {% if images.revisions %}<div class="chart-card"><img src="{{ images.revisions }}" alt="Estimate revision momentum"></div>{% endif %}
      {% if images.working_capital and not images.revisions %}<div class="chart-card"><img src="{{ images.working_capital }}" alt="Working capital days"></div>{% endif %}
    </div>
    {% endif %}
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>10 &middot; Assumptions Provenance</h2>
      <span class="s-note">every input classified - no black box</span></div>
    <table>
      <tr><th>Input</th><th>Value</th><th>Source</th></tr>
      {% for r in provenance_rows %}
      <tr><td>{{ r.item }}</td><td>{{ r.value }}</td>
        <td><span class="assump-src src-{{ r.source }}">{{ r.source }}</span></td></tr>
      {% endfor %}
    </table>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>11 &middot; Methodology Appendix</h2></div>
    <div class="memo"><div class="appendix">
      <p><b>Forecast.</b> Tier-1 driver model: revenue growth, EBITDA margin, D&amp;A %, capex %, and working-capital
      glidepaths, anchored on the company's own TTM data; analyst YAML overrides where present (labeled).
      Taxes at {{ tax_rate }} on positive EBIT.</p>
      <p><b>DCF.</b> Mid-year discounting of interim UFCF; terminal value computed both by exit multiple
      ({{ exit_multiple }} EV/EBITDA, {{ exit_multiple_source }}) and Gordon perpetuity ({{ perp_growth }} growth),
      both discounted at year-{{ horizon }}; the exit-multiple method is primary. Equity bridge: EV &minus; net debt
      &minus; minority &minus; preferred; upside measured against market cap (unit-safe), target = current price x (1 + upside).</p>
      <p><b>WACC.</b> CAPM with {{ wacc_source_note }}. Every component and fallback listed in section 4.</p>
      <p><b>Assumption provenance.</b> {{ provenance_note }}</p>
      <p><b>Confidentiality.</b> Licensed Capital IQ data and analyst assumption files stay in <code>data_private/</code>,
      outside version control. Illustrative analysis; not investment advice.</p>
    </div></div>
  </section>

  <div class="footer">Generated by the Investment Watchlist workflow &middot; {{ case_date }} &middot; {{ mode }} &middot; Not investment advice.</div>
</main>
</body>
</html>
"""
