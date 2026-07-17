"""Watchlist data store: the processed dataset plus all side tables.

The main monitoring dataset stays a single processed CSV for compatibility
with the existing app and tests. Everything that arrived with V2 — valuation
history, consensus estimates, analyst theses, the CapIQ refresh log — is a
*side table* resolved per mode (public demo vs Capital IQ private) with
graceful empty fallbacks, so the public demo runs with zero private data and
the private mode degrades cleanly until a live CapIQ refresh populates a
given table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import (
    DEFAULT_PROCESSED_DATASET,
    DEFAULT_SOURCE_LOG,
    DEMO_ASSUMPTIONS_DIR,
    DEMO_ESTIMATES,
    DEMO_THESES_DIR,
    DEMO_VALUATION_HISTORY,
    PRIVATE_ASSUMPTIONS_DIR,
    PRIVATE_ESTIMATES,
    PRIVATE_PROCESSED_DATASET,
    PRIVATE_SOURCE_LOG,
    PRIVATE_REFRESH_LOG,
    PRIVATE_THESES_DIR,
    PRIVATE_VALUATION_HISTORY,
)
from src.ingestion.schema import VALUATION_HISTORY_COLUMNS


@dataclass
class WatchlistStore:
    mode: str                       # "demo" | "private"
    dataset_path: Path
    valuation_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    estimates: pd.DataFrame = field(default_factory=pd.DataFrame)
    refresh_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    theses_dir: Path | None = None
    assumptions_dir: Path | None = None

    @property
    def has_valuation_history(self) -> bool:
        return not self.valuation_history.empty

    @property
    def has_estimates(self) -> bool:
        if self.estimates.empty:
            return False
        value_cols = [c for c in self.estimates.columns if c not in {"company_id", "period", "source", "next_earnings_date"}]
        return bool(value_cols) and self.estimates[value_cols].notna().any().any()


def _read_csv(path: Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for col in parse_dates or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_valuation_history(demo: bool) -> pd.DataFrame:
    path = DEMO_VALUATION_HISTORY if demo else PRIVATE_VALUATION_HISTORY
    df = _read_csv(path, parse_dates=["date"])
    if df.empty and not demo:
        # Private mode without a populated table: fall back to the demo file
        # only if it matches the private universe (it will not), so keep empty.
        return pd.DataFrame(columns=VALUATION_HISTORY_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=VALUATION_HISTORY_COLUMNS)
    return df.sort_values(["company_id", "date"])


def load_estimates(demo: bool) -> pd.DataFrame:
    path = DEMO_ESTIMATES if demo else PRIVATE_ESTIMATES
    df = _read_csv(path, parse_dates=["period"])
    return df


def load_refresh_log(demo: bool) -> pd.DataFrame:
    if demo:
        return pd.DataFrame()
    return _read_csv(PRIVATE_REFRESH_LOG, parse_dates=["refreshed_at"])


def load_source_log(demo: bool) -> pd.DataFrame:
    path = DEFAULT_SOURCE_LOG if demo else PRIVATE_SOURCE_LOG
    return _read_csv(path, parse_dates=["retrieved_at"])


def theses_dir(demo: bool) -> Path:
    return DEMO_THESES_DIR if demo else PRIVATE_THESES_DIR


def assumptions_dir(demo: bool) -> Path:
    return DEMO_ASSUMPTIONS_DIR if demo else PRIVATE_ASSUMPTIONS_DIR


def load_store(demo: bool) -> WatchlistStore:
    dataset_path = DEFAULT_PROCESSED_DATASET if (demo or not PRIVATE_PROCESSED_DATASET.exists()) else PRIVATE_PROCESSED_DATASET
    return WatchlistStore(
        mode="demo" if demo else "private",
        dataset_path=dataset_path,
        valuation_history=load_valuation_history(demo),
        estimates=load_estimates(demo),
        refresh_log=load_refresh_log(demo),
        source_log=load_source_log(demo),
        theses_dir=theses_dir(demo),
        assumptions_dir=assumptions_dir(demo),
    )
