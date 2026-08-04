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

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import (
    DEFAULT_PROCESSED_DATASET,
    DEFAULT_SOURCE_LOG,
    DEMO_ASSUMPTIONS_DIR,
    DEMO_ESTIMATES,
    DEMO_COMPANY_SEGMENTS,
    DEMO_OPERATING_KPIS,
    DEMO_THESES_DIR,
    DEMO_VALUATION_HISTORY,
    PRIVATE_ASSUMPTIONS_DIR,
    PRIVATE_ESTIMATES,
    PRIVATE_COMPANY_SEGMENTS,
    PRIVATE_OPERATING_KPIS,
    PRIVATE_MONITORING_DIR,
    PRIVATE_PROCESSED_DATASET,
    PRIVATE_SOURCE_LOG,
    PRIVATE_REFRESH_LOG,
    PRIVATE_THESES_DIR,
    PRIVATE_VALUATION_HISTORY,
)
from src.ingestion.schema import VALUATION_HISTORY_COLUMNS
from src.ingestion.private_monitoring import load_private_monitoring


@dataclass
class WatchlistStore:
    mode: str                       # "demo" | "private"
    dataset_path: Path
    valuation_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    operating_kpis: pd.DataFrame = field(default_factory=pd.DataFrame)
    company_segments: pd.DataFrame = field(default_factory=pd.DataFrame)
    estimates: pd.DataFrame = field(default_factory=pd.DataFrame)
    refresh_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    theses_dir: Path | None = None
    assumptions_dir: Path | None = None
    private_monitoring: dict[str, pd.DataFrame] = field(default_factory=dict)
    build_manifest: dict = field(default_factory=dict)

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


def load_operating_kpis(demo: bool) -> pd.DataFrame:
    path = DEMO_OPERATING_KPIS if demo else PRIVATE_OPERATING_KPIS
    return _read_csv(path, parse_dates=["period", "retrieved_at"])


def load_company_segments(demo: bool) -> pd.DataFrame:
    path = DEMO_COMPANY_SEGMENTS if demo else PRIVATE_COMPANY_SEGMENTS
    return _read_csv(path)


def load_source_log(demo: bool) -> pd.DataFrame:
    path = DEFAULT_SOURCE_LOG if demo else PRIVATE_SOURCE_LOG
    return _read_csv(path, parse_dates=["retrieved_at"])


def theses_dir(demo: bool) -> Path:
    return DEMO_THESES_DIR if demo else PRIVATE_THESES_DIR


def assumptions_dir(demo: bool) -> Path:
    return DEMO_ASSUMPTIONS_DIR if demo else PRIVATE_ASSUMPTIONS_DIR


def load_store(demo: bool) -> WatchlistStore:
    dataset_path = DEFAULT_PROCESSED_DATASET if (demo or not PRIVATE_PROCESSED_DATASET.exists()) else PRIVATE_PROCESSED_DATASET
    manifest_path = dataset_path.parent / "build_manifest.json"
    try:
        build_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        build_manifest = {}
    return WatchlistStore(
        mode="demo" if demo else "private",
        dataset_path=dataset_path,
        valuation_history=load_valuation_history(demo),
        operating_kpis=load_operating_kpis(demo),
        company_segments=load_company_segments(demo),
        estimates=load_estimates(demo),
        refresh_log=load_refresh_log(demo),
        source_log=load_source_log(demo),
        theses_dir=theses_dir(demo),
        assumptions_dir=assumptions_dir(demo),
        private_monitoring=(
            load_private_monitoring(None if demo else PRIVATE_MONITORING_DIR)
        ),
        build_manifest=build_manifest,
    )
