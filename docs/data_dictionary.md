# Data Dictionary

## companies.csv

| Column | Description |
| --- | --- |
| company_id | Stable company identifier used across all tables |
| ticker | Public ticker, including exchange suffix where available |
| company_name | Legal or display name |
| sector | Monitoring peer group |
| exchange | Listing venue |
| currency | Reporting currency |
| source | Primary source used for the row |

## financials_quarterly.csv

| Column | Description |
| --- | --- |
| company_id | Stable company identifier |
| period | Quarter-end date |
| revenue | Revenue |
| gross_profit | Gross profit |
| ebitda | EBITDA |
| ebit | EBIT |
| net_income | Net income |
| cfo | Cash flow from operations |
| capex | Capital expenditures, stored as positive cash outflow |
| fcf | Free cash flow |
| cash | Cash and short-term investments |
| total_debt | Total debt |
| net_debt | Total debt minus cash |
| working_capital | Current assets minus current liabilities |
| interest_expense | Interest expense, stored as positive expense |
| source | Data source |

## market_data.csv

| Column | Description |
| --- | --- |
| company_id | Stable company identifier |
| period | Quarter-end date |
| share_price | Closing share price near quarter end |
| shares_outstanding | Shares outstanding |
| market_cap | Market capitalization |
| enterprise_value | Market cap plus net debt |
| source | Data source |

## estimates.csv

| Column | Description |
| --- | --- |
| company_id | Stable company identifier |
| period | Quarter-end date |
| revenue_consensus | Revenue consensus or guidance midpoint |
| ebitda_consensus | EBITDA consensus or guidance midpoint |
| guidance_low | Low end of management guidance |
| guidance_high | High end of management guidance |
| source | Data source |

## source_log.csv

| Column | Description |
| --- | --- |
| table_name | Dataset or table name |
| source_name | Source provider or public source |
| source_url | URL or local export reference |
| retrieved_at | Retrieval date |
| notes | Notes on transformation or limitations |

## Optional fields (export v3)

All optional: absent columns load as NA, never faked.

Financials: minority_interest, preferred_equity, lease_liabilities,
pension_liabilities, non_operating_assets, tangible_common_equity, book_value,
deposits, loans, net_interest_income, provision_expense.

Market data: beta_2y, beta_5y, diluted_market_cap, avg_daily_value_traded,
week52_high, week52_low.

Estimates: revenue/ebitda/eps_est_fy1 and _fy2 (forward comps),
ebitda_est_ntm_30d/90d_ago (EBITDA revisions), guidance_metric.
