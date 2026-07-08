from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import SAMPLE_PUBLIC_DIR
from src.ingestion.schema import (
    COMPANY_COLUMNS,
    ESTIMATE_COLUMNS,
    FINANCIAL_COLUMNS,
    MARKET_COLUMNS,
    SOURCE_LOG_COLUMNS,
)
from src.utils import read_table


def _load_csv(directory: Path, name: str, required_columns: list[str]) -> pd.DataFrame:
    path = directory / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing public demo file: {path}. Run scripts/generate_public_demo_data.py."
        )
    df = read_table(path)
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    return df


def load_public_demo(directory: Path = SAMPLE_PUBLIC_DIR) -> dict[str, pd.DataFrame]:
    return {
        "companies": _load_csv(directory, "companies", COMPANY_COLUMNS),
        "financials": _load_csv(directory, "financials_quarterly", FINANCIAL_COLUMNS),
        "market_data": _load_csv(directory, "market_data", MARKET_COLUMNS),
        "estimates": _load_csv(directory, "estimates", ESTIMATE_COLUMNS),
        "source_log": _load_csv(directory, "source_log", SOURCE_LOG_COLUMNS),
    }

