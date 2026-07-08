from __future__ import annotations

from pathlib import Path

import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path}")


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)
    return path


def coerce_period(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.to_period("Q").dt.to_timestamp("Q")


def clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def fmt_money(value: float | int | None, currency: str = "BRL", suffix: str = "m") -> str:
    if pd.isna(value):
        return "n/a"
    symbols = {"BRL": "R$", "USD": "US$"}
    prefix = symbols.get(str(currency).upper(), str(currency).upper())
    return f"{prefix} {value:,.1f}{suffix}"


def fmt_brl(value: float | int | None, suffix: str = "m") -> str:
    return fmt_money(value, "BRL", suffix)


def fmt_pct(value: float | int | None) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.1%}"


def fmt_multiple(value: float | int | None) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.1f}x"


def fmt_signed_pct(value: float | int | None, digits: int = 1) -> str:
    """Percentage with an explicit + / - sign, e.g. '+12.4%'."""
    if pd.isna(value):
        return "n/a"
    return f"{value:+.{digits}%}"


def fmt_bps(value: float | int | None) -> str:
    """A change expressed in basis points from a decimal margin delta."""
    if pd.isna(value):
        return "n/a"
    return f"{value * 10000:+,.0f} bps"


def fmt_ordinal(value: float | int | None) -> str:
    """Render a 0-1 percentile as an ordinal rank, e.g. 0.83 -> '83rd'."""
    if pd.isna(value):
        return "n/a"
    pct = int(round(float(value) * 100))
    pct = min(max(pct, 1), 99)
    if 11 <= (pct % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(pct % 10, "th")
    return f"{pct}{suffix}"
