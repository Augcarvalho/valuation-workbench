"""Private analyst overrides for the valuation assumptions workbench.

The Streamlit editor writes only company-specific decisions. Automatic values
remain in the model engine and are not duplicated in the YAML unless the
analyst changes them. Every overwrite is archived locally before replacement;
none of these files belongs in Git.
"""

from __future__ import annotations

import csv
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.modeling.valuation_assumptions import VALID_STATUSES, assumptions_filename


class AssumptionValidationError(ValueError):
    """Raised when an editor payload is not financially or structurally valid."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def assumption_path(company_id: str, assumptions_dir: Path) -> Path:
    return Path(assumptions_dir) / assumptions_filename(company_id)


def read_assumption_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {}
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: Any, label: str, errors: list[str]) -> float | None:
    if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric or auto")
        return None


def _check_range(
    value: Any,
    low: float,
    high: float,
    label: str,
    errors: list[str],
) -> None:
    if isinstance(value, dict):
        for endpoint in ("start", "end"):
            if endpoint in value:
                _check_range(value[endpoint], low, high, f"{label} {endpoint}", errors)
        return
    if isinstance(value, list):
        for index, item in enumerate(value, start=1):
            _check_range(item, low, high, f"{label} year {index}", errors)
        return
    number = _number(value, label, errors)
    if number is not None and not low <= number <= high:
        errors.append(f"{label} must be between {low:.1%} and {high:.1%}")


def validate_assumption_payload(payload: dict[str, Any]) -> list[str]:
    """Return all validation errors rather than failing on the first field."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Assumptions payload must be a mapping"]

    status = str(payload.get("status", "draft")).strip().lower()
    if status not in VALID_STATUSES:
        errors.append(f"Status must be one of: {', '.join(VALID_STATUSES)}")

    try:
        horizon = int(payload.get("horizon_years", 5))
        if not 3 <= horizon <= 15:
            errors.append("Detailed forecast horizon must be between 3 and 15 years")
    except (TypeError, ValueError):
        errors.append("Detailed forecast horizon must be an integer")

    transition = payload.get("transition_years", "auto")
    if not (isinstance(transition, str) and transition.strip().lower() == "auto"):
        try:
            transition_years = int(transition)
            if not 0 <= transition_years <= 10:
                errors.append("Transition period must be between 0 and 10 years")
        except (TypeError, ValueError):
            errors.append("Transition period must be auto or an integer")

    bounds = {
        "revenue_growth": (-0.50, 1.00, "Revenue growth"),
        "ebitda_margin": (-0.50, 1.00, "EBITDA margin"),
        "d_and_a_pct_revenue": (0.00, 0.40, "D&A / revenue"),
        "capex_pct_revenue": (0.00, 0.75, "Capex / revenue"),
        "tax_rate": (0.00, 0.60, "Tax rate"),
        "dso": (0.00, 730.00, "DSO"),
        "dih": (0.00, 730.00, "DIH"),
        "dpo": (0.00, 730.00, "DPO"),
        "nwc_pct_revenue": (-1.00, 1.00, "NWC / revenue"),
    }
    scenarios = payload.get("scenarios") or {}
    if not isinstance(scenarios, dict):
        errors.append("Scenarios must be a mapping")
        scenarios = {}
    for scenario_name, scenario in scenarios.items():
        if scenario_name not in {"bear", "base", "bull"}:
            errors.append(f"Unknown scenario: {scenario_name}")
            continue
        if not isinstance(scenario, dict):
            errors.append(f"{scenario_name.title()} scenario must be a mapping")
            continue
        for key, (low, high, label) in bounds.items():
            if key in scenario:
                _check_range(
                    scenario[key], low, high,
                    f"{scenario_name.title()} {label}", errors,
                )

    wacc = payload.get("wacc") or {}
    if not isinstance(wacc, dict):
        errors.append("WACC assumptions must be a mapping")
        wacc = {}
    for key, low, high, label in (
        ("beta", 0.10, 5.00, "Beta"),
        ("pretax_cost_of_debt", 0.00, 0.50, "Pre-tax cost of debt"),
        ("wacc_override", 0.01, 0.50, "WACC override"),
    ):
        if key in wacc:
            _check_range(wacc[key], low, high, label, errors)

    terminal = payload.get("terminal") or {}
    if not isinstance(terminal, dict):
        errors.append("Terminal assumptions must be a mapping")
        terminal = {}
    for key, low, high, label in (
        ("exit_multiple", 0.50, 100.00, "Exit multiple"),
        ("perpetuity_growth", -0.05, 0.15, "Perpetuity growth"),
        ("roic", 0.01, 1.00, "Terminal ROIC"),
        ("wacc", 0.01, 0.50, "Terminal WACC"),
    ):
        if key in terminal:
            _check_range(terminal[key], low, high, label, errors)

    growth = _number(terminal.get("perpetuity_growth"), "Perpetuity growth", [])
    terminal_wacc = _number(terminal.get("wacc"), "Terminal WACC", [])
    terminal_roic = _number(terminal.get("roic"), "Terminal ROIC", [])
    if growth is not None and terminal_wacc is not None and growth >= terminal_wacc:
        errors.append("Perpetuity growth must be below terminal WACC")
    if growth is not None and terminal_roic is not None and terminal_roic <= growth:
        errors.append("Terminal ROIC must exceed perpetuity growth")

    operating = payload.get("operating_drivers") or {}
    if not isinstance(operating, dict):
        errors.append("Operating drivers must be a mapping")
        operating = {}
    driver_scenarios = operating.get("scenarios") or {}
    if not isinstance(driver_scenarios, dict):
        errors.append("Operating-driver scenarios must be a mapping")
        driver_scenarios = {}
    for scenario_name, scenario in driver_scenarios.items():
        if scenario_name not in {"bear", "base", "bull"} or not isinstance(scenario, dict):
            errors.append(f"Invalid operating-driver scenario: {scenario_name}")
            continue
        if "net_store_adds" in scenario:
            _check_range(
                scenario["net_store_adds"], -100.0, 1000.0,
                f"{scenario_name.title()} net store additions", errors,
            )
        for key, label in (
            ("store_productivity_growth", "store productivity growth"),
            ("ecommerce_growth", "e-commerce growth"),
            ("other_growth", "other-channel growth"),
        ):
            if key in scenario:
                _check_range(
                    scenario[key], -0.75, 2.00,
                    f"{scenario_name.title()} {label}", errors,
                )

    return errors


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix: value}
    flat: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        flat.update(_flatten(item, path))
    return flat


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    old, new = _flatten(before), _flatten(after)
    return sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))


def _timestamp(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _archive(path: Path, now: datetime) -> Path | None:
    if not path.exists():
        return None
    history = path.parent / "history" / path.stem
    history.mkdir(parents=True, exist_ok=True)
    archived = history / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}.yaml"
    shutil.copy2(path, archived)
    return archived


def _append_audit(
    assumptions_dir: Path,
    company_id: str,
    action: str,
    changed: list[str],
    status: str,
    now: datetime,
) -> None:
    path = assumptions_dir / "assumption_audit.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "timestamp_utc", "company_id", "action", "status",
            "change_count", "changed_fields",
        ])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp_utc": now.isoformat(),
            "company_id": company_id,
            "action": action,
            "status": status,
            "change_count": len(changed),
            "changed_fields": " | ".join(changed),
        })


def save_assumption_payload(
    company_id: str,
    assumptions_dir: Path,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> Path:
    errors = validate_assumption_payload(payload)
    if errors:
        raise AssumptionValidationError(errors)

    assumptions_dir = Path(assumptions_dir)
    assumptions_dir.mkdir(parents=True, exist_ok=True)
    path = assumption_path(company_id, assumptions_dir)
    before = read_assumption_payload(path)
    stamp = _timestamp(now)
    _archive(path, stamp)

    rendered = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
    )
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    os.replace(temp, path)

    changed = _changed_fields(before, payload)
    _append_audit(
        assumptions_dir, company_id,
        "created" if not before else "updated",
        changed, str(payload.get("status", "draft")), stamp,
    )
    return path


def reset_assumption_payload(
    company_id: str,
    assumptions_dir: Path,
    *,
    now: datetime | None = None,
) -> bool:
    assumptions_dir = Path(assumptions_dir)
    path = assumption_path(company_id, assumptions_dir)
    if not path.exists():
        return False
    before = read_assumption_payload(path)
    stamp = _timestamp(now)
    _archive(path, stamp)
    path.unlink()
    _append_audit(
        assumptions_dir, company_id, "reset_to_automatic",
        sorted(_flatten(before)), "auto", stamp,
    )
    return True
