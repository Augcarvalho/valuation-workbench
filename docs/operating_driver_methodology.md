# Operating Driver Methodology

## Purpose

The operating-driver layer turns a top-down valuation into an auditable
underwriting model. It answers the question an investment committee should ask
before relying on a DCF: **what physical or commercial variables produce the
revenue forecast?**

The system never fabricates an operating statistic. Every company is assigned
an explicit revenue architecture, and the model uses the deepest supported tier:

1. **Tier 3 - physical build:** sourced operating KPIs drive revenue.
2. **Tier 2 - reported segments:** Capital IQ business/geographic segments
   explain mix while reviewed aggregate growth drives the forecast.
3. **Tier 1 - consolidated build:** reviewed revenue growth remains the model
   when neither a complete KPI set nor a useful segment disclosure is available.

The selected tier, missing fields, source, definition, period and reconciliation
status are visible in the application. Missing KPIs remain a refresh queue, not
zeroes or inferred facts.

## Watchlist Architectures

| Company type | Revenue equation | Primary KPI set |
| --- | --- | --- |
| Food retail / store rollout | Average stores x revenue per store | Store count; store-channel revenue |
| Omnichannel apparel | Average stores x store productivity + e-commerce + other channels | Store count; store revenue; e-commerce revenue; other-channel revenue |
| Fitness | Clubs x members per club x revenue per member | Club count; members; revenue/member |
| Fleet leasing | Productive fleet x utilization x revenue per asset | Fleet size; utilization; revenue/vehicle |
| Industrial services | Opening backlog x conversion + awards + recurring services | Backlog; conversion; new orders |
| Subscription software | Customers x recurring revenue/customer + services or usage | Customer count; revenue/customer; recurring share |
| Semiconductors | Shipments x ASP/mix | Shipment volume; average selling price |
| Data-center equipment | Backlog conversion + deliveries + service revenue | Backlog; conversion; service revenue |
| Digital advertising | Monetized volume x revenue per unit + cloud/subscription | Monetized volume; revenue per monetized unit |
| Payments | Total payment volume x take rate + services | TPV; take rate |
| Pharma | Volume x net price/mix + launches - loss of exclusivity | Product volume; net price/mix |
| Consumer lending | Average loans x yield + fees, less funding and credit costs | Average loans; loan yield |

All 26 monitored companies are intentionally mapped in
`src/modeling/operating_drivers.py`. An unknown company does not receive a
silently invented physical model; its profile must be reviewed when it is added.

## Capital IQ And Filing Workflow

Capital IQ Pro Excel remains the normalized data source for financial
statements, market data, consensus, valuation history and reported segments.
Operating statistics require an additional controlled mapping because the
available data item and mnemonic can vary by issuer, sector and entitlement.

1. Run `python scripts/generate_operating_kpi_queue.py`.
2. Review `data_private/operating_kpi_config.csv`.
3. Use Capital IQ Formula Builder or Data Wizard to confirm each requested
   operating statistic. Never guess a mnemonic.
4. Run `scripts/export_capiq_watchlist.ps1`; the workbook refresh creates the
   `operating_kpis_formula` sheet and exports `operating_kpis.csv` locally.
5. Cross-check the same metric against the issuer's latest 10-K/10-Q, annual
   report, results supplement or equivalent filing.
6. Keep the Capital IQ and filing observations as separate rows. The model
   uses the filing definition and displays a 1% reconciliation check wherever
   both sources overlap.

The raw workbook, mnemonic mapping and operating-statistic dataset remain under
`data_private/` and are never committed.

## Omnichannel Retail Formula

For Lululemon and comparable consumer brands:

`Revenue = average stores x store productivity + e-commerce + other channels`

Average stores are used because a year-end store count overstates the revenue
contribution of in-year openings. The first forecast year recognizes half of
net additions; subsequent years recognize half of the prior and current year's
additions. Store productivity is the residual revenue per average store, not
period-end revenue divided by period-end stores.

The Lululemon base case is manually driver-based. FY2026 is anchored to the
midpoint of management's current revenue guidance and incorporates Q1 store
openings, weak Americas comparable sales and international expansion. Later
years assume disciplined openings and gradual channel/productivity recovery.
Bear and Bull paths are separate and editable in the Assumption Workbench.

## Governance

- Automatic paths are permitted as an initial calibration, but are labeled.
- Manual driver paths override top-down revenue growth and feed the same DCF,
  sensitivities, sponsor-return screen and exports.
- The page shows physical KPI coverage across the entire watchlist.
- Source mismatches above 1% are red and must be investigated.
- A filing-only input is labeled `CapIQ refresh-ready`, not `reconciled`.
- Definitions are issuer-specific; comparable sales, active customers and
  backlog must retain the issuer's disclosed definition.
