"""Company classification: peer groups, business models, and thesis themes.

A thesis theme is *why a name is on the watchlist* ("Consumer Brand
Turnaround", "AI Capex Cycle"). A peer group is *what the name trades against* (true comps).
The two were previously conflated in the ``sector`` column, which made peer
medians and percentiles meaningless for mixed themes.

This module keeps them separate:

- ``theme``           <- the original ``sector`` column, untouched.
- ``peer_group``      <- from the committed reference mapping, else falls back
                         to the theme so small/demo universes keep working.
- ``business_model``  <- ``operating`` | ``financial`` | ``insurer``; drives
                         which metrics are meaningful (an EBITDA framework says
                         nothing about a lender).

The mapping lives in ``data/reference/company_classification.csv`` and contains
tickers only (no licensed data), so it is safe to commit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import DATA_DIR

CLASSIFICATION_PATH = DATA_DIR / "reference" / "company_classification.csv"

BUSINESS_MODELS = ("operating", "financial", "insurer")
DEFAULT_BUSINESS_MODEL = "operating"


def _private_overlay_path() -> Path:
    # Imported lazily to avoid a config import cycle at module load.
    from src.config import PRIVATE_DATA_DIR

    return PRIVATE_DATA_DIR / "company_classification_private.csv"


def load_classification(path: Path = CLASSIFICATION_PATH, overlay_path: Path | None = None) -> pd.DataFrame:
    """Committed reference mapping, with the private overlay winning on conflict.

    Companies added through the Add Company workflow store their peer group /
    business model privately (data_private/company_classification_private.csv)
    so watchlist choices never touch Git-tracked files.
    """
    frames = []
    if path.exists():
        frames.append(pd.read_csv(path))
    overlay = overlay_path if overlay_path is not None else _private_overlay_path()
    if overlay.exists():
        frames.append(pd.read_csv(overlay))
    if not frames:
        return pd.DataFrame(columns=["company_id", "peer_group", "business_model"])

    df = pd.concat(frames, ignore_index=True)
    # Overlay rows come last -> keep='last' makes private choices win.
    df = df.drop_duplicates(subset="company_id", keep="last")
    df["business_model"] = (
        df["business_model"].astype(str).str.strip().str.lower()
        .where(lambda s: s.isin(BUSINESS_MODELS), DEFAULT_BUSINESS_MODEL)
    )
    keep = ["company_id", "peer_group", "business_model"]
    if "coverage_role" in df.columns:
        df["coverage_role"] = (
            df["coverage_role"].astype(str).str.strip().str.lower()
            .where(lambda s: s.isin(("watchlist", "comparable")), pd.NA)
        )
        keep.append("coverage_role")
    return df[keep]


def _watchlist_ids() -> set[str]:
    """Private universe defines thesis names; exported extras are comparables.

    Public/demo datasets do not depend on this file, so callers only apply the
    role inference to private Capital IQ exports.
    """
    from src.config import PRIVATE_DATA_DIR

    path = PRIVATE_DATA_DIR / "universe.csv"
    if not path.exists():
        return set()
    try:
        universe = pd.read_csv(path)
    except Exception:
        return set()
    if "id" not in universe.columns:
        return set()
    return set(universe["id"].dropna().astype(str))


def apply_classification(companies: pd.DataFrame, path: Path = CLASSIFICATION_PATH) -> pd.DataFrame:
    """Add ``theme``, ``peer_group``, ``business_model`` to a companies frame.

    Existing values (e.g. supplied directly by a loader or a test) are kept;
    the reference mapping only fills the gaps, and the theme (former sector)
    is the final fallback for the peer group.
    """
    out = companies.copy()
    out["theme"] = out.get("theme", out.get("sector"))

    mapping = load_classification(path)
    if not mapping.empty:
        rename = {"peer_group": "_pg_ref", "business_model": "_bm_ref"}
        if "coverage_role" in mapping.columns:
            rename["coverage_role"] = "_role_ref"
        out = out.merge(
            mapping.rename(columns=rename),
            on="company_id",
            how="left",
        )
    else:
        out["_pg_ref"] = pd.NA
        out["_bm_ref"] = pd.NA
        out["_role_ref"] = pd.NA
    if "_role_ref" not in out.columns:
        out["_role_ref"] = pd.NA

    existing_pg = out["peer_group"] if "peer_group" in out.columns else pd.Series(pd.NA, index=out.index, dtype="object")
    existing_bm = out["business_model"] if "business_model" in out.columns else pd.Series(pd.NA, index=out.index, dtype="object")
    existing_role = out["coverage_role"] if "coverage_role" in out.columns else pd.Series(pd.NA, index=out.index, dtype="object")

    out["peer_group"] = (
        existing_pg.astype("object").combine_first(out["_pg_ref"]).combine_first(out["theme"])
    )
    out["business_model"] = (
        existing_bm.astype("object").combine_first(out["_bm_ref"]).fillna(DEFAULT_BUSINESS_MODEL)
    )
    inferred_role = pd.Series("watchlist", index=out.index, dtype="object")
    is_private_capiq = out.get("company_source", pd.Series("", index=out.index)).astype(str).str.contains(
        "Capital IQ", case=False, na=False
    )
    watchlist_ids = _watchlist_ids()
    if watchlist_ids:
        inferred_role = inferred_role.where(
            ~is_private_capiq | out["company_id"].astype(str).isin(watchlist_ids),
            "comparable",
        )
    out["coverage_role"] = (
        existing_role.astype("object")
        .combine_first(out["_role_ref"])
        .combine_first(inferred_role)
        .fillna("watchlist")
    )
    out["coverage_role"] = (
        out["coverage_role"].astype(str).str.strip().str.lower()
        .where(lambda s: s.isin(("watchlist", "comparable")), "watchlist")
    )
    return out.drop(columns=["_pg_ref", "_bm_ref", "_role_ref"])
