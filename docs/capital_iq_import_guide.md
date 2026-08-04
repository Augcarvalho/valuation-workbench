# Capital IQ Import Guide

This repository must not contain raw Capital IQ exports. Use the private import workflow locally.

## Local Folder

Create this folder locally:

```text
data_private/
  capiq_exports/
    companies.csv
    financials_quarterly.csv
    market_data.csv
    estimates.csv
    company_segments.csv
    operating_kpis.csv
    source_log.csv

  operating_kpi_config.csv
```

`data_private/` is ignored by Git.

## Export Guidance

Use Capital IQ to export the following views:

- Company identity: company name, ticker, exchange, currency, sector.
- Quarterly financials: revenue, gross profit, EBITDA, EBIT, net income, CFO, capex, cash, debt, working capital, interest expense.
- Market data: share price, shares outstanding, market cap, enterprise value.
- Consensus/guidance: revenue and EBITDA estimates where available.
- Peer multiples: EV/Revenue, EV/EBITDA, P/E and related peer fields.
- Reported business/geographic segments.
- Company-specific operating KPIs such as store count, comparable sales,
  club/member counts, fleet/utilization, backlog/orders, customers/retention,
  shipment volume/ASP, TPV/take rate, or loan-book metrics.

Match the column names in `data/templates/`. The loader accepts CSV and Excel files.

Operating-statistic mnemonics vary by issuer and entitlement. Generate the
private request queue with:

```powershell
python scripts/generate_operating_kpi_queue.py
```

Then review `data_private/operating_kpi_config.csv` in Capital IQ Formula
Builder. Replace `VERIFY_IN_FORMULA_BUILDER` only after confirming the data
item, period basis, unit, scope and definition. The exporter skips unverified
rows rather than issuing speculative formulas.

For every material physical KPI, add the issuer-filing observation to
`operating_kpis.csv` as a separate row (`source_type=company_filing`). The
dashboard compares Capital IQ and filing values at a 1% tolerance and never
silently overwrites one source with the other.

## Build Private Dataset

```powershell
python -m src.pipeline.build_dataset --source capiq --input data_private/capiq_exports
```

The command validates required columns, normalizes period dates, calculates KPIs, and writes a local processed dataset.

Detailed revenue-driver methodology is documented in
[`operating_driver_methodology.md`](operating_driver_methodology.md).

## Public GitHub Policy

Do not commit:

- Raw Capital IQ exports.
- Screenshots that reveal proprietary Capital IQ rows or formulas.
- Private-company financials.
- Confidential board materials.

Commit only:

- Import templates.
- Code.
- Methodology.
- Public-demo outputs.
- Sanitized screenshots.

## Export v3 field wishlist (all optional)

Financials sheet: IQ_MINORITY_INTEREST, IQ_PREF_EQUITY, IQ_CAPITAL_LEASES,
IQ_PENSION, IQ_TANGIBLE_COMMON_EQUITY (financial institutions), IQ_TOTAL_REV
segment detail via the Segment Analysis page (already extracted via browser).

Market sheet: IQ_BETA_2YR / IQ_BETA_5YR (already exported via
export_capiq_beta.ps1), IQ_PRICE_52_WK_HIGH, IQ_PRICE_52_WK_LOW,
IQ_AVG_DAILY_VALUE_TRADED_3MO (mnemonic rejected on this entitlement - probe
before wiring).

Estimates sheet: IQ_REVENUE_EST / IQ_EBITDA_EST / IQ_EPS_EST with "IQ_FY+1"
and "IQ_FY+2" period args (forward comps), IQ_EBITDA_EST with 30/90d as-of
dates (EBITDA revisions), guidance fields where covered.
