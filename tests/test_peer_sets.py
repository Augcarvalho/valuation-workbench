"""Peer-set workflow tests: scoring, approval, resolution hierarchy, privacy."""

import subprocess

import pandas as pd
import pytest

from src.config import PROJECT_ROOT
from src.ingestion.store import load_store
from src.modeling.metrics import latest_rows
from src.modeling.peer_sets import (
    MIN_VALID_PEERS,
    generate_peer_sets_for_all,
    get_approved_peer_set,
    load_capiq_comp_set,
    resolve_peers,
    save_peer_set,
    score_peer_candidate,
    suggest_peers,
)


@pytest.fixture()
def demo_latest():
    store = load_store(demo=True)
    df = pd.read_csv(store.dataset_path, parse_dates=["period"])
    return df, latest_rows(df)


# --- scoring -------------------------------------------------------------------------

def test_scoring_rewards_similarity_and_penalizes_cross_model():
    anchor = pd.Series({"peer_group": "G", "business_model": "operating",
                        "primary_industry": "Footwear", "country": "United States",
                        "currency": "USD", "exchange": "NYSE", "market_cap": 1000.0,
                        "ebitda_margin_ttm": 0.25, "revenue_yoy_growth": 0.10})
    twin = anchor.copy()
    score_twin, reasons = score_peer_candidate(anchor, twin)
    assert score_twin > 90
    assert "same peer group" in reasons and "similar size" in reasons
    assert "same CapIQ industry" in reasons

    lender = anchor.copy()
    lender["business_model"] = "financial"
    score_lender, _ = score_peer_candidate(anchor, lender)
    assert score_lender <= score_twin - 25   # cross-model penalty bites (twin clips at 100)

    stranger = pd.Series({"peer_group": "X", "business_model": "operating",
                          "primary_industry": "Banks", "country": "Brazil",
                          "currency": "BRL", "exchange": "B3", "market_cap": 5.0,
                          "ebitda_margin_ttm": 0.02, "revenue_yoy_growth": -0.2})
    score_stranger, _ = score_peer_candidate(anchor, stranger)
    assert score_stranger < 30


def test_suggest_peers_ranks_same_group_first(demo_latest):
    _, latest = demo_latest
    sugg = suggest_peers(latest, "TOTS3.SA")
    assert not sugg.empty
    assert "TOTS3" not in list(sugg["ticker"])          # anchor excluded
    assert sugg.iloc[0]["score"] >= sugg.iloc[-1]["score"]
    assert "reasons" in sugg.columns


# --- save / approve / resolve ----------------------------------------------------------

def test_save_and_resolve_approved_set(tmp_path, demo_latest):
    df, latest = demo_latest
    path = tmp_path / "peer_sets.csv"
    members = [{"company_id": cid, "score": 80, "rationale": "test"}
               for cid in ["LWSA3.SA", "BMOB3.SA", "CSUD3.SA"]]
    save_peer_set("TOTS3.SA", "TOTS3 comps", members, source="fallback", path=path)

    approved = get_approved_peer_set("TOTS3.SA", path=path)
    assert approved and set(approved["members"]) == {"LWSA3.SA", "BMOB3.SA", "CSUD3.SA"}

    row = latest[latest["company_id"] == "TOTS3.SA"].iloc[0]
    res = resolve_peers(latest, row, peer_sets_path=path)
    assert res.source == "fallback" and res.reviewed
    assert res.warning is None
    assert set(res.peers["company_id"]) == {"TOTS3.SA", "LWSA3.SA", "BMOB3.SA", "CSUD3.SA"}

    # Saving again REPLACES the previous set for the anchor.
    save_peer_set("TOTS3.SA", "v2", members[:3], source="manual", path=path)
    sets = pd.read_csv(path)
    assert sets["peer_set_name"].nunique() == 1 and sets["peer_set_name"].iloc[0] == "v2"


def test_small_set_requires_override_and_warns(tmp_path, demo_latest):
    _, latest = demo_latest
    path = tmp_path / "peer_sets.csv"
    two = [{"company_id": "LWSA3.SA"}, {"company_id": "BMOB3.SA"}]
    with pytest.raises(ValueError, match="at least"):
        save_peer_set("TOTS3.SA", "small", two, source="manual", path=path)
    save_peer_set("TOTS3.SA", "small", two, source="manual", allow_small=True, path=path)

    row = latest[latest["company_id"] == "TOTS3.SA"].iloc[0]
    res = resolve_peers(latest, row, peer_sets_path=path)
    assert res.reviewed and res.warning is not None
    assert "fewer than" in res.warning


def test_fallback_hierarchy_without_approved_set(tmp_path, demo_latest):
    _, latest = demo_latest
    path = tmp_path / "nonexistent.csv"
    row = latest[latest["company_id"] == "TOTS3.SA"].iloc[0]
    res = resolve_peers(latest, row, peer_sets_path=path)
    assert res.source == "peer_group" and not res.reviewed

    # A one-member peer group forces the universe fallback with a warning.
    lonely = latest.copy()
    lonely.loc[lonely["company_id"] == "TOTS3.SA", "peer_group"] = "Lonely Group"
    row2 = lonely[lonely["company_id"] == "TOTS3.SA"].iloc[0]
    res2 = resolve_peers(lonely, row2, peer_sets_path=path)
    assert res2.source == "universe"
    assert res2.warning and "FULL universe" in res2.warning


def test_valuation_uses_approved_peer_set(tmp_path, monkeypatch, demo_latest):
    """The assessment spine (and therefore the valuation case) consumes the
    approved set: peer medians must come from the saved members."""
    import src.modeling.peer_sets as ps
    from src.modeling.assessment import build_assessment

    df, latest = demo_latest
    path = tmp_path / "peer_sets.csv"
    members = [{"company_id": cid} for cid in ["LWSA3.SA", "BMOB3.SA", "CSUD3.SA"]]
    save_peer_set("TOTS3.SA", "TOTS3 approved", members, source="manual", path=path)
    monkeypatch.setattr(ps, "PEER_SETS_PATH", path)

    a = build_assessment(df, "TOTS3.SA")
    assert a.peer_source == "manual" and a.peer_reviewed
    assert set(a.peers["company_id"]) == {"TOTS3.SA", "LWSA3.SA", "BMOB3.SA", "CSUD3.SA"}
    expected_median = latest[latest["company_id"].isin(
        ["TOTS3.SA", "LWSA3.SA", "BMOB3.SA", "CSUD3.SA"])]["ebitda_margin_ttm"].median()
    assert a.peer_median["ebitda_margin_ttm"] == pytest.approx(expected_median)


def test_batch_generation_is_unreviewed_and_respects_analyst_sets(tmp_path, demo_latest):
    _, latest = demo_latest
    path = tmp_path / "peer_sets.csv"
    log = tmp_path / "log.csv"

    out = generate_peer_sets_for_all(latest, threshold=40, path=path, log_path=log)
    assert (out["outcome"] == "generated (unreviewed)").any()

    row = latest[latest["company_id"] == "TOTS3.SA"].iloc[0]
    res = resolve_peers(latest, row, peer_sets_path=path)
    assert res.source == "fallback" and not res.reviewed   # visible but flagged

    # An analyst-reviewed set is never overwritten by regeneration.
    members = [{"company_id": c} for c in ["LWSA3.SA", "BMOB3.SA", "CSUD3.SA"]]
    save_peer_set("TOTS3.SA", "analyst set", members, source="manual", path=path)
    out2 = generate_peer_sets_for_all(latest, threshold=40, path=path, log_path=log)
    kept = out2[out2["company_id"] == "TOTS3.SA"]["outcome"].iloc[0]
    assert kept == "kept analyst-reviewed set"
    res2 = resolve_peers(latest, row, peer_sets_path=path)
    assert res2.source == "manual" and res2.reviewed


# --- CapIQ comp-set import hook -----------------------------------------------------------

def test_capiq_comp_set_import_matches_universe(tmp_path, demo_latest):
    _, latest = demo_latest
    (tmp_path / "TOTS3.SA.csv").write_text(
        "ticker\nLWSA3\nBMOB3\nUNKNOWN99\n", encoding="utf-8")
    matched = load_capiq_comp_set("TOTS3.SA", latest, import_dir=tmp_path)
    assert matched is not None
    assert matched["in_universe"].sum() == 2
    assert (~matched["in_universe"]).sum() == 1


# --- privacy ----------------------------------------------------------------------------------

def test_peer_set_files_are_git_ignored():
    for path in ["data_private/peer_sets_private.csv", "data_private/peer_suggestions_log.csv",
                 "data_private/capiq_exports/comp_sets/NASDAQ_LULU.csv"]:
        result = subprocess.run(["git", "check-ignore", path], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{path} not ignored"


def test_review_workflow_schema_migration_and_actions(tmp_path, demo_latest):
    """Old-schema files migrate on load; approve/reject/reset behave."""
    import src.modeling.peer_sets as ps

    _, latest = demo_latest
    path = tmp_path / "peer_sets.csv"

    # Legacy file without the new review columns migrates transparently.
    legacy = pd.DataFrame([{
        "peer_set_id": "abc", "peer_set_name": "legacy", "anchor_company_id": "TOTS3.SA",
        "peer_company_id": "LWSA3.SA", "source": "fallback", "score": 70,
        "rationale": "r", "created_at": "2026-01-01", "reviewed_by_user": False,
    }])
    legacy.to_csv(path, index=False)
    loaded = ps.load_peer_sets(path)
    assert "inclusion_status" in loaded.columns and "reviewer_note" in loaded.columns

    # Fresh generated set -> approve with a note.
    members = [{"company_id": c} for c in ["LWSA3.SA", "BMOB3.SA", "CSUD3.SA"]]
    save_peer_set("TOTS3.SA", "set", members, source="fallback",
                  reviewed_by_user=False, path=path)
    assert ps.approve_peer_set("TOTS3.SA", "checked vs 10-K peers", path=path)
    approved = get_approved_peer_set("TOTS3.SA", path=path)
    assert approved["reviewed"] and approved["reviewed_at"] is not None
    assert approved["reviewer_note"] == "checked vs 10-K peers"

    # Reject one member: stays in file, leaves analytics.
    assert ps.reject_peers("TOTS3.SA", ["BMOB3.SA"], path=path) == 1
    after = get_approved_peer_set("TOTS3.SA", path=path)
    assert "BMOB3.SA" not in after["members"]
    assert "BMOB3.SA" in after["rejected"]
    row = latest[latest["company_id"] == "TOTS3.SA"].iloc[0]
    res = resolve_peers(latest, row, peer_sets_path=path)
    assert "BMOB3.SA" not in set(res.peers["company_id"])

    # Reset regenerates an UNREVIEWED scored set for this anchor only.
    assert ps.reset_to_generated("TOTS3.SA", latest, threshold=40, path=path,
                                 log_path=tmp_path / "log.csv")
    fresh = get_approved_peer_set("TOTS3.SA", path=path)
    assert not fresh["reviewed"]
