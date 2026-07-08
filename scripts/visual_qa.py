"""Headless screenshot QA for the running dashboard.

Captures the key pages at 1280x720 and 1440x900 so chart/layout regressions
are caught by eye before they reach a screen share. The app must already be
running (private instance on :8502 by default).

    python scripts/visual_qa.py
    python scripts/visual_qa.py --url http://localhost:8503 --demo

Privacy: private-mode screenshots contain licensed Capital IQ data, so output
ALWAYS goes to data_private/reports/visual_qa/<timestamp>/ (git-ignored).
A public output path is only allowed together with --demo, for the public
demo dataset - never point a private capture at reports/sample.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_URL = "http://localhost:8502"
DEFAULT_OUT = PROJECT_ROOT / "data_private" / "reports" / "visual_qa"

VIEWPORTS = [(1280, 720), (1440, 900)]

PAGES = [
    "Watchlist Home",
    "Macro Dashboard",
    "Company Situation",
    "Peer Benchmarking",
    "Actual vs Consensus",
    "Company Financials",
    "Capital Structure",
    "Valuation Case",
    "Valuation & Expectations",
    "Data Audit",
]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _wait_settled(page, timeout_ms: int = 45_000) -> None:
    """Wait for Streamlit to finish a rerun (status widget detaches)."""
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached",
                               timeout=timeout_ms)
    except Exception:
        pass  # widget may never have appeared for cheap pages
    page.wait_for_timeout(2_000)  # let Plotly finish drawing


def capture(url: str, out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector('[data-testid="stSidebar"]', timeout=60_000)
            _wait_settled(page)
            for name in PAGES:
                try:
                    page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
                except Exception as exc:
                    print(f"  SKIP {name} ({width}x{height}): {exc}")
                    continue
                _wait_settled(page)
                target = out_dir / f"{_slug(name)}_{width}x{height}.png"
                # Streamlit scrolls inside its own container, so neither
                # full_page nor element screenshots capture below the fold
                # reliably. Grow the viewport to the content height instead.
                content_h = page.evaluate(
                    "() => { const el = document.querySelector('[data-testid=\"stMain\"]');"
                    " return el ? el.scrollHeight : document.body.scrollHeight; }")
                page.set_viewport_size({"width": width,
                                        "height": min(max(height, content_h + 60), 9_000)})
                page.wait_for_timeout(1_200)
                page.screenshot(path=str(target))
                page.set_viewport_size({"width": width, "height": height})
                written.append(target)
                print(f"  ok {target.relative_to(PROJECT_ROOT)}")
            page.close()
        browser.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Screenshot QA for the dashboard.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Running app URL.")
    parser.add_argument("--out", default=None, help="Output folder (default: data_private/reports/visual_qa/<ts>).")
    parser.add_argument("--demo", action="store_true",
                        help="Assert the target app runs the public demo dataset; "
                             "required for any output path outside data_private/.")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / stamp
    # Licensed-data safeguard, same policy as build_dataset: private-mode
    # screenshots must stay inside data_private/.
    if "data_private" not in out_dir.resolve().parts and not args.demo:
        sys.exit(f"Refusing to write screenshots outside data_private/ ({out_dir}). "
                 "Pass --demo only when the target app is running the public demo dataset.")

    print(f"Capturing {len(PAGES)} pages x {len(VIEWPORTS)} viewports from {args.url}")
    written = capture(args.url, out_dir)
    print(f"{len(written)} screenshots -> {out_dir}")


if __name__ == "__main__":
    main()
