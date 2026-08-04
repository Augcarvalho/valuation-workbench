"""Immutable local manifests for reviewed underwriting cases."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils import ensure_dir, write_json_atomic


def case_manifest(case) -> dict:
    from src.modeling.operating_drivers import operating_driver_payload

    scenarios = {}
    for name, result in case.scenarios.items():
        sponsor = case.lbo_scenarios.get(name)
        scenarios[name] = {
            "dcf_enterprise_value": result.enterprise_value,
            "dcf_equity_value": result.implied_equity,
            "target_price": result.target_price,
            "upside": result.upside,
            "wacc": result.wacc,
            "exit_multiple": result.exit_multiple,
            "terminal_growth": result.perpetuity_growth,
            "sponsor_moic": sponsor.moic if sponsor else None,
            "sponsor_irr": sponsor.irr if sponsor else None,
            "sponsor_exit_multiple": sponsor.exit_multiple if sponsor else None,
            "hold_period": sponsor.horizon if sponsor else None,
        }
    return {
        "case_id": case.case_id,
        "company_id": case.company_id,
        "built_at": case.built_at,
        "methodology_version": case.methodology_version,
        "readiness": case.readiness.status if case.readiness else None,
        "readiness_blockers": case.readiness.blockers if case.readiness else [],
        "readiness_warnings": case.readiness.warnings if case.readiness else [],
        "data_vintage": case.data_vintage,
        "assumptions": {
            "status": case.assumptions.status,
            "path": str(case.assumptions.path) if case.assumptions.path else None,
            "wacc": case.wacc.wacc,
            "beta": case.wacc.beta,
            "beta_source": case.wacc.beta_source,
            "cost_of_debt": case.wacc.cost_of_debt_pretax,
            "cost_of_debt_source": case.wacc.cost_of_debt_source,
            "terminal_roic": case.assumptions.terminal_roic,
            "terminal_growth": case.assumptions.perpetuity_growth,
            "sponsor_exit_multiple": case.sponsor_exit_multiple,
            "sponsor_exit_source": case.sponsor_exit_multiple_source,
        },
        "underwriting_terms": case.underwriting_terms,
        "operating_driver": operating_driver_payload(
            case.assumptions.operating_driver_build
        ),
        "peer_set": {
            "name": case.assessment.peer_set_name,
            "source": case.assessment.peer_source,
            "reviewed": case.assessment.peer_reviewed,
            "members": case.assessment.peers["company_id"].astype(str).tolist(),
        },
        "scenarios": scenarios,
        "notes": case.notes,
    }


def persist_case_manifest(case, root: Path) -> Path:
    target = ensure_dir(Path(root) / case.company_id.replace(":", "_")) / f"{case.case_id}.json"
    if not target.exists():
        write_json_atomic(case_manifest(case), target)
    return target


def compare_case_manifests(previous: dict, current: dict) -> pd.DataFrame:
    rows = []
    for scenario in sorted(set(previous.get("scenarios", {})) | set(current.get("scenarios", {}))):
        before = previous.get("scenarios", {}).get(scenario, {})
        after = current.get("scenarios", {}).get(scenario, {})
        for metric in ("target_price", "upside", "sponsor_moic", "sponsor_irr"):
            old, new = before.get(metric), after.get(metric)
            rows.append({
                "scenario": scenario,
                "metric": metric,
                "previous": old,
                "current": new,
                "change": (new - old) if old is not None and new is not None else None,
            })
    return pd.DataFrame(rows)


def load_case_manifests(root: Path, company_id: str) -> list[dict]:
    """Return immutable manifests newest first; malformed files stay isolated."""
    folder = Path(root) / company_id.replace(":", "_")
    manifests: list[dict] = []
    if not folder.exists():
        return manifests
    for path in folder.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["_path"] = str(path)
            manifests.append(payload)
        except (OSError, ValueError):
            continue
    return sorted(manifests, key=lambda item: str(item.get("built_at", "")), reverse=True)
