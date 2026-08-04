"""Create the private Capital IQ Formula Builder queue for operating KPIs.

The queue deliberately does not guess issuer-specific CIQ mnemonics. Existing
reviewed mnemonics are retained, while every missing primary driver is written
as VERIFY_IN_FORMULA_BUILDER. The resulting file stays under data_private/.
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.operating_drivers import COMPANY_PROFILE, PROFILES


OUTPUT = PROJECT_ROOT / "data_private" / "operating_kpi_config.csv"
FIELDS = [
    "company_id", "period", "fiscal_period", "metric_id", "metric_label",
    "capiq_mnemonic", "period_code", "unit", "scope", "period_type",
    "data_type", "definition",
]


def _label(metric_id: str) -> str:
    return metric_id.replace("_", " ").title()


def build_queue(output: Path = OUTPUT) -> list[dict[str, str]]:
    existing: dict[tuple[str, str], dict[str, str]] = {}
    if output.exists():
        with output.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                existing[(row.get("company_id", ""), row.get("metric_id", ""))] = row

    rows: list[dict[str, str]] = []
    for company_id, profile_id in COMPANY_PROFILE.items():
        profile = PROFILES[profile_id]
        for metric_id in profile.primary_metrics + profile.supporting_metrics:
            prior = existing.get((company_id, metric_id), {})
            rows.append({
                "company_id": company_id,
                "period": prior.get("period", ""),
                "fiscal_period": prior.get("fiscal_period", ""),
                "metric_id": metric_id,
                "metric_label": prior.get("metric_label") or _label(metric_id),
                "capiq_mnemonic": prior.get("capiq_mnemonic") or "VERIFY_IN_FORMULA_BUILDER",
                "period_code": prior.get("period_code") or "IQ_LATEST",
                "unit": prior.get("unit", ""),
                "scope": prior.get("scope") or "Consolidated",
                "period_type": prior.get("period_type") or "point_in_time",
                "data_type": prior.get("data_type") or "actual",
                "definition": prior.get("definition") or profile.equation,
            })

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    queue = build_queue()
    verified = sum(row["capiq_mnemonic"] != "VERIFY_IN_FORMULA_BUILDER" for row in queue)
    print(f"{len(queue)} operating-KPI requests -> {OUTPUT}")
    print(f"Verified Capital IQ mnemonics: {verified}; pending Formula Builder review: {len(queue) - verified}")
