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

Financial statement values are stored in each company's reporting currency,
in millions unless noted otherwise. Cross-currency size comparisons use the
explicit USD normalization fields; ratios and multiples remain unitless.

| Metric | Formula |
| --- | --- |
| Revenue YoY growth | Revenue / revenue from same quarter prior year - 1 |
| Gross margin | Gross profit / revenue |
| EBITDA margin | EBITDA / revenue |
| FCF conversion | Free cash flow / EBITDA |
| Capex intensity | Capex / revenue |
| Working capital days | Operating working capital / LTM revenue * 365 |
| Net debt / EBITDA | Net debt / LTM EBITDA |
| Interest coverage | LTM EBITDA / LTM interest expense |
| EV / Revenue | Enterprise value / LTM revenue |
| EV / EBITDA | Enterprise value / LTM EBITDA |
| P/E | Market capitalization / LTM net income |

## Operating Driver Architecture

Every monitored company is mapped to an explicit business-model equation.
Revenue is built at the deepest defensible level: physical operating KPIs
(Tier 3), reported Capital IQ segments (Tier 2), or reviewed consolidated
growth (Tier 1). Missing metrics remain visible in the Excel refresh queue and
are never replaced by synthetic values.

For omnichannel retail, revenue equals average stores times store productivity,
plus e-commerce and other-channel revenue. Average stores, rather than the
period-end count, captures the partial-year contribution of openings. Manual
physical-driver paths supersede the top-down revenue-growth path and feed the
same DCF and return analyses. Capital IQ and filing observations remain
separate and are reconciled at a 1% tolerance.

See [Operating Driver Methodology](operating_driver_methodology.md) for the
equations, source hierarchy, Formula Builder workflow and governance rules.

## Period And Market-Date Convention

The presentation separates the three clocks that coexist in public-company analysis:

- **Latest quarter** means the standalone reported fiscal quarter. Revenue growth is
  compared with the same quarter one year earlier.
- **LTM** means the four consecutive reported quarters ending on each company's latest
  financial period. Margins, cash conversion, returns, leverage denominators, and
  trailing valuation multiples use this basis.
- **NTM / FY1 / FY2** means forward consensus estimates as labeled.
- **Market snapshot** means the price, market capitalization, and enterprise value
  retrieved from the market-data source. Its retrieval date is displayed separately
  from the financials-through date.

Peers can have different financials-through dates because fiscal calendars and filing
dates differ. The selected company remains visible in tables and charts but is excluded
from peer medians, quartiles, and percentile statistics. Flagged multiple outliers are
also excluded from adjusted peer statistics and remain visible with disclosure.

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

LTM metrics require four consecutive reported quarters (`ttm_complete` flags partial history rather than annualizing it silently). Extreme premiums remain visible; the Data Audit & Refresh and outlier rules determine whether the underlying multiple is reliable rather than suppressing a valuation observation solely because the premium is large.

The same assessment object also produces the executive commentary, investment view, key positives, key concerns, management questions, and the valuation premium/discount narrative. This keeps the dashboard and the exported board pack perfectly consistent because both consume one judgment layer.

## Valuation Framing

EV/EBITDA, EV/Revenue, and P/E are each compared to the sector peer median. A premium above ~10% to the peer median is flagged as "premium" (defensible only if growth and margin quality are top-quartile); a discount below ~10% is flagged as a potential re-rating candidate. The "What needs to be true" logic translates the premium/discount into the operational conditions that would justify it.

## Data Caveats

Public data is not a replacement for internal monthly portfolio-company reporting. The dashboard therefore uses quarterly reported financials, prior-year comparisons, public-market valuation, and optional Capital IQ consensus/guidance exports.

For an actual PE portfolio company, the same schema can be expanded to include monthly budget, initiatives, sales pipeline, churn, operational KPIs, and covenant certificates.

## Data Audit & Refresh

Nine check families run over the dataset and raw exports (Data Audit & Refresh page):
market-cap bridge (price x shares vs cap; 5/15/30% tiers), EV bridge
(cap + debt + minority + preferred - cash vs reported TEV; cash means cash &
ST investments - CapIQ's TEV basis - when exported, plain cash & equivalents
otherwise; partial bridges labeled), cross-table unit sanity, CFO/capex/FCF sign conventions (flagged,
never silently flipped), LTM completeness, stale periods (real dates),
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
revenue growth > 100%, EBITDA margin outside [-50%, 80%]. Peer FY1/NTM/LTM
medians are market references; they do not automatically become terminal
multiples in the intrinsic DCF.

## DCF terminal-value consistency

The explicit forecast uses company-specific WACC and operating drivers. Auto
cases extend to ten detailed years when current growth exceeds 10% or current
EV/EBITDA exceeds 15x; otherwise the detailed horizon is five years. If any
scenario has not reached the perpetual growth rate, the engine appends a
disclosed two-to-five-year transition period, limiting the annual fade to
approximately 200bps. This prevents an artificial jump from year N into the
perpetuity. A manual review may set ``transition_years`` explicitly in the private
assumptions YAML.

The Streamlit **Assumption Workbench** is the governed front end to those YAML
files. It loads the currently resolved automatic values before any manual
edits anything. Unchanged fields remain automatic; only deviations are written
as company-specific overrides. Partial scenario overrides inherit the proper
Bear/Base/Bull defaults for every untouched driver. Saving performs structural
and finance checks, atomically replaces the private YAML, archives the prior
version, appends a local audit entry, and rebuilds every valuation output from
the saved set. Restoring automatic assumptions also archives the manual-input file
before removing it.

The stable period then normalizes three linked inputs:

- terminal beta converges to 1.0 and debt weight to the peer median;
- terminal ROIC converges to the peer median when at least three valid peers
  exist (otherwise the capped company anchor is used), with terminal WACC as
  the neutral competitive floor for mechanically generated cases;
- stable reinvestment rate = perpetuity growth / terminal ROIC.

The Gordon terminal cash flow is therefore:

`FCFF(n+1) = NOPAT(n+1) x (1 - g / terminal ROIC)`

and terminal value is `FCFF(n+1) / (terminal WACC - g)`. This prevents current
capex spikes, D&A above capex, or zero reinvestment from being carried into
perpetuity without an economic link to growth.

In auto mode, the displayed DCF exit multiple is the EV/EBITDA expression of
the same stable-growth economics. The independent adjusted peer multiple is
shown separately as **Market Reference**. It enters the DCF only through an
explicit manual assumption in the company YAML; this avoids silently mixing
relative valuation with intrinsic valuation.

This follows the internally consistent FCFF framework described by Aswath
Damodaran: stable growth must be sustainable in the cash-flow currency,
reinvestment must equal ``g / ROIC``, beta and leverage should converge toward
stable-company levels, and a market-derived exit multiple is a relative-value
cross-check rather than an intrinsic terminal-value input. Primary references:

- [Estimating Terminal Value](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalapproaches.htm)
- [Excess Returns and Terminal Value](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm)
- [Stable-growth project guidance](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/project/prques.htm)

## Valuation diagnostics and human review

The valuation case separates three classes of finding:

- **Model integrity exceptions**: invalid Gordon math, non-positive implied
  equity, out-of-bounds drivers, or an abrupt unresolved stable-state jump.
- **Manual review queue**: default beta, fallback borrowing cost, draft/auto
  assumptions, missing working-capital inputs, or an unapproved peer set.
- **Valuation cross-checks**: market-versus-fundamental multiple gaps, terminal
  value concentration, extreme upside/downside, or negative terminal spreads.

Only the first class means the model cannot be relied upon mechanically. The
other two are intentionally preserved because valuation requires human
judgment; relabeling them prevents normal investment debate from looking like
a software error while keeping every caveat visible.

A final case may close an interpretive market cross-check only through a
documented `reviewed_cross_checks` rationale in the versioned assumptions file.
This acknowledgement records why the reviewed underwriting case deliberately
differs from the market reference; it does not alter the calculation. Data
contract failures, readiness blockers, and model-integrity exceptions cannot be
acknowledged away and must be corrected before the case can be marked IC-ready.

## Peer review workflow

Peer sets carry inclusion_status (suggested/approved/rejected/manually_added),
reviewed_at, and reviewer_note. Rejected members remain on file for audit but
never feed analytics. Generated and official CapIQ sets stay UNREVIEWED until
the reviewer explicitly approves (Peer Benchmarking review actions). Hierarchy:
manually approved set > reviewed CapIQ comp set > unreviewed generated set
(labeled directional) > static peer group > full universe (high warning).

## Financials-specific valuation

business_model == financial routes to: P/E, P/B (P/TBV only when tangible
common equity is exported - equity fallback is labeled), ROE vs cost of
equity, justified P/B = (ROE - g)/(COE - g), and a residual-income model
(book value + PV of excess returns). Guardrails: negative book/earnings,
COE <= g, extreme ROE.
