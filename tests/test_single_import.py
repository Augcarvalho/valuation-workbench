"""Single-company export merge: validation gates and upsert semantics."""

import json

import pandas as pd
import pytest

from src.ingestion.single_import import merge_single_export, safe_id, validate_staging

NEW_ID = "BOVESPA:GMAT3"


def _write_staging(root, company_id=NEW_ID, ok=True, revenue=100.0, name="Grupo Mateus"):
    staging = root / safe_id(company_id)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "staging_result.json").write_text(json.dumps({
        "ok": ok, "company_id": company_id, "company_name": name,
        "exported_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "financial_rows": 2, "error": None if ok else "boom",
    }), encoding="utf-8")
    pd.DataFrame([{"company_id": company_id, "ticker": "GMAT3", "company_name": name,
                   "sector": "Brazil Retail", "exchange": "BOVESPA", "currency": "BRL",
                   "source": "Capital IQ Pro Excel Add-In"}]).to_csv(staging / "companies.csv", index=False)
    pd.DataFrame([
        {"company_id": company_id, "period": "2026-03-31", "revenue": revenue, "ebitda": 10.0},
        {"company_id": company_id, "period": "2025-12-31", "revenue": revenue, "ebitda": 9.0},
    ]).to_csv(staging / "financials_quarterly.csv", index=False)
    pd.DataFrame([{"company_id": company_id, "period": "2026-03-31", "share_price": 7.0}]
                 ).to_csv(staging / "market_data.csv", index=False)
    pd.DataFrame([{"company_id": company_id, "date": "2026-06-30", "share_price": 7.0}]
                 ).to_csv(staging / "valuation_history.csv", index=False)
    pd.DataFrame(columns=["company_id", "period", "revenue_est_ntm"]).to_csv(
        staging / "estimates.csv", index=False)
    return staging


def _write_main_exports(exports):
    exports.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"company_id": "NYSE:NKE", "ticker": "NKE", "company_name": "Nike",
         "sector": "Consumer", "exchange": "NYSE", "currency": "USD", "source": "x"},
        {"company_id": NEW_ID, "ticker": "GMAT3", "company_name": "STALE NAME",
         "sector": "Old", "exchange": "BOVESPA", "currency": "BRL", "source": "x"},
    ]).to_csv(exports / "companies.csv", index=False)
    pd.DataFrame([
        {"company_id": "NYSE:NKE", "period": "2026-03-31", "revenue": 999.0, "ebitda": 99.0},
        {"company_id": NEW_ID, "period": "2024-12-31", "revenue": 1.0, "ebitda": 1.0},
    ]).to_csv(exports / "financials_quarterly.csv", index=False)
    for name in ("market_data.csv", "valuation_history.csv", "estimates.csv"):
        pd.DataFrame([{"company_id": "NYSE:NKE", "period": "2026-03-31"}]).to_csv(
            exports / name, index=False)


def test_merge_upserts_and_preserves_other_companies(tmp_path):
    staging_root = tmp_path / "staging"
    exports = tmp_path / "exports"
    _write_staging(staging_root)
    _write_main_exports(exports)

    result = merge_single_export(NEW_ID, staging_root=staging_root, exports_dir=exports)
    assert result.company_name == "Grupo Mateus"
    assert result.rows_merged["financials_quarterly.csv"] == 2

    companies = pd.read_csv(exports / "companies.csv")
    assert len(companies) == 2                                  # NKE + fresh GMAT3
    assert "STALE NAME" not in set(companies["company_name"])   # old row replaced
    fins = pd.read_csv(exports / "financials_quarterly.csv")
    assert (fins[fins["company_id"] == "NYSE:NKE"]["revenue"] == 999.0).all()  # untouched
    assert len(fins[fins["company_id"] == NEW_ID]) == 2         # stale 2024 row gone
    assert list(companies.columns)[:7] == ["company_id", "ticker", "company_name",
                                           "sector", "exchange", "currency", "source"]


def test_merge_creates_main_files_when_absent(tmp_path):
    staging_root = tmp_path / "staging"
    exports = tmp_path / "exports"
    exports.mkdir()
    _write_staging(staging_root)
    merge_single_export(NEW_ID, staging_root=staging_root, exports_dir=exports)
    assert len(pd.read_csv(exports / "companies.csv")) == 1


def test_failed_export_never_touches_main(tmp_path):
    staging_root = tmp_path / "staging"
    exports = tmp_path / "exports"
    _write_staging(staging_root, ok=False)
    _write_main_exports(exports)
    before = (exports / "companies.csv").read_text()
    with pytest.raises(ValueError, match="boom"):
        merge_single_export(NEW_ID, staging_root=staging_root, exports_dir=exports)
    assert (exports / "companies.csv").read_text() == before


def test_empty_revenue_blocks_merge(tmp_path):
    staging_root = tmp_path / "staging"
    staging = _write_staging(staging_root, revenue=None)
    with pytest.raises(ValueError, match="no revenue"):
        validate_staging(NEW_ID, staging)


def test_foreign_rows_block_merge(tmp_path):
    staging_root = tmp_path / "staging"
    staging = _write_staging(staging_root)
    fins = pd.read_csv(staging / "financials_quarterly.csv")
    fins.loc[len(fins)] = {"company_id": "NYSE:EVIL", "period": "2026-03-31",
                           "revenue": 5.0, "ebitda": 1.0}
    fins.to_csv(staging / "financials_quarterly.csv", index=False)
    with pytest.raises(ValueError, match="another company"):
        validate_staging(NEW_ID, staging)


def test_missing_result_json_blocks_merge(tmp_path):
    staging_root = tmp_path / "staging"
    staging = _write_staging(staging_root)
    (staging / "staging_result.json").unlink()
    with pytest.raises(ValueError, match="staging result"):
        validate_staging(NEW_ID, staging)


def test_stale_staging_is_rejected(tmp_path):
    staging = _write_staging(tmp_path / "staging")
    result_path = staging / "staging_result.json"
    result = json.loads(result_path.read_text())
    result["exported_at"] = "2020-01-01 00:00:00"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        validate_staging(NEW_ID, staging)
