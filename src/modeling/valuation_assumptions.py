"""Valuation assumptions layer.

Every DCF input is either **anchored** (derived from the company's own TTM
data) or **analyst** (set in a per-company YAML). Nothing is invented: the
case appendix can label every number with its origin.

Glidepath specs accepted anywhere a per-year series is needed:

- ``"auto"`` / ``None``      -> the anchor value, flat
- scalar ``0.10``            -> flat at that value
- list ``[0.12, 0.10, ...]`` -> as given (padded with the last value)
- ``{start: x|auto, end: y}``-> linear fade from start to end over the horizon

Private files live in ``data_private/assumptions/<company_id>.yaml`` (colon
replaced by underscore, same convention as theses); the public demo ships
samples under ``data/sample/assumptions/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.config import DATA_DIR

WACC_PARAMS_PATH = DATA_DIR / "reference" / "wacc_params.csv"

SCENARIO_NAMES = ("bear", "base", "bull")

# Bounds used when anchoring growth on a single noisy TTM reading.
GROWTH_ANCHOR_CLIP = (-0.05, 0.25)


# --- reference parameters -----------------------------------------------------

def load_wacc_params(currency: str, path: Path = WACC_PARAMS_PATH) -> dict:
    """Rate environment for a currency; USD row is the fallback."""
    defaults = {
        "risk_free_rate": 0.043,
        "equity_risk_premium": 0.045,
        "country_risk_premium": 0.0,
        "tax_rate": 0.25,
        "default_perpetuity_growth": 0.025,
        "source_note": "built-in defaults",
    }
    if not path.exists():
        return defaults
    df = pd.read_csv(path)
    row = df[df["currency"].str.upper() == str(currency).upper()]
    if row.empty:
        row = df[df["currency"].str.upper() == "USD"]
    if row.empty:
        return defaults
    r = row.iloc[0]
    return {
        "risk_free_rate": float(r["risk_free_rate"]),
        "equity_risk_premium": float(r["equity_risk_premium"]),
        "country_risk_premium": float(r["country_risk_premium"]),
        "tax_rate": float(r["tax_rate"]),
        "default_perpetuity_growth": float(r["default_perpetuity_growth"]),
        "source_note": str(r.get("source_note", "")),
    }


# --- glidepaths ----------------------------------------------------------------

def resolve_glidepath(spec, horizon: int, anchor: float | None) -> list[float]:
    """Turn a YAML glidepath spec into a per-year list of length ``horizon``."""
    def _num(value, fallback):
        if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
            return fallback
        return float(value)

    if spec is None or (isinstance(spec, str) and spec.strip().lower() == "auto"):
        base = anchor if anchor is not None else 0.0
        return [float(base)] * horizon
    if isinstance(spec, (int, float)):
        return [float(spec)] * horizon
    if isinstance(spec, list):
        values = [float(v) for v in spec]
        if not values:
            return [anchor if anchor is not None else 0.0] * horizon
        while len(values) < horizon:
            values.append(values[-1])
        return values[:horizon]
    if isinstance(spec, dict):
        start = _num(spec.get("start", "auto"), anchor if anchor is not None else 0.0)
        end = _num(spec.get("end", "auto"), anchor if anchor is not None else start)
        if horizon == 1:
            return [end]
        return list(np.linspace(start, end, horizon))
    raise ValueError(f"Unsupported glidepath spec: {spec!r}")


# --- anchors from the monitoring dataset ----------------------------------------

def _clean(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def derive_anchors(row: pd.Series, params: dict) -> dict:
    """Company-specific defaults derived from TTM data. Every key has a value;
    ``notes`` records fallbacks so the UI/appendix can disclose them."""
    notes: list[str] = []

    # Year-1 growth anchor: NTM consensus is the street's revenue projection -
    # prefer it over trailing growth when both sides of the ratio exist.
    growth = None
    rev_ttm = _clean(row.get("revenue_ttm"))
    rev_ntm = _clean(row.get("revenue_est_ntm"))
    if rev_ttm and rev_ttm > 0 and rev_ntm and rev_ntm > 0:
        growth = rev_ntm / rev_ttm - 1.0
        notes.append(f"year-1 growth anchored to NTM consensus ({growth:+.1%})")
    if growth is None:
        growth = _clean(row.get("revenue_yoy_growth"))
    if growth is None:
        growth = 0.04
        notes.append("revenue growth anchor missing; defaulted to 4%")
    growth = float(np.clip(growth, *GROWTH_ANCHOR_CLIP))

    margin = _clean(row.get("ebitda_margin_ttm"))
    if margin is None or margin <= 0:
        margin = 0.15
        notes.append("EBITDA margin anchor missing/non-positive; defaulted to 15%")

    revenue = _clean(row.get("revenue_ttm"))
    ebitda = _clean(row.get("ebitda_ttm"))
    ebit = _clean(row.get("ebit_ttm"))
    if revenue and ebitda is not None and ebit is not None and revenue > 0:
        d_and_a_pct = max((ebitda - ebit) / revenue, 0.0)
    else:
        d_and_a_pct = 0.03
        notes.append("D&A anchor derived unavailable; defaulted to 3% of revenue")

    capex_pct = _clean(row.get("capex_intensity_ttm"))
    if capex_pct is None or capex_pct < 0:
        capex_pct = 0.04
        notes.append("capex anchor missing; defaulted to 4% of revenue")

    gross_margin = _clean(row.get("gross_margin_ttm"))
    cogs_pct = 1.0 - gross_margin if gross_margin is not None and 0 < gross_margin < 1 else None

    dso, dih, dpo = _clean(row.get("dso")), _clean(row.get("dio")), _clean(row.get("dpo"))
    nwc_pct = None
    wc, rev = _clean(row.get("working_capital")), revenue
    if wc is not None and rev and rev > 0:
        nwc_pct = wc / rev
    days_available = all(v is not None for v in (dso, dih, dpo)) and cogs_pct is not None
    if not days_available:
        if nwc_pct is None:
            nwc_pct = 0.0
            notes.append("no working-capital data; assuming zero NWC change")
        else:
            notes.append("AR/inventory/AP days unavailable; NWC projected as % of revenue")

    return {
        "revenue_growth": growth,
        "ebitda_margin": margin,
        "d_and_a_pct": d_and_a_pct,
        "capex_pct": capex_pct,
        "tax_rate": params["tax_rate"],
        "cogs_pct": cogs_pct,
        "dso": dso,
        "dih": dih,
        "dpo": dpo,
        "nwc_pct_revenue": nwc_pct,
        "nwc_mode": "days" if days_available else "pct",
        "notes": notes,
    }


# --- assumption objects ----------------------------------------------------------

@dataclass
class ScenarioAssumptions:
    name: str
    revenue_growth: list[float]
    ebitda_margin: list[float]
    d_and_a_pct: list[float]
    capex_pct: list[float]
    tax_rate: float
    dso: list[float] | None
    dih: list[float] | None
    dpo: list[float] | None
    nwc_pct_revenue: list[float] | None
    nwc_mode: str                      # "days" | "pct"
    source: str = "derived"            # derived | analyst


VALID_STATUSES = ("final", "draft", "illustrative")


@dataclass
class ValuationAssumptions:
    company_id: str
    horizon_years: int
    scenarios: dict[str, ScenarioAssumptions]
    exit_multiple: float | None        # None -> resolve from peer median at run time
    perpetuity_growth: float
    beta: float | None                 # None -> default at WACC build
    pretax_cost_of_debt: float | None
    wacc_override: float | None
    anchors: dict = field(default_factory=dict)
    path: Path | None = None
    # Disclosure: auto (no file) | illustrative | draft | final.
    status: str = "auto"
    perpetuity_source: str = "anchored"   # analyst | anchored (currency default)
    # Tier-2 operational drivers (units x revenue/unit segment build); None = Tier-1.
    segments: list[dict] | None = None

    @property
    def from_file(self) -> bool:
        return self.path is not None


def _auto_scenario_specs(anchors: dict, perpetuity_growth: float) -> dict:
    """Tier-1 default bear/base/bull driver specs when no YAML exists."""
    g = anchors["revenue_growth"]
    terminal_g = max(perpetuity_growth, 0.02)
    m = anchors["ebitda_margin"]
    return {
        "base": {
            "revenue_growth": {"start": g, "end": terminal_g},
            "ebitda_margin": m,
        },
        "bear": {
            "revenue_growth": {"start": max(g - 0.05, -0.05), "end": max(terminal_g - 0.01, 0.0)},
            "ebitda_margin": max(m - 0.02, 0.01),
        },
        "bull": {
            "revenue_growth": {"start": min(g + 0.05, 0.35), "end": terminal_g + 0.01},
            "ebitda_margin": m + 0.02,
        },
    }


def _build_scenario(name: str, spec: dict, horizon: int, anchors: dict, source: str) -> ScenarioAssumptions:
    spec = spec or {}
    days_mode = anchors["nwc_mode"] == "days"
    tax = spec.get("tax_rate")
    tax = anchors["tax_rate"] if tax is None or (isinstance(tax, str) and tax.lower() == "auto") else float(tax)
    return ScenarioAssumptions(
        name=name,
        revenue_growth=resolve_glidepath(spec.get("revenue_growth"), horizon, anchors["revenue_growth"]),
        ebitda_margin=resolve_glidepath(spec.get("ebitda_margin"), horizon, anchors["ebitda_margin"]),
        d_and_a_pct=resolve_glidepath(spec.get("d_and_a_pct_revenue"), horizon, anchors["d_and_a_pct"]),
        capex_pct=resolve_glidepath(spec.get("capex_pct_revenue"), horizon, anchors["capex_pct"]),
        tax_rate=tax,
        dso=resolve_glidepath(spec.get("dso"), horizon, anchors["dso"]) if days_mode else None,
        dih=resolve_glidepath(spec.get("dih"), horizon, anchors["dih"]) if days_mode else None,
        dpo=resolve_glidepath(spec.get("dpo"), horizon, anchors["dpo"]) if days_mode else None,
        nwc_pct_revenue=(resolve_glidepath(spec.get("nwc_pct_revenue"), horizon, anchors["nwc_pct_revenue"])
                         if not days_mode else None),
        nwc_mode=anchors["nwc_mode"],
        source=source,
    )


def assumptions_filename(company_id: str) -> str:
    return company_id.replace(":", "_") + ".yaml"


def _auto_segments_from_capiq(row: pd.Series, anchors: dict, horizon: int,
                              terminal_g: float, notes: list[str]) -> list[dict] | None:
    """Tier-2 auto drivers from the CapIQ segment extraction.

    Segment revenues on the CIQ page are USD-converted, so absolute levels and
    growth are FX-distorted for non-USD names. Two FX-invariant facts survive:
    the revenue MIX (same FX applies to every segment) and the RELATIVE growth
    between segments. We therefore scale weights onto the local-currency TTM
    revenue and tilt each segment around the company-level growth glidepath.
    """
    from src.config import PRIVATE_CAPIQ_DIR

    path = PRIVATE_CAPIQ_DIR / "company_segments.csv"
    company_id = str(row.get("company_id"))
    revenue_ttm = _clean(row.get("revenue_ttm"))
    if not path.exists() or not revenue_ttm or revenue_ttm <= 0:
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    mine = df[(df["company_id"] == company_id) & (df["revenue_usd"] > 0)]
    # Drop noise segments (<1% of the mix: corporate lines, rounding stubs).
    if not mine.empty:
        mine = mine[mine["revenue_usd"] / mine["revenue_usd"].sum() >= 0.01]
    if len(mine) < 2:
        return None            # single segment adds nothing over Tier-1

    total = float(mine["revenue_usd"].sum())
    g0, tg = anchors["revenue_growth"], max(terminal_g, 0.02)
    cagrs = mine["cagr_3y"].fillna(g0).clip(-0.30, 0.50)
    weights = mine["revenue_usd"] / total
    blended = float((cagrs * weights).sum())

    def path_for(start: float, end: float, tilt: float) -> list[float]:
        n = max(horizon, 2)
        return [round(start + (end - start) * t / (n - 1)
                      + tilt * (1.0 - t / (n - 1)), 6) for t in range(n)]

    segments = []
    for (_, seg), w, cagr in zip(mine.iterrows(), weights, cagrs):
        tilt = float(np.clip(cagr - blended, -0.08, 0.08))
        segments.append({
            "name": str(seg["segment"]),
            "units": 1,
            "revenue_per_unit": float(w) * revenue_ttm,
            "rpu_growth": {
                "bear": path_for(max(g0 - 0.05, -0.05), max(tg - 0.01, 0.0), tilt),
                "base": path_for(g0, tg, tilt),
                "bull": path_for(g0 + 0.05, tg + 0.01, tilt),
            },
            "source": "capiq segments (auto)",
        })
    notes.append(f"revenue built from {len(segments)} CapIQ business segments "
                 f"(mix + relative growth; FY{int(mine['latest_fy'].max())} disclosure)")
    return segments


def load_valuation_assumptions(
    row: pd.Series,
    assumptions_dir: Path | None,
    params: dict | None = None,
) -> ValuationAssumptions:
    """Assumptions for one company: YAML when present, anchored defaults otherwise."""
    company_id = str(row.get("company_id"))
    if params is None:
        params = load_wacc_params(str(row.get("currency", "USD")))
    anchors = derive_anchors(row, params)

    raw, path = {}, None
    if assumptions_dir is not None:
        candidate = Path(assumptions_dir) / assumptions_filename(company_id)
        if candidate.exists():
            try:
                raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                path = candidate
            except yaml.YAMLError:
                raw = {}

    horizon = int(raw.get("horizon_years", 5))
    status_raw = str(raw.get("status", "")).strip().lower()
    if path is None:
        status = "auto"
    elif status_raw in VALID_STATUSES:
        status = status_raw
    else:
        status = "draft"
    terminal = raw.get("terminal") or {}
    pg = terminal.get("perpetuity_growth")
    if pg is None or (isinstance(pg, str) and pg.lower() == "auto"):
        perpetuity_growth, perpetuity_source = params["default_perpetuity_growth"], "anchored"
    else:
        perpetuity_growth, perpetuity_source = float(pg), "analyst"
    em = terminal.get("exit_multiple")
    exit_multiple = None if em is None or (isinstance(em, str) and em.lower() == "auto") else float(em)

    scenario_specs = raw.get("scenarios") or {}
    auto_specs = _auto_scenario_specs(anchors, perpetuity_growth)
    scenarios: dict[str, ScenarioAssumptions] = {}
    for name in SCENARIO_NAMES:
        if name in scenario_specs:
            scenarios[name] = _build_scenario(name, scenario_specs[name], horizon, anchors, "analyst")
        else:
            scenarios[name] = _build_scenario(name, auto_specs[name], horizon, anchors, "derived")

    wacc_raw = raw.get("wacc") or {}

    def _opt(key):
        v = wacc_raw.get(key)
        return None if v is None or (isinstance(v, str) and v.lower() == "auto") else float(v)

    segments = raw.get("segments") or None
    if segments is not None:
        # Minimal validation: every segment needs a unit count and revenue/unit.
        segments = [s for s in segments
                    if isinstance(s, dict) and s.get("units") is not None
                    and s.get("revenue_per_unit") is not None] or None
    if segments is None:
        # Tier-2 auto: CapIQ business-segment mix + relative growth, when extracted.
        segments = _auto_segments_from_capiq(row, anchors, horizon, perpetuity_growth,
                                             anchors.setdefault("notes", []))

    return ValuationAssumptions(
        company_id=company_id,
        horizon_years=horizon,
        scenarios=scenarios,
        exit_multiple=exit_multiple,
        perpetuity_growth=perpetuity_growth,
        beta=_opt("beta"),
        pretax_cost_of_debt=_opt("pretax_cost_of_debt"),
        wacc_override=_opt("wacc_override"),
        anchors=anchors,
        path=path,
        status=status,
        perpetuity_source=perpetuity_source,
        segments=segments,
    )
