"""Merge ev_bridge_patch.csv into financials_quarterly.csv (latest rows).

The targeted EV-bridge export pulls TEV components (minority interest,
preferred equity, leases, pensions, cash incl. ST investments, tangible
common equity) for the LATEST fiscal quarter only. This script writes those
values onto each company's latest-period row in financials_quarterly.csv;
the loader then carries them into the dataset as the already-plumbed
optional columns. Older quarters stay NaN by design.

A .bak copy of financials_quarterly.csv is written before modifying.

    python scripts/patch_ev_bridge_fields.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = PROJECT_ROOT / "data_private" / "capiq_exports"
FIN = EXPORTS / "financials_quarterly.csv"
PATCH = EXPORTS / "ev_bridge_patch.csv"

FIELDS = ["minority_interest", "preferred_equity", "lease_liabilities",
          "pension_liabilities", "cash_st_invest", "tangible_common_equity"]


def main() -> None:
    if not PATCH.exists():
        sys.exit(f"{PATCH} not found - run scripts/export_capiq_ev_bridge.ps1 first.")
    fin = pd.read_csv(FIN)
    patch = pd.read_csv(PATCH)
    patch = patch.dropna(subset=["company_id"]).set_index("company_id")

    shutil.copy2(FIN, FIN.with_suffix(".csv.bak"))

    for col in FIELDS:
        if col not in fin.columns:
            fin[col] = pd.NA

    latest_idx = (fin.sort_values("period").groupby("company_id").tail(1)).index
    patched = 0
    per_field = {c: 0 for c in FIELDS}
    for i in latest_idx:
        cid = fin.loc[i, "company_id"]
        if cid not in patch.index:
            continue
        src = patch.loc[cid]
        wrote = False
        for col in FIELDS:
            v = src.get(col)
            if pd.notna(v):
                fin.loc[i, col] = float(v)
                per_field[col] += 1
                wrote = True
        patched += int(wrote)

    fin.to_csv(FIN, index=False)
    print(f"Patched latest-quarter rows for {patched} companies -> {FIN.name}")
    print("Field coverage:", {k: v for k, v in per_field.items()})
    print("Backup:", FIN.with_suffix(".csv.bak").name)
    print("Next: python -m src.pipeline.build_dataset --source capiq "
          "--input data_private/capiq_exports "
          "--output data_private/processed/monitoring_dataset.csv")


if __name__ == "__main__":
    main()
