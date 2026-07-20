"""Generate demo side tables (valuation history, consensus estimates) offline.

Derives everything from the committed public-demo CSVs so no network access is
needed and no licensed data is involved. The outputs are deliberately labeled
synthetic: valuation history reuses the quarterly demo price points, and
"consensus" is actuals perturbed by a deterministic small delta — enough to
exercise the percentile, revision-momentum, and beats/misses machinery in demo
mode without pretending to be real consensus data.

    python scripts/generate_demo_side_data.py
"""

from __future__ import annotations

import sys
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import SAMPLE_PUBLIC_DIR
from src.utils import write_csv

SOURCE_LABEL = "Synthetic demo series (derived from public demo actuals)"


def _load() -> tuple[pd.DataFrame, pd.DataFrame]:
    fin = pd.read_csv(SAMPLE_PUBLIC_DIR / "financials_quarterly.csv", parse_dates=["period"])
    mkt = pd.read_csv(SAMPLE_PUBLIC_DIR / "market_data.csv", parse_dates=["period"])
    return fin.sort_values(["company_id", "period"]), mkt.sort_values(["company_id", "period"])


def build_valuation_history(fin: pd.DataFrame, mkt: pd.DataFrame) -> pd.DataFrame:
    df = fin.merge(mkt, on=["company_id", "period"], how="inner", suffixes=("", "_mkt"))
    df = df.sort_values(["company_id", "period"])
    grouped = df.groupby("company_id", group_keys=False)
    for col in ["revenue", "ebitda", "net_income"]:
        df[f"{col}_ltm"] = grouped[col].transform(lambda s: s.rolling(4, min_periods=4).sum())

    def _ratio(num, den):
        den = den.where(den > 0)
        return num / den

    out = pd.DataFrame({
        "company_id": df["company_id"],
        "date": df["period"],
        "share_price": df["share_price"],
        "market_cap": df["market_cap"],
        "enterprise_value": df["enterprise_value"],
        "ev_to_ebitda_ltm": _ratio(df["enterprise_value"], df["ebitda_ltm"]),
        "ev_to_revenue_ltm": _ratio(df["enterprise_value"], df["revenue_ltm"]),
        "pe_ltm": _ratio(df["market_cap"], df["net_income_ltm"]),
        "source": SOURCE_LABEL,
    })
    return out.dropna(subset=["enterprise_value"])


def build_estimates(fin: pd.DataFrame) -> pd.DataFrame:
    fin = fin.sort_values(["company_id", "period"])
    grouped = fin.groupby("company_id", group_keys=False)
    fin = fin.assign(
        revenue_ltm=grouped["revenue"].transform(lambda s: s.rolling(4, min_periods=4).sum()),
        ebitda_ltm=grouped["ebitda"].transform(lambda s: s.rolling(4, min_periods=4).sum()),
        net_income_ltm=grouped["net_income"].transform(lambda s: s.rolling(4, min_periods=4).sum()),
    )
    rows = []
    for company_id, g in fin.groupby("company_id"):
        seed = int.from_bytes(hashlib.sha256(str(company_id).encode("utf-8")).digest()[:4], "big")
        rng = np.random.default_rng(seed)
        for _, r in g.iterrows():
            beat = rng.normal(0.0, 0.02)
            growth = rng.normal(0.06, 0.02)
            drift_30 = rng.normal(0.0, 0.01)
            drift_90 = rng.normal(0.0, 0.02)
            rev_ntm = r["revenue_ltm"] * (1 + growth) if pd.notna(r["revenue_ltm"]) else np.nan
            eps_proxy = r["net_income_ltm"] if pd.notna(r["net_income_ltm"]) else np.nan
            rows.append({
                "company_id": company_id,
                "period": r["period"].date().isoformat(),
                "revenue_consensus": r["revenue"] * (1 - beat),
                "ebitda_consensus": r["ebitda"] * (1 - beat * 1.4) if pd.notna(r["ebitda"]) else np.nan,
                "eps_consensus": np.nan,
                "guidance_low": np.nan,
                "guidance_high": np.nan,
                "revenue_est_ntm": rev_ntm,
                "ebitda_est_ntm": r["ebitda_ltm"] * (1 + growth) if pd.notna(r["ebitda_ltm"]) else np.nan,
                "eps_est_ntm": eps_proxy * (1 + growth) if pd.notna(eps_proxy) else np.nan,
                "num_analysts": int(rng.integers(4, 14)),
                "revenue_est_ntm_30d_ago": rev_ntm * (1 - drift_30) if pd.notna(rev_ntm) else np.nan,
                "eps_est_ntm_30d_ago": eps_proxy * (1 + growth) * (1 - drift_30) if pd.notna(eps_proxy) else np.nan,
                "revenue_est_ntm_90d_ago": rev_ntm * (1 - drift_90) if pd.notna(rev_ntm) else np.nan,
                "eps_est_ntm_90d_ago": eps_proxy * (1 + growth) * (1 - drift_90) if pd.notna(eps_proxy) else np.nan,
                "next_earnings_date": "",
                "source": SOURCE_LABEL,
            })
    return pd.DataFrame(rows)


def main() -> None:
    fin, mkt = _load()
    valuation = build_valuation_history(fin, mkt)
    estimates = build_estimates(fin)
    write_csv(valuation, SAMPLE_PUBLIC_DIR / "valuation_history.csv")
    write_csv(estimates, SAMPLE_PUBLIC_DIR / "estimates.csv")
    print(f"valuation_history rows: {len(valuation)}  |  estimates rows: {len(estimates)}")
    print(f"written to {SAMPLE_PUBLIC_DIR}")


if __name__ == "__main__":
    main()
