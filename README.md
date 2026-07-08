# Valuation Workbench

**From Capital IQ export to IC memo — an underwriting workbench where every assumption shows its source.**

A Capital IQ-powered micro-underwriting and valuation workbench for public-company
investment analysis: automated CapIQ ingestion, a business-model-aware judgment layer,
peer benchmarking with an explicit review workflow, driver-based DCF cases with full
assumptions provenance, and one-click IC memo exports.

`Python 3.10+` · `Streamlit` · `Plotly` · 150+ tests · **public demo runs fully offline**

![Valuation case](reports/sample/03_valuation_case.png)

---

## What it does

1. **Automated Capital IQ ingestion** — a PowerShell bridge drives the CapIQ Excel
   Add-In (COM + UI Automation): writes `CIQ()` formula sheets, fires the ribbon
   refresh, polls pending cells, and scrapes 20 quarters of financials, a monthly
   valuation-history series, and consensus estimates (with 30/90-day-ago snapshots)
   into private CSVs. Every run appends to a refresh log.
2. **One normalized judgment layer** — quarterly schema with business-model-aware
   metrics (operating vs financial vs insurer): strict TTM windows, ROIC/ROE,
   SBC-adjusted FCF, cash conversion cycle, USD-normalized sizes, peer percentiles.
3. **Watchlist triage** — an attention score (valuation dislocation, revision
   momentum, operating inflection, flag pressure) ranks the book by where diligence
   hours pay. Thesis themes are kept separate from trading comps by design.
4. **Peer benchmarking with a review workflow** — scored comp-set suggestions,
   analyst approval/rejection with an audit trail, IB-style valuation spread
   (LTM/NTM multiples, quartiles, medians with and without outliers), peer
   distribution strips, and "is the multiple earned?" scatters.
5. **Multi-multiple framework** — each multiple is assigned a role per company
   (Primary / Secondary / Cross-check / Not meaningful) based on the business model.
   Lenders are never judged on EV/EBITDA; negative-EBITDA names never enter an
   EBITDA median.
6. **Valuation case generator** — driver-based operating forecast anchored on the
   company's own TTM data, CAPM WACC with every component shown, mid-year DCF with
   dual terminal value (exit multiple vs Gordon, cross-checked), equity bridge to a
   target, football field, sensitivity grids, and a full HTML case export.
7. **Capital structure & credit lens** — EV bridge vs reported TEV, covenant-style
   headroom, sponsor debt capacity, leverage/coverage trends.
8. **Actual vs consensus** — beats/misses, NTM revision momentum, guidance framing.
9. **Data audit** — nine check families over the raw exports and the derived dataset
   (unit sanity, EV/market-cap bridges, sign conventions, staleness, outliers), with
   a per-company audit score. *Trust the data before trusting the valuation.*
10. **IC memo export** — a 12-section decision document combining the machine layer
    with the analyst's YAML thesis.

## Analytical safeguards (the part that matters in an interview)

- **Assumptions provenance** — every DCF input is classified *analyst / anchored-TTM /
  default-fallback* and badged (`AUTO-ANCHORED / ILLUSTRATIVE / DRAFT / FINAL`).
  Cases without an analyst file carry a visible **"calibration only — not an
  investment view"** disclosure on every chart and export.
- **Indicative stance, not advice** — the DCF-upside stance (±20% bands) is labeled
  indicative, reconciled against the operating verdict, and ships with a conviction
  qualifier driven by the bear/bull spread.
- **Business-model masks** — EBITDA frameworks report `N/M` for financials, which run
  on P/E, P/TBV, ROE vs cost of equity, and residual income instead.
- **Outlier discipline** — extreme multiples (EV/EBITDA > 75x, P/E > 100x) and
  negative denominators are excluded from *adjusted* medians but never hidden:
  raw medians stay displayed and every exclusion is named with its reason.
- **TTM honesty** — partial four-quarter windows are excluded, never annualized.
- **Confidentiality is enforced, not promised** — the private data path is
  gitignored *and covered by tests* (`tests/test_confidentiality.py`): builds refuse
  to write licensed data to public paths, and sample outputs are scanned for
  private-mode markers.

## Dashboard pages

| Page | Question it answers |
| --- | --- |
| Watchlist Home | Where do I spend diligence time? |
| Compare | How do 2–4 names stack side by side? |
| Company Situation | What's going on, and what's the debate? (verdict, KPIs, flags, thesis) |
| Peer Benchmarking | Is the multiple earned vs true comps? (review workflow, spread, distributions) |
| Actual vs Consensus | Beat or miss — and which way are estimates moving? |
| Company Financials | Is the operating story inflecting? |
| Capital Structure | Is the balance sheet a constraint or an option? |
| Valuation Case | What is it worth, and on what assumptions? (DCF, WACC, bridges, sensitivities) |
| Valuation & Expectations | What is priced in? (multi-multiple scorecard, momentum, scenarios) |
| IC Memo Export | The decision document, one click |
| Data Audit | Can I trust the inputs? |
| Data & Refresh | Mode, dataset, refresh log, add-company workflow |

The active data mode (**Public Demo** vs **Capital IQ Private**) is shown on every page.

## Data modes & confidentiality

| Mode | Data | Location | Git policy |
| --- | --- | --- | --- |
| **Public demo** | Snapshot of 7 B3-listed companies + deterministic synthetic estimates/valuation series (labeled) + sample theses | `data/sample/` | Committed |
| **Capital IQ private** | Licensed CapIQ exports, the private watchlist composition, analyst theses, private reports | `data_private/` | **Never committed** |

The watchlist composition itself (which names, which themes) is treated as private:
it lives in `data_private/universe.csv` and a private classification overlay, and no
tracked file references it. The public demo exists so the project runs out of the box
for reviewers.

## Quick start — public demo (no Capital IQ needed)

```powershell
pip install -e .

python -m src.pipeline.build_dataset --source public-demo
streamlit run src/app/streamlit_app.py -- --demo

python -m src.reporting.ic_memo --demo --company TOTS3.SA
python -m src.reporting.valuation_case --demo --company TOTS3.SA
pytest
```

## Private mode — Capital IQ workflow

1. Create `data_private/universe.csv` (columns `id,ticker,sector,currency`) — the
   composition of your book, never committed.
2. Open Excel with the S&P Capital IQ Pro Add-In signed in, then:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\export_capiq_watchlist.ps1
   python -m src.pipeline.build_dataset --source capiq --input data_private/capiq_exports --output data_private/processed/monitoring_dataset.csv
   streamlit run src/app/streamlit_app.py
   ```
3. Theses: copy `data/templates/thesis_template.yaml` to `data_private/theses/<id>.yaml`.
   DCF assumptions: `data/templates/valuation_assumptions_template.yaml` to
   `data_private/assumptions/`. Without a file, cases run fully auto-anchored and say so.

Field mnemonics vary by CapIQ entitlement; rejected formulas resolve to null and the
pipeline degrades gracefully (pages show *not populated*, never fake numbers).

## Sample outputs (public demo data only)

| | |
|---|---|
| ![Watchlist](reports/sample/01_watchlist_home.png) | ![Peer benchmarking](reports/sample/02_peer_benchmarking.png) |
| ![Football field](reports/sample/04_football_field.png) | ![Multiples scorecard](reports/sample/05_multiples_scorecard.png) |

- [`reports/sample/ic_memo_TOTS3.html`](reports/sample/ic_memo_TOTS3.html) — 12-section IC memo
- [`reports/sample/valuation_case_TOTS3.html`](reports/sample/valuation_case_TOTS3.html) — full valuation case export
- `reports/sample/06_data_audit.png` — data-quality control page

## Architecture

```
src/
├── ingestion/   CapIQ loaders, schema, classification, universe lookup
├── pipeline/    build_dataset (public-demo | capiq) with licensed-data guardrails
├── modeling/    metrics, assessment, peer_sets, multiples, dcf, wacc, forecast,
│                scenarios, capital_structure, consensus, data_audit, outliers
├── reporting/   charts, valuation/multiples chart builders, ic_memo,
│                valuation_case, board pack (HTML/PDF exports)
└── app/         Streamlit shell: theme, components, one module per page
```

Design choices worth noting: the HTML exports reuse the same chart builders as the
app (one visual language, no drift), all judgment flows through a single assessment
layer, and every "clever" number carries its provenance to the surface.

## Testing

150+ tests cover the valuation engine (DCF/WACC/terminal-value math), peer-set
scoring and review state, multiple-applicability rules, outlier exclusion, capital
structure, consensus logic, the data audit checks, template integrity, and the
confidentiality guardrails. `pytest` runs offline in under a minute.

## Limitations

- Rule-based judgment surfaces the right questions; it does not replace underwriting.
- The scenario model is deliberately simple (net debt held constant, interim FCF
  ignored) and says so on every output.
- Demo consensus/valuation series are synthetic and labeled — they exercise the
  machinery, not reality.
- Cross-listed names can carry currency mismatches in CapIQ market data; a
  self-validating normalization fixes the identifiable cases and the data audit
  flags the rest.

## How to talk about this project in interviews

> "I run a private multi-theme watchlist through a workflow I built: automated
> Capital IQ exports re-rank the book by valuation versus history, estimate momentum,
> and operating inflection. For any name I can open the debate, check whether the
> multiple is earned against a peer set I explicitly approved, and export an IC memo
> with my variant perception, what's priced in, and bear/base/bull IRRs. Nothing is a
> black box — every DCF input is labeled analyst, anchored, or default."

Worth discussing: why thesis themes must be separated from trading comps; why lenders
can't be judged on EV/EBITDA; how outlier-adjusted medians keep one broken multiple
from poisoning an exit assumption; how licensed data stays private while the project
stays demonstrable.

---

*Not investment advice. Public demo data only in the repository; licensed Capital IQ
data and the watchlist composition stay local.*
