"""Private universe management: add companies to the CapIQ watchlist.

The export script reads ``data_private/universe.csv`` when it exists (columns
``id,ticker,sector,currency`` where ``sector`` holds the thesis theme). This
module owns that file:

- ``ensure_universe()`` bootstraps it from the last exported companies.csv the
  first time, so the editable private universe replaces the script's
  hard-coded default from then on.
- ``add_company()`` appends a new name with duplicate protection, records the
  peer group / business model in a PRIVATE classification overlay (never the
  committed reference CSV), and appends an audit log entry.

Everything here writes only inside ``data_private/`` (gitignored).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import json
import pandas as pd

from src.config import PRIVATE_CAPIQ_DIR, PRIVATE_DATA_DIR

UNIVERSE_PATH = PRIVATE_DATA_DIR / "universe.csv"
BOOTSTRAP_SOURCE = PRIVATE_CAPIQ_DIR / "companies.csv"
PRIVATE_CLASSIFICATION_PATH = PRIVATE_DATA_DIR / "company_classification_private.csv"
ADD_LOG_PATH = PRIVATE_CAPIQ_DIR / "add_company_log.csv"

UNIVERSE_COLUMNS = ["id", "ticker", "sector", "currency"]


@dataclass
class LookupResult:
    company_id: str
    resolved: bool
    company_name: str = ""
    exchange: str = ""
    industry: str = ""
    currency: str = ""
    error: str = ""


def parse_lookup_result(payload: str | dict) -> LookupResult:
    """Parse the JSON written by scripts/lookup_capiq_company.ps1.

    Invalid identifiers come back with resolved=false and a readable error.
    """
    try:
        data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        return LookupResult(company_id="", resolved=False, error=f"unreadable lookup output: {exc}")

    name = str(data.get("company_name") or "").strip()
    resolved = bool(data.get("resolved")) and bool(name)
    return LookupResult(
        company_id=str(data.get("company_id") or "").strip(),
        resolved=resolved,
        company_name=name,
        exchange=str(data.get("exchange") or "").strip(),
        industry=str(data.get("industry") or "").strip(),
        currency=str(data.get("currency") or "").strip(),
        error=str(data.get("error") or ("identifier did not resolve in Capital IQ" if not resolved else "")),
    )


def ensure_universe(
    universe_path: Path = UNIVERSE_PATH,
    bootstrap_source: Path = BOOTSTRAP_SOURCE,
) -> pd.DataFrame:
    """Load the private universe, bootstrapping it from the last export once."""
    if universe_path.exists():
        return pd.read_csv(universe_path)[UNIVERSE_COLUMNS]

    if bootstrap_source.exists():
        companies = pd.read_csv(bootstrap_source)
        universe = pd.DataFrame({
            "id": companies["company_id"],
            "ticker": companies["ticker"],
            "sector": companies["sector"],
            "currency": companies["currency"],
        })
    else:
        universe = pd.DataFrame(columns=UNIVERSE_COLUMNS)

    universe_path.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(universe_path, index=False)
    return universe


def company_exists(universe: pd.DataFrame, company_id: str, ticker: str | None = None) -> bool:
    if universe.empty:
        return False
    cid = company_id.strip().upper()
    if (universe["id"].astype(str).str.upper() == cid).any():
        return True
    # Tickers are not globally unique across exchanges. The Capital IQ
    # exchange-qualified identifier is the canonical duplicate key.
    return False


def _append_private_classification(company_id: str, peer_group: str, business_model: str,
                                   path: Path = PRIVATE_CLASSIFICATION_PATH) -> None:
    row = pd.DataFrame([{
        "company_id": company_id,
        "peer_group": peer_group,
        "business_model": business_model,
    }])
    if path.exists():
        existing = pd.read_csv(path)
        existing = existing[existing["company_id"] != company_id]
        combined = pd.concat([existing, row], ignore_index=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = row
    combined.to_csv(path, index=False)


def _append_audit_log(entry: dict, path: Path = ADD_LOG_PATH) -> None:
    row = pd.DataFrame([entry])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        row.to_csv(path, mode="a", header=False, index=False)
    else:
        row.to_csv(path, index=False)


def add_company(
    company_id: str,
    ticker: str,
    theme: str,
    currency: str,
    peer_group: str,
    business_model: str,
    company_name: str = "",
    universe_path: Path = UNIVERSE_PATH,
    bootstrap_source: Path = BOOTSTRAP_SOURCE,
    classification_path: Path = PRIVATE_CLASSIFICATION_PATH,
    log_path: Path = ADD_LOG_PATH,
) -> pd.DataFrame:
    """Add a company to the private universe. Raises ValueError on duplicates
    or missing fields. Returns the updated universe frame."""
    company_id = company_id.strip()
    ticker = ticker.strip()
    if not company_id or ":" not in company_id:
        raise ValueError(f"company_id must look like 'EXCHANGE:TICKER', got {company_id!r}")
    if not all([ticker, theme.strip(), currency.strip(), peer_group.strip(), business_model.strip()]):
        raise ValueError("ticker, theme, currency, peer_group, and business_model are all required")

    universe = ensure_universe(universe_path, bootstrap_source)
    if company_exists(universe, company_id, ticker):
        raise ValueError(f"{company_id} is already in the universe")

    new_row = pd.DataFrame([{
        "id": company_id, "ticker": ticker, "sector": theme.strip(), "currency": currency.strip().upper(),
    }])
    updated = pd.concat([universe, new_row], ignore_index=True)
    updated.to_csv(universe_path, index=False)

    _append_private_classification(company_id, peer_group.strip(), business_model.strip().lower(),
                                   classification_path)
    _append_audit_log({
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "company_id": company_id,
        "ticker": ticker,
        "company_name": company_name,
        "theme": theme.strip(),
        "peer_group": peer_group.strip(),
        "business_model": business_model.strip().lower(),
        "currency": currency.strip().upper(),
    }, log_path)
    return updated
