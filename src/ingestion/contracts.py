"""Dataset contracts and build provenance for every ingestion mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pandas as pd


class DataContractError(ValueError):
    """Raised before an invalid dataset can replace the current good build."""


@dataclass
class ContractResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def require_valid(self) -> None:
        if not self.valid:
            raise DataContractError("; ".join(self.errors))


def _required_columns(df: pd.DataFrame, table: str, columns: set[str], errors: list[str]) -> None:
    missing = columns - set(df.columns)
    if missing:
        errors.append(f"{table} missing required columns: {sorted(missing)}")


def validate_raw_inputs(inputs: dict[str, pd.DataFrame]) -> ContractResult:
    errors: list[str] = []
    warnings: list[str] = []
    companies = inputs.get("companies", pd.DataFrame())
    financials = inputs.get("financials", pd.DataFrame())
    market = inputs.get("market_data", pd.DataFrame())
    _required_columns(companies, "companies", {"company_id", "ticker", "currency"}, errors)
    _required_columns(financials, "financials", {"company_id", "period", "revenue", "ebitda"}, errors)
    _required_columns(market, "market_data", {"company_id", "period"}, errors)
    if errors:
        return ContractResult(False, errors, warnings)

    if companies["company_id"].isna().any() or companies["company_id"].astype(str).str.strip().eq("").any():
        errors.append("companies contains blank company_id")
    if companies.duplicated("company_id").any():
        errors.append("companies contains duplicate company_id values")
    parsed = pd.to_datetime(financials["period"], errors="coerce")
    if parsed.isna().any():
        errors.append("financials contains invalid period values")
    exact_keys = pd.DataFrame({
        "company_id": financials["company_id"].astype(str),
        "period": parsed,
        "period_type": financials.get("period_type", "quarterly"),
    })
    if exact_keys.duplicated(["company_id", "period", "period_type"]).any():
        errors.append("financials contains duplicate canonical fiscal observations")
    unknown = set(financials["company_id"].dropna().astype(str)) - set(companies["company_id"].astype(str))
    if unknown:
        errors.append(f"financials references {len(unknown)} unknown company_id value(s)")
    if inputs.get("source_log", pd.DataFrame()).empty:
        warnings.append("source log is empty; generated local provenance will be used")
    return ContractResult(not errors, errors, warnings)


def validate_processed_dataset(df: pd.DataFrame) -> ContractResult:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "company_id", "period", "fiscal_period_end", "fiscal_period_id",
        "period_type", "revenue", "ebitda", "ttm_complete",
    }
    _required_columns(df, "processed dataset", required, errors)
    if errors:
        return ContractResult(False, errors, warnings)
    key = ["company_id", "fiscal_period_end", "period_type"]
    if df.duplicated(key).any():
        errors.append("processed dataset contains duplicate canonical fiscal observations")
    if df["company_id"].isna().any() or df["fiscal_period_end"].isna().any():
        errors.append("processed dataset contains null canonical keys")
    if not df["ttm_complete"].any():
        warnings.append("no company has a complete trailing-twelve-month window")
    return ContractResult(not errors, errors, warnings)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    source: str,
    dataset: pd.DataFrame,
    inputs: dict[str, pd.DataFrame],
    warnings: list[str],
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    periods = pd.to_datetime(dataset["fiscal_period_end"], errors="coerce")
    identity = "|".join(sorted(dataset["fiscal_period_id"].astype(str)))
    build_id = sha256(f"v2|{source}|{identity}".encode()).hexdigest()[:16]
    return {
        "schema_version": 2,
        "build_id": build_id,
        "source": source,
        "status": "success",
        "started_at": now,
        "completed_at": now,
        "companies": int(dataset["company_id"].nunique()),
        "processed_rows": int(len(dataset)),
        "financial_rows": int(len(inputs.get("financials", pd.DataFrame()))),
        "market_rows": int(len(inputs.get("market_data", pd.DataFrame()))),
        "estimate_rows": int(len(inputs.get("estimates", pd.DataFrame()))),
        "valuation_rows": int(len(inputs.get("valuation_history", pd.DataFrame()))),
        "min_fiscal_period": periods.min(),
        "max_fiscal_period": periods.max(),
        "warnings": warnings,
    }
