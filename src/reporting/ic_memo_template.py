"""HTML template for the IC memo — the decision document.

Structure follows an investment-committee memo, not a monitoring pack:
cover -> situation -> why now -> business quality -> variant perception ->
key debate -> financial snapshot -> valuation & scenarios -> catalysts/risks ->
diligence questions -> decision -> methodology.

Reuses the shared board-pack stylesheet so every artifact looks like one
product; adds only memo-specific styles.
"""

from __future__ import annotations

from src.reporting.board_pack_template import board_pack_css


def ic_memo_css() -> str:
    extra = """
/* --- IC memo additions --- */
.stage-pill { display:inline-block; font-size:10px; font-weight:800; letter-spacing:.08em;
  text-transform:uppercase; padding:3px 10px; border-radius:999px;
  background: rgba(255,253,247,.12); color:#f1eadb; border:1px solid rgba(255,253,247,.35); margin-left:10px; }
.attn { font-family: var(--font-mono); }
.kv { display:grid; grid-template-columns: repeat(4,1fr); gap:11px; }
.kv .cell { background: var(--panel); border:1px solid var(--line); border-radius:6px; padding:10px 12px; }
.kv .cell .l { font-size:9.5px; font-weight:750; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.kv .cell .v { font-size:16px; font-weight:750; color:var(--ink); margin-top:5px; }
.kv .cell .s { font-size:10px; color:var(--muted-2); margin-top:2px; }
.debate { background: var(--panel); border:1px solid var(--line); border-left:4px solid var(--gold);
  border-radius:6px; padding:14px 18px; }
.debate p { font-family: var(--font-serif); font-size:14px; line-height:1.55; color:var(--slate); margin:0; }
.empty-note { font-size:12px; color:var(--muted-2); font-style:italic; }
.pillar-list { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; margin-top:12px; }
.pillar-list .pillar { background: var(--panel); border:1px solid var(--line); border-radius:6px;
  padding:10px 12px; font-size:12px; line-height:1.45; color:var(--slate); }
.swot-grid { display:grid; grid-template-columns: repeat(4,1fr); gap:10px; }
.swot-card { background: var(--panel); border:1px solid var(--line); border-radius:6px; padding:11px 12px; }
.swot-card h4 { margin:0 0 8px; font-size:9.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.swot-card ul { margin:0; padding-left:15px; }
.swot-card li { font-size:11.2px; line-height:1.42; color:var(--slate); margin-bottom:5px; }
.grid-table td, .grid-table th { text-align:center; }
.grid-table td:first-child, .grid-table th:first-child { text-align:left; }
.irr-pos { color: var(--green); font-weight:750; } .irr-neg { color: var(--red); font-weight:750; }
.catalyst-date { font-family: var(--font-mono); font-size:11px; color:var(--gold); font-weight:700; }
.journal { font-size:11.5px; color:var(--muted); }
.journal .jdate { font-family: var(--font-mono); color:var(--gold); }
.decision-box { background: var(--panel); border:1px solid var(--line); border-top:4px solid var(--charcoal);
  border-radius:6px; padding:16px 20px; }
"""
    return board_pack_css() + extra


IC_MEMO_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ company.company_name }} - IC Memo</title>
<style>{{ css }}</style>
</head>
<body>
<main>

  <div class="cover">
    <div class="cover-kicker">Investment Committee Memo | {{ memo_date }}</div>
    <h1>{{ company.company_name }}<span class="stage-pill">{{ stage_label }}</span></h1>
    <div class="cover-sub">{{ company.ticker }} | {{ peer_group }} comps | {{ currency_label }} | Financials through {{ as_of }}</div>
    <div class="cover-verdict" style="border-left-color:{{ verdict.color }}">
      <div class="v-kicker">Watchlist Verdict &middot; Attention {{ attention_score }}/100</div>
      <div class="v-label" style="color:{{ verdict.color }}">{{ verdict.label }}</div>
      <div class="v-rationale">{{ verdict.rationale }}</div>
    </div>
    <div class="cover-foot"><span>Price {{ snapshot.price }}</span><span>Mkt cap {{ snapshot.market_cap }}</span><span>EV {{ snapshot.ev }}</span><span>{{ snapshot.multiple }}</span><span>{{ mode }}</span></div>
  </div>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>1 &middot; Situation Overview</h2></div>
    <div class="memo"><p>{{ situation }}</p></div>
    {% if thesis.investment_pillars %}
    <div class="pillar-list">
      {% for p in thesis.investment_pillars %}<div class="pillar">{{ p }}</div>{% endfor %}
    </div>
    {% endif %}
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>2 &middot; Why Now</h2></div>
    <div class="kv">
      <div class="cell"><div class="l">Valuation vs Own History</div><div class="v">{{ why_now.history }}</div><div class="s">{{ why_now.history_detail }}</div></div>
      <div class="cell"><div class="l">Estimate Momentum</div><div class="v">{{ why_now.revisions }}</div><div class="s">{{ why_now.revisions_detail }}</div></div>
      <div class="cell"><div class="l">vs Peer Median</div><div class="v">{{ why_now.premium }}</div><div class="s">{{ why_now.premium_detail }}</div></div>
      <div class="cell"><div class="l">Next Earnings</div><div class="v">{{ why_now.earnings }}</div><div class="s">Open flags: {{ why_now.flags }}</div></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>3 &middot; Business Quality</h2></div>
    <table>
      <tr><th>Metric (basis in label)</th><th>Current</th><th>Year Ago</th><th>Peer Median (ex-company)</th></tr>
      {% for r in quality_rows %}
      <tr><td>{{ r.label }}</td><td class="num">{{ r.current }}</td><td class="num">{{ r.prior }}</td><td class="num">{{ r.median }}</td></tr>
      {% endfor %}
    </table>
  </section>

  <section>
    <div class="cols2">
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>4 &middot; Variant Perception</h2></div>
        {% if thesis.variant_perception %}<div class="memo"><p>{{ thesis.variant_perception }}</p></div>
        {% else %}<div class="empty-note">No analyst variant perception on file — add one to the thesis YAML.</div>{% endif %}
      </div>
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>5 &middot; Key Debate</h2></div>
        {% if thesis.key_debate %}<div class="debate"><p>{{ thesis.key_debate }}</p></div>
        {% else %}<div class="empty-note">No key debate on file — the memo is machine-only until the analyst writes it.</div>{% endif %}
      </div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>6 &middot; Financial Snapshot</h2>
      <span class="s-note">Last {{ performance_rows|length }} quarters | latest highlighted</span></div>
    <table>
      <tr><th>Reported Quarter</th><th>Revenue (Quarter)</th><th>Rev Growth (Quarter YoY)</th><th>{{ profit_label }} (Quarter)</th><th>Margin (Quarter)</th><th>FCF (Quarter)</th></tr>
      {% for r in performance_rows %}
      <tr class="{{ 'anchor' if r.is_latest else '' }}">
        <td>{{ r.period }}</td><td class="num">{{ r.revenue }}</td><td class="num">{{ r.rev_yoy|safe }}</td>
        <td class="num">{{ r.profit }}</td><td class="num">{{ r.margin }}</td><td class="num">{{ r.fcf }}</td>
      </tr>
      {% endfor %}
    </table>
    <div class="charts" style="margin-top:14px">
      <div class="chart-card"><img src="{{ chart_history }}" alt="Revenue and profitability"></div>
      <div class="chart-card"><img src="{{ chart_peer }}" alt="Peer positioning"></div>
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>7 &middot; Valuation &amp; Scenarios</h2></div>
    <div class="cols2">
      <div>
        <table>
          {% for r in valuation_rows %}
          <tr><td>{{ r.label }}</td><td class="num">{{ r.value }}</td><td class="num">{{ r.context }}</td></tr>
          {% endfor %}
        </table>
        <div class="memo" style="margin-top:10px"><h4>What Is Priced In</h4><p>{{ implied_text }}</p></div>
      </div>
      <div>
        <table class="grid-table">
          <tr><th>Case</th><th>Rev CAGR</th><th>Exit Margin</th><th>Exit Multiple</th><th>MOIC</th><th>IRR ({{ horizon }}y)</th></tr>
          {% for s in scenario_rows %}
          <tr><td>{{ s.name }}</td><td class="num">{{ s.cagr }}</td><td class="num">{{ s.margin }}</td>
              <td class="num">{{ s.multiple }}</td><td class="num">{{ s.moic }}</td><td class="num">{{ s.irr|safe }}</td></tr>
          {% endfor %}
        </table>
        <div class="s-note" style="margin-top:6px">{{ scenario_note }}</div>
      </div>
    </div>
  </section>

  <section>
    <div class="cols2">
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>8 &middot; Catalysts</h2></div>
        {% if catalysts %}
        <div class="lst q"><ul>
          {% for c in catalysts %}<li><span class="catalyst-date">{{ c.date }}</span> &nbsp;{{ c.event }}{% if c.note %} — {{ c.note }}{% endif %}</li>{% endfor %}
        </ul></div>
        {% else %}<div class="empty-note">No dated catalysts on file.</div>{% endif %}
      </div>
      <div>
        <div class="s-head"><div class="s-bar"></div><h2>9 &middot; Risks</h2></div>
        {% if risks %}
        <div class="lst con"><ul>{% for r in risks %}<li>{{ r }}</li>{% endfor %}</ul></div>
        {% else %}<div class="empty-note">No analyst risks on file; auto-generated concerns below.</div>
        <div class="lst con"><ul>{% for c in concerns %}<li>{{ c }}</li>{% endfor %}</ul></div>{% endif %}
      </div>
    </div>
  </section>

  {% if thesis.swot %}
  <section>
    <div class="s-head"><div class="s-bar"></div><h2>10 &middot; SWOT From Analyst Case</h2></div>
    <div class="swot-grid">
      {% for key, label in [('strengths','Strengths'),('weaknesses','Weaknesses'),('opportunities','Opportunities'),('threats','Threats')] %}
      <div class="swot-card">
        <h4>{{ label }}</h4>
        <ul>{% for item in thesis.swot.get(key, []) %}<li>{{ item }}</li>{% endfor %}</ul>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>11 &middot; Diligence Questions</h2></div>
    <div class="lst q"><ol style="margin:0;padding-left:18px">
      {% for q in questions %}<li style="font-size:12px;color:var(--slate);line-height:1.45;margin-bottom:6px">{{ q }}</li>{% endfor %}
    </ol></div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>12 &middot; Decision &amp; Next Steps</h2></div>
    <div class="decision-box">
      <p style="margin:0 0 8px;font-size:13.5px;color:var(--ink)"><b>Stage:</b> {{ stage_label }}{% if thesis.analyst_status %} &nbsp;|&nbsp; <b>Thesis status:</b> {{ thesis.analyst_status }}{% endif %} &nbsp;|&nbsp; <b>Verdict:</b> {{ verdict.label }}</p>
      <p style="margin:0;font-size:13px;color:var(--slate)">{{ decision_text }}</p>
      {% if journal %}
      <div class="journal" style="margin-top:12px">
        <b>Journal (latest):</b>
        {% for j in journal %}<div><span class="jdate">{{ j.date }}</span> — {{ j.note }}</div>{% endfor %}
      </div>
      {% endif %}
    </div>
  </section>

  <section>
    <div class="s-head"><div class="s-bar"></div><h2>13 &middot; Methodology Appendix</h2></div>
    <div class="memo"><div class="appendix">
      {% if thesis.source_deck or thesis.source_as_of or thesis.source_notes %}
      <p><b>Analyst source.</b>
      {% if thesis.source_deck %}Deck/case: {{ thesis.source_deck }}. {% endif %}
      {% if thesis.source_as_of %}Thesis as of {{ thesis.source_as_of }}. {% endif %}
      {% if thesis.source_notes %}{{ thesis.source_notes }}{% endif %}</p>
      {% endif %}
      <p><b>Data.</b> {{ mode }}. LTM metrics require four reported quarters; partial windows are excluded rather than annualized.
      Peer statistics use the true trading comp set ({{ peer_group }}), separate from the thesis theme. Signals marked N/M are
      not meaningful for the company's business model.</p>
      <p><b>Scenarios.</b> Exit value = exit-year {{ scenario_profit_label }} &times; exit multiple; equity bridged with today's net debt held
      constant and interim FCF ignored (conservative for cash-generative names). IRR = MOIC^(1/t)&minus;1 against today's market cap.
      Cases come from the analyst thesis where present, otherwise derived from the company's current profile.</p>
      <p><b>Implied expectations.</b> Solves the {{ scenario_profit_label }} CAGR required for today's value to compound at the stated
      returns assuming exit at the peer-median multiple.</p>
      <p><b>Confidentiality.</b> Licensed Capital IQ data and analyst theses stay in <code>data_private/</code>, outside version control.
      This memo is an illustrative watchlist artifact, not investment advice.</p>
    </div></div>
  </section>

  <div class="footer">Generated by the Investment Watchlist workflow · {{ memo_date }} · {{ mode }} · Not investment advice.</div>
</main>
</body>
</html>
"""
