from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import SAMPLE_PUBLIC_DIR


def load_b3_demo_universe(path: Path | None = None) -> pd.DataFrame:
    """Load the B3 company universe used by the public demo."""

    companies_path = path or SAMPLE_PUBLIC_DIR / "companies.csv"
    df = pd.read_csv(companies_path)
    return df[["company_id", "ticker", "company_name", "sector", "exchange", "currency"]]

