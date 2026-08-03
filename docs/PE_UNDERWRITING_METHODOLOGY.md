# PE Underwriting Methodology

## Purpose and scope

The platform is a public-company underwriting and sponsor-feasibility workbench. It uses local S&P Capital IQ Excel exports to screen companies, govern comparable-company sets, build a transparent operating forecast, value the business, test a hypothetical sponsor capital structure and produce an investment-committee memo. It is not a substitute for private-company diligence, a quality-of-earnings report, lender term sheets or legal review.

Private Capital IQ exports, assumption overrides, review histories and generated private reports remain under `data_private/` and are excluded from version control. The public repository contains code, empty templates and a separate demonstrative dataset only.

## Governed data contract

Each financial observation retains the issuer's exact fiscal period end, fiscal year, fiscal quarter and canonical `fiscal_period_id`. Calendar-quarter keys are used only to attach market and consensus snapshots. Duplicate company/fiscal-period observations, invalid periods and missing required columns block a new build before it can replace the current dataset.

Every successful build creates `build_manifest.json` with a deterministic build ID, schema version, source mode, row counts, company count, fiscal range, timestamps and warnings. TTM calculations require four consecutive issuer fiscal quarters; incomplete windows remain unavailable rather than being annualized.

## Case identity and readiness

Every operating-company underwrite receives a deterministic case ID derived from the fiscal observation, assumptions, WACC, peer set and methodology version. The same canonical case feeds the interactive valuation page, sponsor returns, standalone valuation report and IC memo.

Readiness is explicit:

| Status | Meaning |
| --- | --- |
| `DATA_BLOCKED` | Fiscal identity, TTM data or high-severity audit checks are unresolved. |
| `SCREENING_ONLY` | The automated case is directional; assumptions and peers are not both reviewed. |
| `MODEL_READY` | The model runs, but at least one governance or WACC input remains unresolved. |
| `MANUALLY_REVIEWED` | Core judgments are reviewed; medium-severity data warnings remain visible. |
| `IC_READY` | Data gates pass, assumptions are final, peers are approved and WACC does not use fallbacks. |

Only an `IC_READY` case is labeled final. Other exports are explicitly labeled screening materials.

## Valuation methodology

The DCF converts revenue and margin assumptions into EBIT, taxes, reinvestment and unlevered free cash flow. The explicit forecast and terminal value are discounted at WACC. Perpetuity growth must remain below terminal WACC and is cross-checked against terminal ROIC and the implied reinvestment rate. The market exit multiple is a separate cross-check; it is not forced to equal the Gordon-consistent multiple.

The enterprise-to-equity bridge deducts gross debt, minority interests, preferred equity and pension liabilities, adds non-operating assets and only credits cash above restricted/minimum cash. Target price uses diluted shares when available. Missing bridge items remain disclosed.

Bottom-up peer beta is the preferred cost-of-equity input. Observed company beta is a cross-check/fallback. Cost of debt uses, in order, a manual input, observed debt yield, interest expense over average debt, or a disclosed fallback. The WACC panel records the source of every component.

Financial institutions are excluded from EBITDA DCF and sponsor leverage calculations. Their applicable framework uses P/E, P/TBV, ROE versus cost of equity and excess-return logic. NIM, provision cost, efficiency ratio, CET1, NPL ratio and reserve coverage appear only when the corresponding Capital IQ fields are exported; unavailable metrics remain `n/a`.

## Sponsor feasibility and debt capacity

The LBO uses an explicit 3-, 5- or 7-year hold period independent of the DCF horizon. Sources and uses include purchase equity, refinancing, minimum cash, transaction fees, financing fees/OID, term debt, rollover and sponsor equity. Sources must equal uses.

The annual debt schedule calculates cash interest, deductibility limits, tax shield, mandatory amortization, revolver draws/repayments, cash sweep, minimum cash, ending debt, leverage and interest coverage. A shortfall after exhausting the revolver makes the case invalid. Sponsor returns use sponsor ownership after rollover and reconcile to a value-creation bridge.

Debt capacity is the lower of a gross-leverage limit and an interest-coverage limit. Incremental capacity is measured against existing gross debt and preserves minimum cash. Screening covenant levels are not presented as actual credit-document terms.

## Human-review controls

Human judgment is required before a case becomes final:

1. Review data-audit exceptions and the fiscal-period mapping.
2. Approve or adjust the Capital IQ-suggested peer set, with rejected names retained in the review record.
3. Review operating, WACC, terminal-value, minimum-cash, leverage and covenant assumptions.
4. Reconcile DCF, trading comps and sponsor returns; explain material differences rather than averaging them mechanically.
5. Confirm thesis, catalysts, risks, diligence questions and the investment decision.

Private monitoring extensions accept monthly budget-versus-actual, covenant, value-creation and ownership templates. These files remain optional because public-company Capital IQ data cannot recreate internal portfolio-company reporting.

## Limitations

- Public filings and Capital IQ consensus do not provide a quality-of-earnings adjustment, customer cohort data, legal diligence or actual financing terms.
- The sponsor case is a feasibility screen until entry price, leverage, debt tranches, cash taxes, management rollover and covenants are underwritten manually.
- Consensus surprise analysis requires a point-in-time pre-report snapshot; comparing an actual with a current post-report estimate is labeled directional.
- Licensed Capital IQ data must not be committed, redistributed or embedded in public screenshots beyond the user's license rights.
