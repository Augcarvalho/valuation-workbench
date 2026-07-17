"""HTML template + stylesheet for the exported board pack.

Kept separate from the rendering logic so :mod:`src.reporting.board_pack`
stays focused on building the data context. The stylesheet reuses the shared
:mod:`src.branding` palette so the export is visually consistent with the
Streamlit dashboard.
"""

from __future__ import annotations

from src.branding import FONT_MONO, FONT_SANS, FONT_SERIF, PALETTE


def board_pack_css() -> str:
    tokens = "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in PALETTE.items())
    root = (
        ":root{\n" + tokens
        + f"\n  --font-sans: {FONT_SANS};\n  --font-serif: {FONT_SERIF};\n  --font-mono: {FONT_MONO};\n}}"
    )
    body = """
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-sans); font-size: 13px; }
main { width: 1040px; margin: 0 auto; padding: 0 0 40px; }
.num, table td.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

/* Cover */
.cover {
  background: linear-gradient(104deg, var(--navy) 0%, var(--navy-2) 68%, var(--sage) 155%);
  color: #fffaf0; padding: 30px 36px 26px; border-radius: 0 0 10px 10px;
}
.cover-kicker { font-size: 11px; letter-spacing: .26em; text-transform: uppercase; color: #c2ad73; }
.cover h1 { margin: 8px 0 4px; font-size: 30px; font-weight: 750; letter-spacing: 0; }
.cover-sub { font-size: 13px; color: #e7ddc8; font-family: var(--font-mono); }
.cover-verdict {
  margin-top: 18px; background: rgba(255,253,247,.08); border-left: 5px solid var(--gold);
  padding: 12px 16px; border-radius: 5px;
}
.cover-verdict .v-label { font-size: 17px; font-weight: 800; }
.cover-verdict .v-kicker { font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: #c2ad73; }
.cover-verdict .v-rationale { font-size: 13px; color: #f1eadb; margin-top: 3px; }
.cover-foot { margin-top: 16px; font-size: 11px; color: #bdb5a6; display: flex; gap: 22px; }

section { padding: 0 36px; }
.s-head { display: flex; align-items: center; gap: 10px; margin: 26px 0 12px; }
.s-bar { width: 4px; height: 17px; background: var(--gold); border-radius: 2px; }
.s-head h2 { margin: 0; font-size: 14px; font-weight: 750; letter-spacing: .05em; text-transform: uppercase; color: var(--navy); }
.s-head .s-note { font-size: 11.5px; color: var(--muted); }

/* KPI cards */
.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 11px; }
.kpi {
  background: var(--panel); border: 1px solid var(--line); border-top: 3px solid var(--muted-2);
  border-radius: 6px; padding: 11px 12px;
}
.kpi.sig-green { border-top-color: var(--green); } .kpi.sig-yellow { border-top-color: var(--amber); }
.kpi.sig-red { border-top-color: var(--red); } .kpi.sig-na { border-top-color: var(--muted-2); }
.kpi .k-label { font-size: 9.5px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.kpi .k-value { font-size: 21px; font-weight: 750; color: var(--ink); margin: 6px 0 3px; }
.kpi .k-context { font-size: 10.5px; color: var(--muted); }
.kpi .k-foot { margin-top: 8px; display: flex; justify-content: space-between; align-items: center; }
.pill { font-size: 9px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; padding: 2px 7px; border-radius: 3px; }
.pill.sig-green { background: var(--green-soft); color: var(--green); } .pill.sig-yellow { background: var(--amber-soft); color: var(--amber); }
.pill.sig-red { background: var(--red-soft); color: var(--red); } .pill.sig-na { background: var(--panel-alt); color: var(--muted); }
.k-pctile { font-size: 9.5px; color: var(--muted-2); }

/* Memos */
.cols2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.cols-58 { display: grid; grid-template-columns: 1.25fr 1fr; gap: 16px; }
.memo { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--sage); border-radius: 6px; padding: 13px 16px; }
.memo h4 { margin: 0 0 6px; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--navy); }
.memo p { font-family: var(--font-serif); font-size: 13.5px; line-height: 1.5; color: var(--slate); margin: 0; }

.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 4px; }
.chart-card { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 8px; }
.chart-card img { width: 100%; display: block; }

/* Tables */
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; font-size: 12px; }
th, td { padding: 7px 11px; text-align: right; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { background: var(--panel-alt); color: var(--muted); font-weight: 750; font-size: 10px; letter-spacing: .05em; text-transform: uppercase; }
tr.anchor td { background: var(--sage-soft); font-weight: 750; color: var(--navy); }
tr.median td { background: #f3eadb; font-style: italic; color: var(--slate); }
.tone-green { color: var(--green); font-weight: 750; } .tone-red { color: var(--red); font-weight: 750; }
.cell-pill { font-size: 9.5px; font-weight: 800; padding: 1px 6px; border-radius: 3px; }
.cell-green { background: var(--green-soft); color: var(--green); } .cell-yellow { background: var(--amber-soft); color: var(--amber); } .cell-red { background: var(--red-soft); color: var(--red); }

/* Lists */
.lst { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 11px 14px; }
.lst h4 { margin: 0 0 7px; font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; }
.lst.pos h4 { color: var(--green); } .lst.con h4 { color: var(--red); } .lst.q h4 { color: var(--navy); }
.lst ul { margin: 0; padding-left: 16px; }
.lst li { font-size: 12px; color: var(--slate); line-height: 1.45; margin-bottom: 5px; }

/* Flags */
.flag { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--muted-2); border-radius: 5px; padding: 9px 12px; margin-bottom: 7px; }
.flag.sev-high { border-left-color: var(--red); } .flag.sev-medium { border-left-color: var(--amber); } .flag.sev-monitor { border-left-color: var(--green); }
.flag .f-sev { font-size: 9px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; color: #fffaf0; padding: 1px 6px; border-radius: 3px; }
.flag.sev-high .f-sev { background: var(--red); } .flag.sev-medium .f-sev { background: var(--amber); } .flag.sev-monitor .f-sev { background: var(--green); }
.flag .f-area { font-size: 12px; font-weight: 750; color: var(--ink); margin-left: 7px; }
.flag .f-obs { font-size: 12px; color: var(--slate); margin: 5px 0 3px; }
.flag .f-q { font-size: 12px; color: var(--sage); font-style: italic; }

.appendix { font-size: 11.5px; color: var(--slate); line-height: 1.55; }
.appendix code { background: var(--panel-alt); padding: 1px 5px; border-radius: 3px; font-size: 11px; }
.footer { margin: 26px 36px 0; padding-top: 12px; border-top: 1px solid var(--line); font-size: 10.5px; color: var(--muted-2); }

@media print {
  body { background: #fff; }
  .charts, .cols2, .cols-58 { break-inside: avoid; }
  section { break-inside: avoid; }
}
"""
    return root + body


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ company.company_name }} - Investment Watchlist Board Pack</title>
<style>{{ css }}</style>
</head>
<body>
<main>
  <div class="cover">
    <div class="cover-kicker">Investment Watchlist | Special Situations Review</div>
    <h1>{{ company.company_name }}</h1>
    <div class="cover-sub">{{ company.ticker }} | {{ company.sector }} | {{ geography }} | {{ period_label }} | {{ currency_label }}</div>
    <div class="cover-verdict" style="border-left-color:{{ verdict.color }}">
      <div class="v-kicker">Watchlist Verdict</div>
      <div class="v-label" style="color:{{ verdict.color }}">{{ verdict.label }}</div>
      <div class="v-rationale">{{ verdict.rationale }}</div>
    </div>
    <div class="cover-foot"><span>Quarterly Board Pack</span><span>Financials through {{ as_of }}</span><span>{{ mode }}</span></div>
  </div>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Executive Summary</h2>
      <span class="s-note">Key KPIs vs investment watchlist thresholds</span></div>
    <div class="kpis">
    {% for k in kpis %}
      <div class="kpi sig-{{ k.signal_class }}">
        <div class="k-label">{{ k.label }}</div>
        <div class="k-value">{{ k.value }}</div>
        <div class="k-context">{{ k.context }}</div>
        <div class="k-foot"><span class="pill sig-{{ k.signal_class }}">{{ k.signal_text }}</span>
          <span class="k-pctile">{{ k.pctile or '' }}</span></div>
      </div>
    {% endfor %}
    </div>
    <div class="cols-58" style="margin-top:14px">
      <div class="memo"><h4>Executive Commentary</h4><p>{{ commentary }}</p></div>
      <div class="memo"><h4>Investment View</h4><p>{{ sponsor_view }}</p></div>
    </div>
  </section>

  <section>
    <div class="charts">
      <div class="chart-card"><img src="{{ chart_history }}" alt="Revenue and EBITDA"></div>
      <div class="chart-card"><img src="{{ chart_peer }}" alt="Peer positioning"></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Quarterly Performance Review</h2>
      <span class="s-note">Last {{ performance_rows|length }} quarters | latest highlighted</span></div>
    <table>
      <tr><th>Reported Quarter</th><th>Revenue (Quarter)</th><th>Rev Growth (Quarter YoY)</th><th>EBITDA (Quarter)</th><th>EBITDA Margin (Quarter)</th><th>FCF (Quarter)</th><th>FCF Conv. (LTM)</th></tr>
      {% for r in performance_rows %}
      <tr class="{{ 'anchor' if r.is_latest else '' }}">
        <td>{{ r.period }}</td><td class="num">{{ r.revenue }}</td><td class="num">{{ r.rev_yoy|safe }}</td>
        <td class="num">{{ r.ebitda }}</td><td class="num">{{ r.ebitda_mgn }}</td>
        <td class="num">{{ r.fcf }}</td><td class="num">{{ r.fcf_conv }}</td>
      </tr>
      {% endfor %}
    </table>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Peer Benchmarking</h2>
      <span class="s-note">{{ company.peer_group or company.sector }} comps | anchor &amp; peer median highlighted</span></div>
    <table>
      <tr><th>Ticker</th><th>Company</th><th>Rev Growth (Latest Q YoY)</th><th>EBITDA Margin (LTM)</th><th>FCF Conv. (LTM)</th><th>ND/EBITDA (LTM)</th><th>EV/Rev (LTM)</th><th>EV/EBITDA (LTM)</th></tr>
      {% for p in peers %}
      <tr class="{{ p.cls }}">
        <td>{{ p.ticker }}</td><td>{{ p.name }}</td><td class="num">{{ p.growth|safe }}</td>
        <td class="num">{{ p.margin }}</td><td class="num">{{ p.fcf }}</td><td class="num">{{ p.leverage }}</td>
        <td class="num">{{ p.ev_rev }}</td><td class="num">{{ p.valuation|safe }}</td>
      </tr>
      {% endfor %}
    </table>
  </section>

  <section>
    <div class="cols2">
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>Cash Flow &amp; Leverage</h2></div>
        <table>
          {% for r in cashflow_rows %}
          <tr><td>{{ r.label }}</td><td class="num">{{ r.value }}</td></tr>
          {% endfor %}
        </table>
      </div>
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>Valuation Snapshot</h2></div>
        <table>
          {% for r in valuation_rows %}
          <tr><td>{{ r.label }}</td><td class="num">{{ r.value }}</td><td class="num">{{ r.median }}</td></tr>
          {% endfor %}
        </table>
        <div class="memo" style="margin-top:10px"><h4>Premium / Discount</h4><p>{{ valuation.commentary }}</p></div>
      </div>
    </div>
  </section>

  <section>
    <div class="cols2">
      <div class="lst pos"><h4>Key Positives</h4><ul>{% for i in positives %}<li>{{ i }}</li>{% endfor %}</ul></div>
      <div class="lst con"><h4>Key Concerns</h4><ul>{% for i in concerns %}<li>{{ i }}</li>{% endfor %}</ul></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Red Flags &amp; Management Questions</h2></div>
    <div class="cols-58">
      <div>
        {% for f in flags %}
        <div class="flag sev-{{ f.sev_class }}">
          <span class="f-sev">{{ f.severity }}</span><span class="f-area">{{ f.area }}</span>
          <div class="f-obs">{{ f.observation }}</div><div class="f-q">&gt; {{ f.management_question }}</div>
        </div>
        {% endfor %}
      </div>
      <div class="lst q"><h4>Questions for Management</h4><ol style="margin:0;padding-left:18px">
        {% for q in questions %}<li style="font-size:12px;color:var(--slate);line-height:1.45;margin-bottom:6px">{{ q }}</li>{% endfor %}
      </ol></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>Methodology Appendix</h2></div>
    <div class="memo"><div class="appendix">
      <p><b>Scope.</b> Public-company financials and market data are normalized into one quarterly investment monitoring schema.
      LTM metrics aggregate the trailing four reported quarters; YoY compares to the same quarter one year prior.</p>
      <p><b>KPI thresholds (traffic lights).</b> Thresholds are profiled by business model. Operating companies:
      revenue growth green &gt;=10% / amber &gt;=2%; EBITDA margin green &gt;=22% / amber &gt;=12%; FCF conversion green
      &gt;=60% / amber &gt;=30%; net debt/EBITDA green &lt;=2.0x / amber &lt;=3.5x; EV/EBITDA green &lt;=10x / amber &lt;=16x.
      Financial institutions are judged on growth, net income margin, and P/E; managed care uses recalibrated
      thin-margin bands.</p>
      <p><b>Verdict logic.</b> The watchlist verdict combines the applicable operating signals with valuation vs the
      peer-group median multiple: deteriorating KPIs already priced by the market -&gt; <i>Do Work</i> (value trap vs
      entry debate); on-track operations at a &gt;=15% discount -&gt; <i>Do Work</i> (mispriced quality); on-track
      without a valuation blocker -&gt; <i>Constructive</i>; deterioration without valuation support -&gt;
      <i>Avoid / Pass</i>; otherwise <i>Watch</i>.</p>
      <p><b>Peers.</b> Benchmarks use the true trading peer group (separate from the thesis theme); percentiles and
      medians are computed within peer group and period. Signals marked N/M are not meaningful for the company's
      business model (e.g. the EBITDA framework for financial institutions).</p>
      <p><b>Confidentiality.</b> Licensed Capital IQ exports and private outputs are excluded from version control
      (<code>data_private/</code>, <code>reports/private/</code>). This pack is an illustrative monitoring artifact and is not investment advice.</p>
    </div></div>
  </section>

  <div class="footer">Generated by the Investment Watchlist Dashboard | {{ as_of }} | {{ mode }}.
    Raw licensed exports must stay outside version control. Not investment advice.</div>
</main>
</body>
</html>
"""
