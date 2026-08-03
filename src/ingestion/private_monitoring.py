"""Optional internal portfolio-monitoring tables; always local and gitignored."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PRIVATE_MONITORING_SCHEMAS = {
    "monthly_budget_actual": [
        "company_id", "period", "metric", "actual", "budget", "currency", "source",
    ],
    "covenants": [
        "company_id", "period", "covenant", "actual", "limit", "test_direction",
        "headroom", "source",
    ],
    "value_creation": [
        "company_id", "initiative_id", "initiative", "owner", "status", "target_date",
        "target_value", "realized_value", "source",
    ],
    "ownership": [
        "company_id", "holder", "security", "shares", "ownership_pct", "as_of", "source",
    ],
}


def load_private_monitoring(root: Path | None) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for name, columns in PRIVATE_MONITORING_SCHEMAS.items():
        path = Path(root) / f"{name}.csv" if root is not None else None
        if path is None or not path.exists():
            tables[name] = pd.DataFrame(columns=columns)
            continue
        frame = pd.read_csv(path)
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
        tables[name] = frame[columns].copy()
    return tables
