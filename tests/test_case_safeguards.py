"""Safeguard tests: applicability gating, INDICATIVE stance, warnings, universe management."""

import json

import pandas as pd
import pytest

from src.ingestion.classification import load_classification
from src.ingestion.store import load_store
from src.ingestion.universe import (
    add_company,
    ensure_universe,
    parse_lookup_result,
)
from src.modeling.valuation_case import (
    CaseNotApplicableError,
    build_valuation_case,
    case_warnings,
    dcf_applicability,
)
from src.modeling.valuation_diagnostics import diagnose_case


@pytest.fixture(scope="module")
def demo_df():
    store = load_store(demo=True)
    return pd.read_csv(store.dataset_path, parse_dates=["period"]), store


# --- applicability gate ---------------------------------------------------------------

def test_financial_business_model_blocks_dcf():
    row = pd.Series({"business_model": "financial", "revenue_ttm": 1000.0, "ebitda_ttm": 200.0})
    ok, reason, detail = dcf_applicability(row)
    assert not ok and "Financial institution" in reason and "dividend-discount" in detail


def test_missing_or_negative_anchors_block_dcf():
    ok, reason, _ = dcf_applicability(pd.Series({"business_model": "operating", "revenue_ttm": float("nan")}))
    assert not ok and "revenue" in reason.lower()
    ok, reason, _ = dcf_applicability(pd.Series({"business_model": "operating",
                                                 "revenue_ttm": 500.0, "ebitda_ttm": -20.0}))
    assert not ok and "EBITDA" in reason


def test_insurers_use_financials_framework_not_ebitda_dcf(demo_df):
    row = pd.Series({"business_model": "insurer", "revenue_ttm": 1000.0, "ebitda_ttm": 80.0})
    ok, _, _ = dcf_applicability(row)
    assert not ok


def test_build_case_raises_clean_error_for_financials(demo_df):
    df, store = demo_df
    frankenstein = df.copy()
    frankenstein.loc[frankenstein["company_id"] == "PRNR3.SA", "business_model"] = "financial"
    with pytest.raises(CaseNotApplicableError) as exc:
        build_valuation_case(frankenstein, "PRNR3.SA", store=store)
    assert "Financial institution" in exc.value.reason


# --- INDICATIVE stance -------------------------------------------------------------------

def test_auto_case_never_shows_formal_recommendation(demo_df):
    df, store = demo_df
    case = build_valuation_case(df, "PRNR3.SA", store=store)   # no assumptions file
    assert not case.assumptions.from_file
    assert case.recommendation.stance == "INDICATIVE"
    assert "NOT a final investment view" in case.recommendation.headline
    assert case.recommendation.stance not in {"BUY", "HOLD", "SELL"}


def test_illustrative_file_does_not_issue_formal_recommendation(demo_df):
    df, store = demo_df
    case = build_valuation_case(df, "GOOGL", store=store)   # demo sample YAML
    assert case.assumptions.from_file
    assert case.assumptions.status == "illustrative"
    assert case.recommendation.stance == "INDICATIVE"


# --- warnings engine ------------------------------------------------------------------------

def test_case_warnings_flag_default_beta_and_fallbacks(demo_df):
    df, store = demo_df
    case = build_valuation_case(df, "PRNR3.SA", store=store)
    assumptions = [d for d in diagnose_case(case) if d.category == "assumption"]
    texts = " | ".join(d.text for d in assumptions)
    assert "1.0 fallback" in texts
    # Assumption gaps are not mislabeled as mathematical failures.
    assert "1.0 fallback" not in " | ".join(w["text"] for w in case_warnings(case))
    severities = {w["severity"] for w in case_warnings(case)}
    assert severities <= {"high", "medium", "low"}


def test_case_warnings_terminal_value_thresholds(demo_df):
    df, store = demo_df
    case = build_valuation_case(df, "GOOGL", store=store)
    tv_pct = case.base.terminal_pct_of_ev
    cross_checks = [d for d in diagnose_case(case) if d.category == "cross_check"]
    texts = " | ".join(d.text for d in cross_checks)
    if tv_pct > 0.90:
        assert "enterprise value" in texts
    # Implied-growth-vs-WACC guard fires when the gap is inside 150bps.
    if case.base.implied_terminal_growth is not None and \
            case.base.implied_terminal_growth >= case.wacc.wacc - 0.015:
        assert "perpetual" in texts


def test_final_case_can_document_and_clear_market_cross_check(demo_df):
    df, store = demo_df
    case = build_valuation_case(df, "GOOGL", store=store)
    case.market_reference_multiple = case.exit_multiple * 2.0
    case.assumptions.status = "final"

    case.assumptions.reviewed_cross_checks = {}
    pending = {d.code for d in diagnose_case(case)}
    assert "market_fundamental_gap" in pending

    case.assumptions.reviewed_cross_checks = {
        "market_fundamental_gap": "Reviewed and retained as an upside-only market cross-check."
    }
    reviewed = {d.code for d in diagnose_case(case)}
    assert "market_fundamental_gap" not in reviewed


# --- universe management -----------------------------------------------------------------------

def _bootstrap_files(tmp_path):
    src = tmp_path / "companies.csv"
    pd.DataFrame([
        {"company_id": "NYSE:AAA", "ticker": "AAA", "company_name": "Alpha",
         "sector": "Theme One", "exchange": "NYSE", "currency": "USD", "source": "test"},
        {"company_id": "NASDAQ:BBB", "ticker": "BBB", "company_name": "Beta",
         "sector": "Theme Two", "exchange": "NASDAQ", "currency": "USD", "source": "test"},
    ]).to_csv(src, index=False)
    return tmp_path / "universe.csv", src


def test_universe_bootstraps_from_export(tmp_path):
    upath, src = _bootstrap_files(tmp_path)
    universe = ensure_universe(upath, src)
    assert upath.exists()
    assert list(universe.columns) == ["id", "ticker", "sector", "currency"]
    assert len(universe) == 2
    # Second call reads the file, no re-bootstrap.
    again = ensure_universe(upath, src)
    assert len(again) == 2


def test_add_company_duplicate_and_validation(tmp_path):
    upath, src = _bootstrap_files(tmp_path)
    cls_path = tmp_path / "classification_private.csv"
    log_path = tmp_path / "add_log.csv"

    updated = add_company(
        company_id="BOVESPA:GMAT3", ticker="GMAT3", theme="Brazil Retail",
        currency="brl", peer_group="LatAm Food Retail", business_model="Operating",
        company_name="Grupo Mateus",
        universe_path=upath, bootstrap_source=src,
        classification_path=cls_path, log_path=log_path,
    )
    assert len(updated) == 3
    row = updated[updated["id"] == "BOVESPA:GMAT3"].iloc[0]
    assert row["currency"] == "BRL" and row["sector"] == "Brazil Retail"

    # Private classification overlay written with normalized business model.
    cls = pd.read_csv(cls_path)
    assert cls.iloc[0]["business_model"] == "operating"
    assert cls.iloc[0]["peer_group"] == "LatAm Food Retail"

    # Audit log appended.
    log = pd.read_csv(log_path)
    assert log.iloc[0]["company_id"] == "BOVESPA:GMAT3"

    # Duplicates rejected (by id and by ticker).
    with pytest.raises(ValueError, match="already"):
        add_company("BOVESPA:GMAT3", "GMAT3", "X", "BRL", "Y", "operating",
                    universe_path=upath, bootstrap_source=src,
                    classification_path=cls_path, log_path=log_path)
    # Malformed id rejected.
    with pytest.raises(ValueError, match="EXCHANGE:TICKER"):
        add_company("GMAT3", "GMAT3", "X", "BRL", "Y", "operating",
                    universe_path=upath, bootstrap_source=src,
                    classification_path=cls_path, log_path=log_path)


def test_private_classification_overlay_wins(tmp_path):
    overlay = tmp_path / "overlay.csv"
    pd.DataFrame([
        {"company_id": "NASDAQ:LULU", "peer_group": "Private Group", "business_model": "operating"},
        {"company_id": "NEW:XYZ", "peer_group": "New Group", "business_model": "financial"},
    ]).to_csv(overlay, index=False)
    merged = load_classification(overlay_path=overlay)
    lulu = merged[merged["company_id"] == "NASDAQ:LULU"].iloc[0]
    assert lulu["peer_group"] == "Private Group"       # overlay beats committed reference
    assert (merged["company_id"] == "NEW:XYZ").any()


# --- lookup parsing ---------------------------------------------------------------------------------

def test_parse_lookup_result_paths():
    ok = parse_lookup_result(json.dumps({
        "company_id": "BOVESPA:GMAT3", "resolved": True, "company_name": "Grupo Mateus S.A.",
        "exchange": "BOVESPA", "industry": "Food Retail", "currency": "BRL", "error": "",
    }))
    assert ok.resolved and ok.company_name.startswith("Grupo")

    invalid = parse_lookup_result(json.dumps({
        "company_id": "NYSE:NOTREAL", "resolved": False, "company_name": None,
        "error": "Identifier did not resolve in Capital IQ.",
    }))
    assert not invalid.resolved and "resolve" in invalid.error

    # resolved=true but empty name is still treated as unresolved.
    empty_name = parse_lookup_result(json.dumps({"company_id": "X:Y", "resolved": True, "company_name": ""}))
    assert not empty_name.resolved

    garbage = parse_lookup_result("this is not json")
    assert not garbage.resolved and "unreadable" in garbage.error
