"""Replace the stale market_data TEV with the latest dated TEV print.

Root cause: the market snapshot exported TEV via bare IQ_ENTERPRISE_VALUE,
which returns a period print that can sit months behind the live price and
market cap (AMD +213%, ADBE -36% EV-bridge gaps). The monthly valuation
history pulls IQ_TEV with an explicit as-of date, which IS date-consistent.
This script overwrites market_data.enterprise_value with each company's most
recent valuation-history TEV (still a CapIQ-reported figure, ~month-end).
The export script now pulls dated TEV directly, so this patch is only needed
once for the current cycle.

A .bak copy of market_data.csv is written before modifying.

    python scripts/patch_market_tev.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = PROJECT_ROOT / "data_private" / "capiq_exports"
MARKET = EXPORTS / "market_data.csv"
VALUATION = EXPORTS / "valuation_history.csv"


def main() -> None:
    if not VALUATION.exists():
        sys.exit(f"{VALUATION} not found.")
    market = pd.read_csv(MARKET)
    vh = pd.read_csv(VALUATION, parse_dates=["date"])
    last = (vh.dropna(subset=["enterprise_value"])
              .sort_values("date").groupby("company_id").tail(1)
              .set_index("company_id"))

    shutil.copy2(MARKET, MARKET.with_suffix(".csv.bak"))
    replaced = 0
    for i, row in market.iterrows():
        cid = row["company_id"]
        if cid in last.index:
            market.loc[i, "enterprise_value"] = float(last.loc[cid, "enterprise_value"])
            replaced += 1
    market.to_csv(MARKET, index=False)
    as_of = last["date"].max().date() if len(last) else "n/a"
    print(f"Replaced TEV for {replaced}/{len(market)} names with dated prints (as of ~{as_of}).")
    print("Backup:", MARKET.with_suffix(".csv.bak").name)


if __name__ == "__main__":
    main()
