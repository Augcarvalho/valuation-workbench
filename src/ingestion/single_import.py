"""Merge a single-company Capital IQ staging export into the main export CSVs.

``scripts/export_capiq_single.ps1`` writes one company's data to an isolated
staging folder (``data_private/capiq_exports/staging_single/<ID>``). This module
validates that staging output and *upserts* it into the five main export CSVs:
existing rows for the company are replaced, everything else is untouched. On any
validation failure it raises before writing, so a failed or partial fetch can
never corrupt the good exports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

EXPORTS_DIR = PROJECT_ROOT / "data_private" / "capiq_exports"
STAGING_ROOT = EXPORTS_DIR / "staging_single"

# table filename -> minimum staged rows required for the merge to proceed.
# Estimates/market may legitimately come back empty for thinly covered names.
TABLES = {
    "companies.csv": 1,
    "financials_quarterly.csv": 1,
    "market_data.csv": 0,
    "valuation_history.csv": 0,
    "estimates.csv": 0,
}


@dataclass
class MergeResult:
    company_id: str
    company_name: str
    rows_merged: dict[str, int] = field(default_factory=dict)


def safe_id(company_id: str) -> str:
    return company_id.replace(":", "_")


def staging_dir_for(company_id: str, staging_root: Path | None = None) -> Path:
    root = staging_root if staging_root is not None else STAGING_ROOT
    return root / safe_id(company_id)


def _read_staging_result(staging: Path) -> dict:
    result_path = staging / "staging_result.json"
    if not result_path.exists():
        raise ValueError(f"No staging result found at {result_path} - did the export script run?")
    return json.loads(result_path.read_text(encoding="utf-8-sig"))


def validate_staging(company_id: str, staging: Path) -> dict:
    """Raise ValueError unless the staging folder holds a usable export."""
    result = _read_staging_result(staging)
    if not result.get("ok"):
        raise ValueError(f"Export script reported failure: {result.get('error', 'unknown error')}")
    if result.get("company_id") != company_id:
        raise ValueError(f"Staging folder holds {result.get('company_id')}, expected {company_id}.")

    for name, min_rows in TABLES.items():
        path = staging / name
        if not path.exists():
            raise ValueError(f"Missing staged table {name}.")
        staged = pd.read_csv(path)
        if len(staged) < min_rows:
            raise ValueError(f"Staged {name} has {len(staged)} rows (needs >= {min_rows}).")
        if len(staged) and (staged["company_id"] != company_id).any():
            raise ValueError(f"Staged {name} contains rows for another company.")

    financials = pd.read_csv(staging / "financials_quarterly.csv")
    if financials["revenue"].dropna().empty:
        raise ValueError("Staged financials have no revenue values - Capital IQ returned nothing usable.")
    return result


def merge_single_export(
    company_id: str,
    staging_root: Path | None = None,
    exports_dir: Path | None = None,
) -> MergeResult:
    """Validate the staging export for ``company_id`` and upsert it into the
    main export CSVs. Returns per-table merged row counts."""
    exports = exports_dir if exports_dir is not None else EXPORTS_DIR
    staging = staging_dir_for(company_id, staging_root)
    result = validate_staging(company_id, staging)

    merged = MergeResult(company_id=company_id, company_name=result.get("company_name", ""))
    for name in TABLES:
        staged = pd.read_csv(staging / name)
        main_path = exports / name
        if main_path.exists():
            main = pd.read_csv(main_path)
            main = main[main["company_id"] != company_id]
            combined = pd.concat([main, staged], ignore_index=True)
            # Preserve the main file's column order; staged-only columns append.
            ordered = list(main.columns) + [c for c in staged.columns if c not in main.columns]
            combined = combined[ordered]
        else:
            combined = staged
        combined.to_csv(main_path, index=False)
        merged.rows_merged[name] = len(staged)
    return merged
