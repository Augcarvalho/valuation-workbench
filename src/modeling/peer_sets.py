"""Peer-set management: suggested comps, analyst approval, resolution hierarchy.

Institutional comp sets are *proposed by data, approved by the analyst*. This
module implements that workflow:

**Source hierarchy** (highest priority first):
1. ``capiq_comp_set`` - a comp set exported from Capital IQ Pro (drop a CSV in
   ``data_private/capiq_exports/comp_sets/<ANCHOR_ID>.csv`` with a
   ``company_id`` or ``ticker`` column) and approved in the app.
2. ``fallback`` / ``manual`` - rule-based suggestions scored on Capital
   IQ-exported attributes (peer group, business model, geography/currency,
   size, margin, growth), approved and optionally edited by the analyst.
3. The static ``peer_group`` mapping (no analyst review) - used when no
   approved peer set exists.
4. The full universe - last resort, flagged with a visible warning.

Nothing affects valuation, percentiles, or benchmarking until the analyst
saves an approved set. All peer-set files live in ``data_private/``
(gitignored); the public demo can ship sample sets separately.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PRIVATE_CAPIQ_DIR, PRIVATE_DATA_DIR

PEER_SETS_PATH = PRIVATE_DATA_DIR / "peer_sets_private.csv"
SUGGESTIONS_LOG_PATH = PRIVATE_DATA_DIR / "peer_suggestions_log.csv"
COMP_SET_IMPORT_DIR = PRIVATE_CAPIQ_DIR / "comp_sets"
INDUSTRY_PATH = PRIVATE_CAPIQ_DIR / "company_industry.csv"

PEER_SET_COLUMNS = [
    "peer_set_id", "peer_set_name", "anchor_company_id", "peer_company_id",
    "source", "score", "rationale", "created_at", "reviewed_by_user",
    # Review-workflow columns (older files auto-migrate: absent -> NA on load).
    "inclusion_status",     # suggested | approved | rejected | manually_added
    "reviewed_at",
    "reviewer_note",
    "updated_at",
]

MIN_VALID_PEERS = 3

# Scoring weights. Disclosed in the methodology panel. ``industry``/``country``
# only contribute when the CapIQ industry export (company_industry.csv) exists.
WEIGHTS = {
    "peer_group": 30,
    "business_model": 15,
    "industry": 15,      # CapIQ primary industry (e.g. "Footwear")
    "currency": 10,
    "exchange": 5,
    "country": 5,
    "size": 15,
    "margin": 10,
    "growth": 5,
}


# --- suggestion scoring (pure, testable) --------------------------------------------

def _log_proximity(a: float | None, b: float | None, decades: float = 1.0) -> float:
    """1.0 when equal, 0.0 when `decades` orders of magnitude apart."""
    if a is None or b is None or pd.isna(a) or pd.isna(b) or a <= 0 or b <= 0:
        return 0.0
    gap = abs(np.log10(a) - np.log10(b))
    return float(max(0.0, 1.0 - gap / decades))


def _abs_proximity(a: float | None, b: float | None, span: float) -> float:
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return 0.0
    return float(max(0.0, 1.0 - abs(a - b) / span))


def score_peer_candidate(anchor: pd.Series, candidate: pd.Series) -> tuple[float, list[str]]:
    """Similarity score (0-100) plus human-readable reason chips."""
    score = 0.0
    reasons: list[str] = []

    if pd.notna(anchor.get("peer_group")) and anchor.get("peer_group") == candidate.get("peer_group"):
        score += WEIGHTS["peer_group"]
        reasons.append("same peer group")
    if str(anchor.get("business_model", "")) == str(candidate.get("business_model", "")):
        score += WEIGHTS["business_model"]
        reasons.append("same business model")
    else:
        score -= 20  # cross-model comps (lender vs operating) are rarely valid
    if pd.notna(anchor.get("primary_industry")) and str(anchor.get("primary_industry")).strip() \
            and anchor.get("primary_industry") == candidate.get("primary_industry"):
        score += WEIGHTS["industry"]
        reasons.append("same CapIQ industry")
    if str(anchor.get("currency", "")) == str(candidate.get("currency", "")):
        score += WEIGHTS["currency"]
        reasons.append("same reporting currency")
    if pd.notna(anchor.get("exchange")) and anchor.get("exchange") == candidate.get("exchange"):
        score += WEIGHTS["exchange"]
        reasons.append("same exchange")
    if pd.notna(anchor.get("country")) and str(anchor.get("country")).strip() \
            and anchor.get("country") == candidate.get("country"):
        score += WEIGHTS["country"]
        reasons.append("same country")

    size = _log_proximity(anchor.get("market_cap_usd", anchor.get("market_cap")),
                          candidate.get("market_cap_usd", candidate.get("market_cap")), decades=1.2)
    if size > 0.4:
        score += WEIGHTS["size"] * size
        reasons.append("similar size")

    margin = _abs_proximity(anchor.get("ebitda_margin_ttm"), candidate.get("ebitda_margin_ttm"), span=0.25)
    if margin > 0.4:
        score += WEIGHTS["margin"] * margin
        reasons.append("similar margin profile")

    growth = _abs_proximity(anchor.get("revenue_yoy_growth"), candidate.get("revenue_yoy_growth"), span=0.30)
    if growth > 0.4:
        score += WEIGHTS["growth"] * growth
        reasons.append("similar growth profile")

    return float(np.clip(score, 0.0, 100.0)), reasons


def attach_industry(latest: pd.DataFrame, path: Path | None = None) -> pd.DataFrame:
    """Join the CapIQ industry export (primary industry / country) when present."""
    p = Path(path) if path is not None else INDUSTRY_PATH
    if not p.exists() or "company_id" not in latest.columns:
        return latest
    try:
        ind = pd.read_csv(p)
    except Exception:
        return latest
    keep = [c for c in ("company_id", "primary_industry", "country") if c in ind.columns]
    if len(keep) < 2:
        return latest
    merged = latest.drop(columns=[c for c in ("primary_industry", "country") if c in latest.columns])
    return merged.merge(ind[keep].drop_duplicates("company_id"), on="company_id", how="left")


def suggest_peers(latest: pd.DataFrame, anchor_company_id: str, top_n: int = 12) -> pd.DataFrame:
    """Scored peer suggestions from within the exported universe.

    Note: candidates are limited to companies already exported from Capital IQ.
    To consider an outside name, add it to the universe first (Add Company),
    refresh, and re-run the suggestion.
    """
    latest = attach_industry(latest)
    anchor_rows = latest[latest["company_id"] == anchor_company_id]
    if anchor_rows.empty:
        return pd.DataFrame(columns=["company_id", "ticker", "company_name", "score", "reasons"])
    anchor = anchor_rows.iloc[0]

    rows = []
    for _, cand in latest.iterrows():
        if cand["company_id"] == anchor_company_id:
            continue
        score, reasons = score_peer_candidate(anchor, cand)
        rows.append({
            "company_id": cand["company_id"],
            "ticker": str(cand.get("ticker", "")).replace(".SA", ""),
            "company_name": cand.get("company_name", ""),
            "exchange": cand.get("exchange", ""),
            "currency": cand.get("currency", ""),
            "peer_group": cand.get("peer_group", ""),
            "market_cap": cand.get("market_cap"),
            "revenue_ttm": cand.get("revenue_ttm"),
            "ebitda_margin_ttm": cand.get("ebitda_margin_ttm"),
            "score": round(score, 1),
            "reasons": ", ".join(reasons) if reasons else "low similarity",
        })
    out = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return out.head(top_n)


# --- Capital IQ comp-set import hook ---------------------------------------------------

def _compset_filename(anchor_company_id: str) -> str:
    return anchor_company_id.replace(":", "_") + ".csv"


def load_capiq_comp_set(anchor_company_id: str, latest: pd.DataFrame,
                        import_dir: Path = COMP_SET_IMPORT_DIR) -> pd.DataFrame | None:
    """Comp set exported from Capital IQ Pro, matched against the universe.

    Accepts a CSV with a ``company_id`` and/or ``ticker`` column. Members not
    in the exported universe are reported but cannot be used until added.
    """
    path = Path(import_dir) / _compset_filename(anchor_company_id)
    if not path.exists():
        return None
    try:
        raw = pd.read_csv(path)
    except Exception:
        return None
    raw.columns = [c.strip().lower() for c in raw.columns]
    matches = []
    for _, r in raw.iterrows():
        cid = str(r.get("company_id", "")).strip()
        ticker = str(r.get("ticker", "")).strip().upper()
        hit = pd.DataFrame()
        if cid:
            hit = latest[latest["company_id"].str.upper() == cid.upper()]
        if hit.empty and ticker:
            hit = latest[latest["ticker"].astype(str).str.upper().str.replace(".SA", "", regex=False) == ticker]
        if not hit.empty:
            matches.append({"company_id": hit.iloc[0]["company_id"], "in_universe": True})
        else:
            matches.append({"company_id": cid or ticker, "in_universe": False})
    return pd.DataFrame(matches)


# --- persistence --------------------------------------------------------------------------

def load_peer_sets(path: Path = PEER_SETS_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=PEER_SET_COLUMNS)
    df = pd.read_csv(path)
    for col in PEER_SET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    for col in ["peer_set_id", "peer_set_name", "anchor_company_id", "peer_company_id",
                "source", "rationale", "created_at", "inclusion_status",
                "reviewed_at", "reviewer_note", "updated_at"]:
        df[col] = df[col].astype("object")
    return df[PEER_SET_COLUMNS]


def get_approved_peer_set(anchor_company_id: str, path: Path = PEER_SETS_PATH) -> dict | None:
    """Latest saved peer set for an anchor: {name, source, members, reviewed, ...}.

    Analyst-reviewed and batch-generated (unreviewed) sets are both returned;
    ``reviewed`` tells the caller which one it is so the UI can label honestly.
    """
    sets = load_peer_sets(path)
    if sets.empty:
        return None
    mine = sets[sets["anchor_company_id"] == anchor_company_id]
    if mine.empty:
        return None
    latest_set_id = mine.sort_values("created_at")["peer_set_id"].iloc[-1]
    members = mine[mine["peer_set_id"] == latest_set_id]
    # Rejected members stay in the file for audit but never feed analytics.
    status = members["inclusion_status"].astype(str).str.lower()
    active = members[status != "rejected"]
    rejected = members[status == "rejected"]
    note = ""
    notes = members["reviewer_note"].dropna().astype(str)
    if not notes.empty and notes.iloc[-1] not in ("", "nan", "<NA>"):
        note = notes.iloc[-1]
    return {
        "peer_set_id": latest_set_id,
        "name": members["peer_set_name"].iloc[0],
        "source": members["source"].iloc[0],
        "created_at": members["created_at"].iloc[0],
        "reviewed": str(members["reviewed_by_user"].iloc[0]).lower() in ("true", "1"),
        "reviewed_at": members["reviewed_at"].dropna().astype(str).iloc[-1]
                       if members["reviewed_at"].notna().any() else None,
        "reviewer_note": note,
        "members": list(active["peer_company_id"]),
        "rejected": list(rejected["peer_company_id"]),
        "rationales": dict(zip(active["peer_company_id"], active["rationale"])),
    }


def save_peer_set(
    anchor_company_id: str,
    peer_set_name: str,
    members: list[dict],
    source: str,
    reviewed_by_user: bool = True,
    allow_small: bool = False,
    path: Path = PEER_SETS_PATH,
) -> str:
    """Persist an approved peer set (replaces any earlier set for the anchor).

    ``members``: [{company_id, score?, rationale?}, ...]. Fewer than
    ``MIN_VALID_PEERS`` requires ``allow_small=True`` (explicit override).
    """
    clean = [m for m in members if str(m.get("company_id", "")).strip()
             and m["company_id"] != anchor_company_id]
    # De-duplicate, keep order.
    seen, unique = set(), []
    for m in clean:
        if m["company_id"] not in seen:
            seen.add(m["company_id"])
            unique.append(m)
    if len(unique) < MIN_VALID_PEERS and not allow_small:
        raise ValueError(
            f"Peer set has {len(unique)} member(s); at least {MIN_VALID_PEERS} required "
            f"(or pass an explicit small-set override)."
        )
    if not unique:
        raise ValueError("Peer set has no valid members.")

    set_id = uuid.uuid4().hex[:10]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_status = "approved" if reviewed_by_user else "suggested"
    rows = pd.DataFrame([{
        "peer_set_id": set_id,
        "peer_set_name": peer_set_name.strip() or f"{anchor_company_id} comps",
        "anchor_company_id": anchor_company_id,
        "peer_company_id": m["company_id"],
        "source": source,
        "score": m.get("score"),
        "rationale": m.get("rationale", ""),
        "created_at": now,
        "reviewed_by_user": reviewed_by_user,
        "inclusion_status": m.get("inclusion_status", default_status),
        "reviewed_at": now if reviewed_by_user else pd.NA,
        "reviewer_note": m.get("reviewer_note", ""),
        "updated_at": now,
    } for m in unique])

    existing = load_peer_sets(path)
    # Replace: drop prior sets for this anchor.
    existing = existing[existing["anchor_company_id"] != anchor_company_id]
    if existing.empty:
        combined = rows
    else:
        records = existing.to_dict(orient="records") + rows.to_dict(orient="records")
        combined = pd.DataFrame.from_records(records, columns=PEER_SET_COLUMNS)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return set_id


def log_suggestions(anchor_company_id: str, suggestions: pd.DataFrame,
                    accepted_ids: list[str], path: Path = SUGGESTIONS_LOG_PATH) -> None:
    """Audit trail: every suggestion shown, with the accept/reject outcome."""
    if suggestions.empty:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = pd.DataFrame([{
        "logged_at": now,
        "anchor_company_id": anchor_company_id,
        "suggested_company_id": s["company_id"],
        "score": s.get("score"),
        "reasons": s.get("reasons", ""),
        "accepted": s["company_id"] in accepted_ids,
    } for _, s in suggestions.iterrows()])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if Path(path).exists():
        rows.to_csv(path, mode="a", header=False, index=False)
    else:
        rows.to_csv(path, index=False)


def rejected_suggestions(anchor_company_id: str, path: Path = SUGGESTIONS_LOG_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    log = pd.read_csv(path)
    mine = log[(log["anchor_company_id"] == anchor_company_id) & (~log["accepted"].astype(bool))]
    return mine.sort_values("logged_at").drop_duplicates("suggested_company_id", keep="last")


# --- resolution hierarchy -------------------------------------------------------------------

@dataclass
class PeerResolution:
    peers: pd.DataFrame
    source: str            # capiq_comp_set | capiq_web_peer_comps | manual | fallback | peer_group | universe
    reviewed: bool
    warning: str | None = None
    set_name: str = ""

    @property
    def count(self) -> int:
        return len(self.peers)


def _issuer_key(frame: pd.DataFrame) -> pd.Series:
    if "issuer_id" in frame.columns:
        issuer = frame["issuer_id"].astype("string")
    else:
        issuer = pd.Series(pd.NA, index=frame.index, dtype="string")
    if "company_name" in frame.columns:
        name = (frame["company_name"].astype(str).str.lower()
                .str.replace(r"[^a-z0-9]", "", regex=True))
    else:
        name = frame["company_id"].astype(str)
    return issuer.where(issuer.notna() & issuer.str.strip().ne(""), name)


def _dedupe_issuers(peers: pd.DataFrame, anchor_id: str) -> pd.DataFrame:
    """Keep one listing per issuer and remove anchor cross-listings."""
    if peers.empty:
        return peers
    out = peers.copy()
    out["_issuer_key"] = _issuer_key(out)
    anchor = out[out["company_id"].astype(str) == anchor_id]
    anchor_key = anchor["_issuer_key"].iloc[0] if not anchor.empty else None
    anchor_row = anchor.head(1)
    candidates = out[out["company_id"].astype(str) != anchor_id]
    if anchor_key is not None:
        candidates = candidates[candidates["_issuer_key"] != anchor_key]
    candidates = candidates.drop_duplicates("_issuer_key", keep="first")
    return pd.concat([anchor_row, candidates], ignore_index=True).drop(columns="_issuer_key")


def resolve_peers(latest: pd.DataFrame, row: pd.Series,
                  peer_sets_path: Path | None = None) -> PeerResolution:
    """Approved peer set > peer_group mapping > full universe (with warning).

    The anchor row is always included in the returned frame (needed for
    percentile context), matching the previous behaviour.
    """
    # Late-bound so tests (and future config) can repoint the module path.
    path = peer_sets_path if peer_sets_path is not None else PEER_SETS_PATH
    anchor_id = str(row.get("company_id"))
    approved = get_approved_peer_set(anchor_id, path)
    if approved:
        ids = set(approved["members"]) | {anchor_id}
        peers = _dedupe_issuers(latest[latest["company_id"].isin(ids)].copy(), anchor_id)
        valid = len(peers) - 1  # exclude anchor
        warning = None
        if valid < MIN_VALID_PEERS:
            warning = (f"Peer set has fewer than {MIN_VALID_PEERS} valid comps; "
                       f"results should be treated as directional.")
        return PeerResolution(peers=peers, source=str(approved["source"]),
                              reviewed=bool(approved.get("reviewed", True)),
                              warning=warning, set_name=str(approved["name"]))

    group_col = "peer_group" if "peer_group" in latest.columns else "sector"
    group = row.get(group_col)
    same_group = latest[latest[group_col] == group]
    if len(same_group) - 1 >= MIN_VALID_PEERS - 1 and len(same_group) >= 3:
        return PeerResolution(peers=_dedupe_issuers(same_group.copy(), anchor_id), source="peer_group", reviewed=False,
                              set_name=str(group))

    return PeerResolution(
        peers=_dedupe_issuers(latest.copy(), anchor_id), source="universe", reviewed=False,
        warning=("No approved peer set and the mapped peer group has fewer than "
                 f"{MIN_VALID_PEERS} comps - benchmarking against the FULL universe. "
                 "Treat all peer statistics as directional."),
        set_name="full universe",
    )


# --- review actions -------------------------------------------------------------------------

def approve_peer_set(anchor_company_id: str, reviewer_note: str = "",
                     path: Path | None = None) -> bool:
    """Mark the anchor's current set as analyst-approved (explicit action only)."""
    sets_path = path if path is not None else PEER_SETS_PATH
    sets = load_peer_sets(sets_path)
    mask = sets["anchor_company_id"] == anchor_company_id
    if not mask.any():
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets.loc[mask, "reviewed_by_user"] = True
    sets.loc[mask, "reviewed_at"] = now
    sets.loc[mask, "updated_at"] = now
    if reviewer_note:
        sets.loc[mask, "reviewer_note"] = reviewer_note
    status_all = sets["inclusion_status"].astype(str).str.lower()
    sets.loc[mask & (status_all != "rejected"), "inclusion_status"] = "approved"
    sets.to_csv(sets_path, index=False)
    return True


def reject_peers(anchor_company_id: str, peer_ids: list[str],
                 path: Path | None = None) -> int:
    """Mark specific members rejected (kept in the file for audit, excluded from
    analytics). Returns the number of rows updated."""
    sets_path = path if path is not None else PEER_SETS_PATH
    sets = load_peer_sets(sets_path)
    mask = (sets["anchor_company_id"] == anchor_company_id) & \
           (sets["peer_company_id"].isin(peer_ids))
    n = int(mask.sum())
    if n:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sets.loc[mask, "inclusion_status"] = "rejected"
        sets.loc[mask, "updated_at"] = now
        sets.to_csv(sets_path, index=False)
    return n


def reset_to_generated(anchor_company_id: str, latest: pd.DataFrame,
                       threshold: float = 55.0, top_n: int = 8,
                       path: Path | None = None,
                       log_path: Path | None = None) -> bool:
    """Drop the anchor's saved set and regenerate the scored suggestion for it
    only (other anchors' sets are untouched)."""
    sets_path = path if path is not None else PEER_SETS_PATH
    sets = load_peer_sets(sets_path)
    sets = sets[sets["anchor_company_id"] != anchor_company_id]
    sets.to_csv(sets_path, index=False)

    sugg = suggest_peers(latest, anchor_company_id, top_n=12)
    eligible = sugg[sugg["reasons"].str.contains("same peer group|same CapIQ industry",
                                                 regex=True, na=False)]
    picked = eligible[eligible["score"] >= threshold].head(top_n)
    if len(picked) < MIN_VALID_PEERS:
        return False               # taxonomy fallback applies
    anchor_rows = latest[latest["company_id"] == anchor_company_id]
    ticker = str(anchor_rows["ticker"].iloc[0]).replace(".SA", "") if not anchor_rows.empty \
        else anchor_company_id
    members = [{"company_id": s["company_id"], "score": s["score"], "rationale": s["reasons"]}
               for _, s in picked.iterrows()]
    save_peer_set(anchor_company_id, f"{ticker} scored comps", members,
                  source="fallback", reviewed_by_user=False, path=sets_path)
    log_suggestions(anchor_company_id, sugg, list(picked["company_id"]),
                    path=log_path if log_path is not None else SUGGESTIONS_LOG_PATH)
    return True


# --- batch generation ---------------------------------------------------------------------

def generate_peer_sets_for_all(
    latest: pd.DataFrame,
    threshold: float = 55.0,
    top_n: int = 8,
    path: Path | None = None,
    log_path: Path | None = None,
) -> pd.DataFrame:
    """Generate a scored peer set for every company in the universe.

    Sets are saved with ``reviewed_by_user=False`` (labeled "Not reviewed" in
    the UI until the analyst approves them in the peer editor). Anchors that
    already have an analyst-reviewed set are left untouched. Anchors where
    fewer than MIN_VALID_PEERS candidates clear the threshold are skipped -
    the static peer-group mapping remains their fallback.
    """
    sets_path = path if path is not None else PEER_SETS_PATH
    audit_path = log_path if log_path is not None else SUGGESTIONS_LOG_PATH
    outcomes = []
    for anchor_id in list(latest["company_id"].unique()):
        existing = get_approved_peer_set(anchor_id, sets_path)
        if existing and existing.get("reviewed"):
            outcomes.append({"company_id": anchor_id, "outcome": "kept analyst-reviewed set",
                             "members": len(existing["members"])})
            continue
        sugg = suggest_peers(latest, anchor_id, top_n=12)
        # Comps discipline: generic similarity (size/margin/country) is not
        # enough - a batch-generated comp must share the peer group or the
        # CapIQ primary industry with the anchor.
        eligible = sugg[sugg["reasons"].str.contains("same peer group|same CapIQ industry",
                                                     regex=True, na=False)]
        picked = eligible[eligible["score"] >= threshold].head(top_n)
        if len(picked) < MIN_VALID_PEERS:
            # Drop any stale unreviewed set so the peer-group fallback applies.
            if existing and not existing.get("reviewed"):
                stale = load_peer_sets(sets_path)
                stale = stale[stale["anchor_company_id"] != anchor_id]
                stale.to_csv(sets_path, index=False)
            outcomes.append({"company_id": anchor_id, "outcome": "skipped (thin candidates)",
                             "members": len(picked)})
            continue
        ticker = str(latest.loc[latest["company_id"] == anchor_id, "ticker"].iloc[0]).replace(".SA", "")
        members = [{"company_id": s["company_id"], "score": s["score"], "rationale": s["reasons"]}
                   for _, s in picked.iterrows()]
        save_peer_set(anchor_id, f"{ticker} scored comps", members, source="fallback",
                      reviewed_by_user=False, path=sets_path)
        log_suggestions(anchor_id, sugg, list(picked["company_id"]), path=audit_path)
        outcomes.append({"company_id": anchor_id, "outcome": "generated (unreviewed)",
                         "members": len(members)})
    return pd.DataFrame(outcomes)
