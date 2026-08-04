"""Capture the curated README gallery from the running private dashboard.

This script writes derived analytical screenshots, never raw Excel exports.
Because the private app can display licensed data, publishing requires an
explicit acknowledgement on every run.

    python scripts/capture_readme_gallery.py \
        --company LULU --confirm-derived-private-output
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "sample" / "browser" / "current"


@dataclass(frozen=True)
class Capture:
    filename: str
    anchor: str | None = None
    offset: int = 0


OPERATING_CAPTURES = [
    Capture("04e_operating_driver_history.png"),
    Capture("04f_operating_driver_projection.png", "Base Revenue Build", -80),
]

PEER_CAPTURES = [
    Capture("02_compare.png", "Side-by-Side Comparison", -70),
]

VALUATION_CAPTURES = [
    Capture("08_valuation_case_top.png"),
    Capture("08_assumption_workbench.png", "Assumption Workbench | Edit valuation assumptions", -70),
    Capture("08j_operating_driver_assumptions.png", "Operating revenue drivers", -70),
    Capture("08h_assumption_drivers.png", "Base case", -120),
    Capture("08i_assumption_terminal.png", "Discount rate and terminal value", -70),
    Capture("08a_key_assumptions.png", "Key Valuation Assumptions", -70),
    Capture("08b_valuation_range.png", "Valuation Range", -70),
    Capture("08b1_sensitivity_matrix.png", "Valuation Range", 520),
    Capture("08b2_range_detail.png", "From Assumptions to Cash Flow", -620),
    Capture("08c_forecast_and_fcf.png", "From Assumptions to Cash Flow", -70),
    Capture("08d_valuation_mechanics.png", "Valuation Mechanics", -70),
    Capture("08e_sponsor_returns.png", "Sponsor Feasibility - LBO Returns", -70),
    Capture("08f_market_context.png", "Market Context", -70),
    Capture("08g_provenance_and_export.png", "Assumptions Provenance", -70),
    Capture("09_valuation_snapshot.png", "Valuation & Market Expectations", -70),
    Capture("09b_historical_multiples.png", "Historical Multiples", -70),
    Capture("09c_scenario_returns.png", "Public-Market Scenario Returns", -70),
]

DATA_GOVERNANCE_CAPTURES = [
    Capture("11_data_audit_charts.png", "Findings Overview", -70),
    Capture("11b_urgent_findings.png", "Most Urgent Fixes", -70),
    Capture("11c_company_audit_scores.png", "Company Audit Scores", -70),
    Capture("12_data_governance.png", "Refresh, Coverage & Provenance", -70),
    Capture("12b_add_company.png", "Add Company", -70),
    Capture("12c_source_log.png", "Source Log", -70),
]


def _wait_settled(page, timeout_ms: int = 60_000) -> None:
    try:
        page.wait_for_selector(
            '[data-testid="stStatusWidget"]', state="detached", timeout=timeout_ms
        )
    except Exception:
        pass
    page.wait_for_timeout(1_800)


def _select_company(page, ticker: str) -> None:
    selector = page.locator('[data-testid="stSidebar"] [role="combobox"]').first
    selector.click()
    selector.fill(ticker.upper())
    selector.press("Enter")
    _wait_settled(page)


def _open_page(page, name: str) -> None:
    page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
    _wait_settled(page)
    page.locator('[data-testid="stMain"]').evaluate("el => { el.scrollTop = 0; }")
    page.wait_for_timeout(300)


def _scroll_to(page, anchor: str | None, offset: int = 0) -> None:
    main = page.locator('[data-testid="stMain"]')
    if anchor is None:
        main.evaluate("el => { el.scrollTop = 0; }")
        return
    target = page.get_by_text(anchor, exact=True).first
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    if box is None:
        raise RuntimeError(f"Unable to locate screenshot anchor: {anchor}")
    delta = float(box["y"]) - 80.0 + float(offset)
    main.evaluate("(el, amount) => { el.scrollBy(0, amount); }", delta)
    page.wait_for_timeout(550)


def _capture(page, output: Path, specification: Capture) -> None:
    _scroll_to(page, specification.anchor, specification.offset)
    target = output / specification.filename
    page.screenshot(path=str(target), animations="disabled")
    print(f"  ok {target.relative_to(PROJECT_ROOT)}")


def capture(url: str, output: Path, company: str) -> None:
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1584, "height": 1000},
            device_scale_factor=2,
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="stSidebar"]', timeout=60_000)
        _wait_settled(page)
        _select_company(page, company)

        _open_page(page, "Peer Benchmarking")
        for specification in PEER_CAPTURES:
            _capture(page, output, specification)

        _open_page(page, "Operating Drivers")
        for specification in OPERATING_CAPTURES:
            _capture(page, output, specification)

        _open_page(page, "Valuation Case")
        _capture(page, output, VALUATION_CAPTURES[0])

        workbench = page.get_by_text(
            "Assumption Workbench | Edit valuation assumptions", exact=True
        ).first
        workbench.click()
        _wait_settled(page)
        for specification in VALUATION_CAPTURES[1:6]:
            _capture(page, output, specification)

        workbench.click()
        _wait_settled(page)
        for specification in VALUATION_CAPTURES[6:]:
            _capture(page, output, specification)

        _open_page(page, "Data Audit & Refresh")
        for specification in DATA_GOVERNANCE_CAPTURES:
            _capture(page, output, specification)

        context.close()
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the private README gallery.")
    parser.add_argument("--url", default="http://localhost:8502")
    parser.add_argument("--company", default="LULU")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--confirm-derived-private-output", action="store_true")
    args = parser.parse_args()
    if not args.confirm_derived_private_output:
        raise SystemExit(
            "Refusing to publish private-mode screenshots without "
            "--confirm-derived-private-output. Review the images before committing."
        )
    capture(args.url, args.output, args.company)


if __name__ == "__main__":
    main()
