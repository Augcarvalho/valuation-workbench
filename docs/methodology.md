# Methodology

## Monitoring Philosophy

The dashboard is built around the questions a PE investment team would ask after receiving quarterly company results:

- Is growth accelerating or decelerating?
- Are margins expanding for the right reasons?
- Is EBITDA converting into cash?
- Is leverage still supportable?
- Does the valuation still make sense versus peers?
- What should management explain at the next board meeting?

## Formula Summary

All financial statement values are stored in BRL millions unless noted otherwise.

| Metric | Formula |
| --- | --- |
| Revenue YoY growth | Revenue / revenue from same quarter prior year - 1 |
| Gross margin | Gross profit / revenue |
| EBITDA margin | EBITDA / revenue |
| FCF conversion | Free cash flow / EBITDA |
| Capex intensity | Capex / revenue |
| Working capital days | Working capital / TTM revenue * 365 |
| Net debt / EBITDA | Net debt / TTM EBITDA |
| Interest coverage | TTM EBITDA / TTM interest expense |
| EV / Revenue | Enterprise value / TTM revenue |
| EV / EBITDA | Enterprise value / TTM EBITDA |
| P/E | Market capitalization / TTM net income |

## Traffic-Light Logic

The traffic-light system is configurable in `src/modeling/thresholds.py`.

Default interpretation:

- Green: KPI is within a range that would generally be acceptable in a PE monitoring pack.
- Yellow: KPI requires explanation or follow-up.
- Red: KPI indicates a potential underwriting, operating, liquidity, or valuation issue.

The default thresholds are intentionally conservative and should be adjusted by sector.

## Peer Percentiles

Peer percentiles are calculated by sector and period when enough comparable companies are available. Higher percentile is treated as better for growth, margins, FCF conversion, and interest coverage. Lower percentile is treated as better for leverage and valuation multiples.

## Peer Groups vs Thesis Themes

Every company carries two separate classifications (`data/reference/company_classification.csv`):

- **Thesis theme** - why the name is on the watchlist (e.g. "Consumer Brand Turnaround", "AI Capex Cycle"). Used for filtering and narrative.
- **Peer group** - what the name actually trades against. Used for all medians, percentiles, and premium/discount math.

A `business_model` field (`operating` / `financial` / `insurer`) drives which metrics are meaningful. Financial institutions are never judged on the EBITDA framework - those signals report **N/M** (not meaningful) - and are read on revenue growth, net income margin, and P/E instead. Managed care uses recalibrated thin-margin thresholds.

## Peer Group Construction (IB Comps Discipline)

Peer groups follow standard investment-banking comparable-company selection: names are
grouped by **business model and value drivers first** (what the revenue line is made of,
margin structure, capital intensity), then end market, with geography and size treated
as disclosed caveats rather than filters. Multiples are unitless ratios, so mixing
currencies inside a comp set is standard street practice; country-risk discounts are a
documented caveat, not a reason to shrink a set below usefulness.

Principles applied to the private universe (composition not published):

- **Same economic engine beats same zip code** - a Brazilian merchant acquirer's primary
  comps are other merchant acquirers, not a "LatAm fintech" catch-all. The structural
  country-risk discount inside a US-heavy median is read as a caveat, not filtered away.
- **Coherent infrastructure sets over sector labels** - subscription data/analytics and
  financial processing names form a "mission-critical financial infrastructure" set even
  when their GICS labels differ.
- **Broad sets are labeled broad** - when true comps sit outside the exported universe,
  the group is kept for context but explicitly flagged as *not comp evidence*, with the
  expansion candidates named in the review queue.
- **Cross-model masking inside mixed groups** - `financial` names inside an otherwise
  operating theme keep their P/E / P/TBV framework; the group median never forces an
  EBITDA lens onto a lender.
- **Country sets where the local universe is thin** - standard practice for small
  exchanges; disclosed on the page.

The static taxonomy is the *fallback*. For real work, the per-anchor approved peer set
(Peer Benchmarking page editor, or a Capital IQ comp-set import) overrides it - that is
where single-name nuance belongs.

## Watchlist Verdict

Each company gets a headline verdict in `src/modeling/assessment.py`, combining the *applicable* operating signals with valuation versus the peer-group median multiple (EV/EBITDA for operating companies, P/E for financials):

| Verdict | Trigger |
| --- | --- |
| **Do Work** | Deteriorating core KPIs with the market already pricing it (>=15% discount) - the value-trap-vs-entry debate; or an on-track operating profile trading at a >=15% discount - potential mispriced quality |
| **Constructive** | Operating profile on track; valuation not a blocker (a rich multiple is noted, not penalized) |
| **Watch** | Mixed signals, one isolated red, or incomplete valuation context - no forced action |
| **Avoid / Pass** | Deteriorating KPIs without valuation support |

TTM metrics require a full four-quarter window (`ttm_complete` flags partial history rather than annualizing it silently). Premiums beyond +/-500% are treated as broken inputs (e.g. currency-unit mismatches on cross-listed names) and degrade to "valuation context incomplete" instead of polluting the verdict.

The same assessment object also produces the executive commentary, investment view, key positives, key concerns, management questions, and the valuation premium/discount narrative. This keeps the dashboard and the exported board pack perfectly consistent because both consume one judgment layer.

## Valuation Framing

EV/EBITDA, EV/Revenue, and P/E are each compared to the sector peer median. A premium above ~10% to the peer median is flagged as "premium" (defensible only if growth and margin quality are top-quartile); a discount below ~10% is flagged as a potential re-rating candidate. The "What needs to be true" logic translates the premium/discount into the operational conditions that would justify it.

## Data Caveats

Public data is not a replacement for internal monthly portfolio-company reporting. The dashboard therefore uses quarterly reported financials, prior-year comparisons, public-market valuation, and optional Capital IQ consensus/guidance exports.

For an actual PE portfolio company, the same schema can be expanded to include monthly budget, initiatives, sales pipeline, churn, operational KPIs, and covenant certificates.

## Data Audit

Nine check families run over the dataset and raw exports (Data Audit page):
market-cap bridge (price x shares vs cap; 5/15/30% tiers), EV bridge
(cap + debt + minority + preferred - cash vs reported TEV; cash means cash &
ST investments - CapIQ's TEV basis - when exported, plain cash & equivalents
otherwise; partial bridges labeled), cross-table unit sanity, CFO/capex/FCF sign conventions (flagged,
never silently flipped), TTM completeness, stale periods (real dates),
refresh-log consistency, missing deep fields (critical vs nice-to-have),
and outlier metrics. Per-company audit score: 100 - 15/high - 5/medium - 1/low.

## Multi-Multiple Framework

No single multiple is "the" valuation. The dashboard assigns each multiple a
role per company - **Primary / Secondary / Cross-check / Not meaningful** -
based on the business model (`src/modeling/multiples.py`):

| Company type | Primary | Secondary | Cross-check | Never forced |
| --- | --- | --- | --- | --- |
| Software / high-growth / negative EBITDA | EV/Revenue | EV/EBITDA (only if positive) | P/E if profitable | - |
| Mature operating | EV/EBITDA | P/E | EV/Revenue | - |
| Consumer / retail / branded | EV/EBITDA + P/E | - | EV/Revenue (margin-aware) | - |
| Financials / lenders | P/E + P/TBV | - | ROE vs COE (financials page) | EV/EBITDA, EV/Revenue |

**Why each multiple:**
- **EV/Revenue** - when the profit line is not yet informative (investment
  phase, margin reset, negative EBITDA). A revenue multiple embeds an implicit
  margin assumption, so it is only a *cross-check* for profitable names.
- **EV/EBITDA** - the workhorse for operating companies: capital-structure
  neutral, closest proxy for pre-capex operating cash flow.
- **P/E** - meaningful when earnings are positive and reasonably clean; adds
  the leverage and tax reality EV/EBITDA deliberately ignores.
- **P/TBV** - for financials the balance sheet *is* the business; tangible
  book is productive capital and pairs with ROE (justified P/B = (ROE-g)/(COE-g)).
  EV multiples are never forced onto banks - debt is raw material, not financing.

**NTM P/E** = current price / NTM consensus EPS (`eps_est_ntm`); negative,
zero, or missing forward EPS renders N/M and never enters a median.

**Historical percentiles** - the current multiple is ranked against the
company's own monthly valuation history (share of past observations below
today's value; negative-multiple months dropped; minimum 8 observations).
Regime zones: bottom quartile / below median / near median / above median /
top quartile.

**Multiple momentum** - company multiple change vs peer-median change over
3/6/12 months (monthly closes, nearest observation within 45 days). 12m move
>= +/-10% = re-rating/de-rating; relative-to-peers gap >= 5% = company-specific,
otherwise sector-driven. The re-rating bridge decomposes the 12m price move
into fundamental-per-share x multiple x residual (approximate for EV multiples;
the residual absorbs net debt and share-count effects - always labeled).

## Outlier handling in comps

Multiples are excluded from the ADJUSTED median when: EBITDA or earnings are
negative, EV/EBITDA > 75x, P/E > 100x, EV/Revenue > 50x. Raw medians remain
displayed; excluded names are listed with reasons. Softer flags (never
excluded): FCF conversion outside [-100%, 200%], leverage outside [-5x, 8x],
revenue growth > 100%, EBITDA margin outside [-50%, 80%]. The DCF exit
multiple uses the adjusted median (FY1 preferred, then NTM, then LTM).

## Peer review workflow

Peer sets carry inclusion_status (suggested/approved/rejected/manually_added),
reviewed_at, and reviewer_note. Rejected members remain on file for audit but
never feed analytics. Generated and official CapIQ sets stay UNREVIEWED until
the analyst explicitly approves (Peer Benchmarking review actions). Hierarchy:
analyst-approved set > reviewed CapIQ comp set > unreviewed generated set
(labeled directional) > static peer group > full universe (high warning).

## Financials-specific valuation

business_model == financial routes to: P/E, P/B (P/TBV only when tangible
common equity is exported - equity fallback is labeled), ROE vs cost of
equity, justified P/B = (ROE - g)/(COE - g), and a residual-income model
(book value + PV of excess returns). Guardrails: negative book/earnings,
COE <= g, extreme ROE.
