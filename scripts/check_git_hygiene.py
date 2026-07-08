"""Git hygiene guard: licensed/private data must never be trackable.

Checks (exit code 1 on any violation):
1. No file under ``data_private/`` is tracked or staged.
2. Representative private paths are matched by .gitignore.
3. No tracked file anywhere carries a Capital IQ raw-export signature name.

Run manually or via pytest (tests/test_templates_and_safety.py).

    python scripts/check_git_hygiene.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MUST_BE_IGNORED = [
    "data_private/capiq_exports/raw.xlsx",
    "data_private/capiq_exports/valuation_history.csv",
    "data_private/processed/monitoring_dataset.csv",
    "data_private/assumptions/NASDAQ_LULU.yaml",
    "data_private/theses/NASDAQ_LULU.yaml",
    "data_private/reports/valuation_case_LULU.html",
    "data_private/universe.csv",
]

FORBIDDEN_TRACKED_PATTERNS = ["capiq_watchlist_workbook", "capiq_export_workbook"]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


def run_checks() -> list[str]:
    violations: list[str] = []

    tracked_private = _git("ls-files", "data_private")
    if tracked_private:
        violations.append(f"TRACKED files under data_private/: {tracked_private.splitlines()[:5]}")

    staged = _git("diff", "--cached", "--name-only")
    staged_private = [p for p in staged.splitlines() if p.startswith("data_private")]
    if staged_private:
        violations.append(f"STAGED private files: {staged_private[:5]}")

    for path in MUST_BE_IGNORED:
        result = subprocess.run(
            ["git", "check-ignore", path], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            violations.append(f"NOT ignored by .gitignore: {path}")

    all_tracked = _git("ls-files").splitlines()
    for pattern in FORBIDDEN_TRACKED_PATTERNS:
        hits = [p for p in all_tracked if pattern in p]
        if hits:
            violations.append(f"Raw CapIQ workbook tracked: {hits}")

    return violations


def main() -> int:
    violations = run_checks()
    if violations:
        print("GIT HYGIENE VIOLATIONS:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("git hygiene OK: no private data tracked, staged, or unignored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
