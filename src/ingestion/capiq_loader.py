from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ingestion.schema import (
    COMPANY_COLUMNS,
    COMPANY_OPTIONAL_COLUMNS,
    ESTIMATE_COLUMNS,
    ESTIMATE_OPTIONAL_COLUMNS,
    FINANCIAL_COLUMNS,
    FINANCIAL_OPTIONAL_COLUMNS,
    MARKET_COLUMNS,
    MARKET_OPTIONAL_COLUMNS,
    SOURCE_LOG_COLUMNS,
    VALUATION_HISTORY_COLUMNS,
)
from src.utils import read_table

# table key -> (file stem, required columns, optional columns, required table?)
TABLES = {
    "companies": ("companies", COMPANY_COLUMNS, COMPANY_OPTIONAL_COLUMNS, True),
    "financials": ("financials_quarterly", FINANCIAL_COLUMNS, FINANCIAL_OPTIONAL_COLUMNS, True),
    "market_data": ("market_data", MARKET_COLUMNS, MARKET_OPTIONAL_COLUMNS, True),
    "estimates": ("estimates", ESTIMATE_COLUMNS, ESTIMATE_OPTIONAL_COLUMNS, False),
    "valuation_history": ("valuation_history", VALUATION_HISTORY_COLUMNS, [], False),
    "source_log": ("source_log", SOURCE_LOG_COLUMNS, [], False),
}


def _find_table(input_dir: Path, stem: str) -> Path | None:
    for suffix in (".csv", ".xlsx", ".xls"):
        candidate = input_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _load_one(
    input_dir: Path,
    stem: str,
    columns: list[str],
    optional: list[str],
    required: bool,
) -> pd.DataFrame:
    path = _find_table(input_dir, stem)
    if path is None:
        if required:
            raise FileNotFoundError(
                f"Missing required Capital IQ export '{stem}.csv' or '{stem}.xlsx' in {input_dir}."
            )
        return _empty(columns)

    df = read_table(path)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")
    keep = columns + [c for c in optional if c in df.columns]
    return df[keep].copy()


def load_capiq_exports(input_dir: str | Path) -> dict[str, pd.DataFrame]:
    directory = Path(input_dir)
    if not directory.exists():
        raise FileNotFoundError(
            f"Capital IQ input folder does not exist: {directory}. "
            "Create data_private/capiq_exports and add files matching data/templates."
        )

    loaded: dict[str, pd.DataFrame] = {}
    for key, (stem, columns, optional, required) in TABLES.items():
        loaded[key] = _load_one(directory, stem, columns, optional, required)

    # Optional beta side-table (export_capiq_beta.ps1) joins onto market data so
    # the WACC build sees a real levered beta instead of the flagged default.
    beta_path = _find_table(directory, "company_beta")
    if beta_path is not None and not loaded["market_data"].empty:
        betas = read_table(beta_path)
        if {"company_id", "beta_2y"} <= set(betas.columns):
            keep = ["company_id", "beta_2y"] + (["beta_5y"] if "beta_5y" in betas.columns else [])
            market = loaded["market_data"]
            # Drop empty optional beta columns so the side-table join wins.
            for col in ("beta_2y", "beta_5y"):
                if col in market.columns and market[col].isna().all():
                    market = market.drop(columns=col)
            loaded["market_data"] = market.merge(
                betas[keep].drop_duplicates("company_id"), on="company_id", how="left")

    if loaded["source_log"].empty:
        loaded["source_log"] = pd.DataFrame(
            [
                {
                    "table_name": "Capital IQ exports",
                    "source_name": "Capital IQ",
                    "source_url": "local private export",
                    "retrieved_at": pd.Timestamp.today().date().isoformat(),
                    "notes": "Private local import. Raw exports are excluded from Git.",
                }
            ]
        )
    return loaded
