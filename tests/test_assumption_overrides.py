from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.modeling.assumption_overrides import (
    AssumptionValidationError,
    assumption_path,
    read_assumption_payload,
    reset_assumption_payload,
    save_assumption_payload,
    validate_assumption_payload,
)


def _payload(growth: float = 0.03, status: str = "draft") -> dict:
    return {
        "status": status,
        "horizon_years": 5,
        "transition_years": "auto",
        "scenarios": {
            "base": {
                "revenue_growth": {"start": 0.08, "end": 0.04},
                "ebitda_margin": {"start": 0.20, "end": 0.22},
                "capex_pct_revenue": {"start": 0.05, "end": 0.04},
            }
        },
        "terminal": {
            "perpetuity_growth": growth,
            "roic": 0.12,
            "wacc": 0.09,
        },
        "review_note": "Base case reviewed against management guidance.",
    }


def test_save_archives_and_reset_restores_automatic(tmp_path):
    company_id = "NASDAQ:TEST"
    first_time = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    path = save_assumption_payload(company_id, tmp_path, _payload(), now=first_time)
    assert path == assumption_path(company_id, tmp_path)
    assert read_assumption_payload(path)["terminal"]["perpetuity_growth"] == pytest.approx(0.03)

    second = _payload(growth=0.025)
    save_assumption_payload(
        company_id, tmp_path, second, now=first_time + timedelta(minutes=1)
    )
    history = list((tmp_path / "history" / "NASDAQ_TEST").glob("*.yaml"))
    assert len(history) == 1
    assert read_assumption_payload(history[0])["terminal"]["perpetuity_growth"] == pytest.approx(0.03)

    assert reset_assumption_payload(
        company_id, tmp_path, now=first_time + timedelta(minutes=2)
    )
    assert not path.exists()
    assert len(list((tmp_path / "history" / "NASDAQ_TEST").glob("*.yaml"))) == 2

    audit = pd.read_csv(tmp_path / "assumption_audit.csv")
    assert list(audit["action"]) == ["created", "updated", "reset_to_automatic"]
    assert audit.iloc[1]["change_count"] >= 1


def test_validation_collects_finance_and_structure_errors():
    payload = _payload(growth=0.10)
    payload["horizon_years"] = 2
    payload["terminal"]["wacc"] = 0.08
    payload["terminal"]["roic"] = 0.09
    payload["scenarios"]["base"]["capex_pct_revenue"] = 0.90

    errors = validate_assumption_payload(payload)
    joined = " | ".join(errors)
    assert "horizon" in joined.lower()
    assert "Capex" in joined
    assert "below terminal WACC" in joined
    assert "ROIC" in joined


def test_invalid_payload_is_never_written(tmp_path):
    payload = _payload()
    payload["wacc"] = {"beta": 8.0}
    with pytest.raises(AssumptionValidationError):
        save_assumption_payload("NYSE:BAD", tmp_path, payload)
    assert not assumption_path("NYSE:BAD", tmp_path).exists()
