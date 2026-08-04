"""Business-model-aware operating drivers for revenue underwriting.

The valuation engine has three honest levels of detail:

* Tier 3 - physical drivers sourced from Capital IQ/Excel and issuer filings;
* Tier 2 - reported business/geographic segments from Capital IQ;
* Tier 1 - consolidated revenue growth when no deeper operating KPI exists.

Missing KPIs never receive synthetic values. A profile tells the reviewer
which data is required and the valuation continues on the best available tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DriverProfile:
    model_id: str
    label: str
    equation: str
    primary_metrics: tuple[str, ...]
    supporting_metrics: tuple[str, ...] = ()


@dataclass
class OperatingDriverBuild:
    company_id: str
    profile: DriverProfile
    tier: int
    tier_label: str
    status: str
    segments: list[dict] | None = None
    historical: pd.DataFrame = field(default_factory=pd.DataFrame)
    projection: pd.DataFrame = field(default_factory=pd.DataFrame)
    segment_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    sources: pd.DataFrame = field(default_factory=pd.DataFrame)
    reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)
    available_metrics: list[str] = field(default_factory=list)
    missing_metrics: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    model_inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def coverage_pct(self) -> float:
        required = len(self.profile.primary_metrics)
        if required == 0:
            return 1.0
        return (required - len(self.missing_metrics)) / required


PROFILES = {
    "retail_rollout": DriverProfile(
        "retail_rollout",
        "Store rollout and productivity",
        "Revenue = average stores x revenue per store; same-store sales and maturation are cross-checks",
        ("store_count_total", "revenue_store_channel"),
        ("comparable_sales_growth", "sales_per_square_foot", "net_store_additions"),
    ),
    "retail_omnichannel": DriverProfile(
        "retail_omnichannel",
        "Omnichannel consumer brand",
        "Revenue = average stores x store productivity + e-commerce revenue + other-channel revenue",
        (
            "store_count_total",
            "revenue_store_channel",
            "revenue_ecommerce",
            "revenue_other_channels",
        ),
        (
            "comparable_sales_growth",
            "sales_per_square_foot",
            "comparable_sales_growth_americas",
            "comparable_sales_growth_china",
            "comparable_sales_growth_rest_of_world",
        ),
    ),
    "fitness_membership": DriverProfile(
        "fitness_membership",
        "Membership rollout",
        "Revenue = clubs x members per club x revenue per member",
        ("club_count", "member_count", "revenue_per_member"),
        ("same_club_sales_growth", "churn_rate", "mature_club_margin"),
    ),
    "fleet_assets": DriverProfile(
        "fleet_assets",
        "Fleet capacity and utilization",
        "Revenue = productive fleet x utilization x revenue per productive asset",
        ("fleet_size", "fleet_utilization", "revenue_per_vehicle"),
        ("fleet_additions", "average_asset_age", "residual_value"),
    ),
    "project_services": DriverProfile(
        "project_services",
        "Backlog conversion",
        "Revenue = opening backlog x conversion + in-year awards + recurring services",
        ("backlog", "backlog_conversion", "new_orders"),
        ("book_to_bill", "recurring_revenue_share", "headcount"),
    ),
    "software_subscription": DriverProfile(
        "software_subscription",
        "Subscription and usage",
        "Revenue = customers x recurring revenue per customer + services/usage revenue",
        ("customer_count", "revenue_per_customer", "recurring_revenue_share"),
        ("net_revenue_retention", "remaining_performance_obligations", "churn_rate"),
    ),
    "semiconductor": DriverProfile(
        "semiconductor",
        "Volume, capacity and mix",
        "Revenue = shipments x ASP/mix, reconciled to reported product segments",
        ("shipment_volume", "average_selling_price"),
        ("utilization_rate", "capacity", "data_center_revenue"),
    ),
    "equipment_backlog": DriverProfile(
        "equipment_backlog",
        "Backlog and service attach",
        "Revenue = backlog conversion + new equipment deliveries + service revenue",
        ("backlog", "backlog_conversion", "service_revenue"),
        ("orders", "book_to_bill", "installed_base"),
    ),
    "digital_advertising": DriverProfile(
        "digital_advertising",
        "Traffic and monetization",
        "Revenue = monetized volume x revenue per monetized unit + cloud/subscription segments",
        ("monetized_volume", "revenue_per_monetized_unit"),
        ("cloud_revenue", "paid_clicks", "cost_per_click"),
    ),
    "payments": DriverProfile(
        "payments",
        "Payments volume and take rate",
        "Revenue = payment volume x take rate + credit and value-added services",
        ("total_payment_volume", "take_rate"),
        ("active_accounts", "transactions_per_account", "transaction_margin"),
    ),
    "pharma": DriverProfile(
        "pharma",
        "Product portfolio and loss of exclusivity",
        "Revenue = product volume x net price/mix + launches - loss-of-exclusivity erosion",
        ("product_volume", "net_price_mix"),
        ("key_product_revenue", "pipeline_launches", "loss_of_exclusivity_revenue"),
    ),
    "consumer_lender": DriverProfile(
        "consumer_lender",
        "Loan book and credit economics",
        "Net revenue = average loans x yield + fees; earnings deduct funding cost and credit losses",
        ("average_loans", "loan_yield"),
        ("net_interest_margin", "net_charge_off_rate", "loan_growth"),
    ),
}


# Explicit coverage prevents a generic sector string from silently choosing an
# unsuitable equation. Every current watchlist name is intentionally mapped.
COMPANY_PROFILE = {
    "BOVESPA:GMAT3": "retail_rollout",
    "BOVESPA:TOTS3": "software_subscription",
    "BOVESPA:SMFT3": "fitness_membership",
    "BOVESPA:ASAI3": "retail_rollout",
    "BOVESPA:VAMO3": "fleet_assets",
    "BOVESPA:PRNR3": "project_services",
    "NASDAQ:LULU": "retail_omnichannel",
    "NYSE:NKE": "retail_omnichannel",
    "NYSE:DECK": "retail_omnichannel",
    "NYSE:ONON": "retail_omnichannel",
    "NASDAQ:CROX": "retail_omnichannel",
    "NASDAQ:NVDA": "semiconductor",
    "NASDAQ:AVGO": "semiconductor",
    "NYSE:TSM": "semiconductor",
    "NASDAQ:ASML": "equipment_backlog",
    "NASDAQ:AMD": "semiconductor",
    "NYSE:VRT": "equipment_backlog",
    "NASDAQ:MSFT": "software_subscription",
    "NASDAQ:GOOGL": "digital_advertising",
    "NASDAQ:ADBE": "software_subscription",
    "NASDAQ:PLTR": "software_subscription",
    "NYSE:CRM": "software_subscription",
    "NYSE:NOW": "software_subscription",
    "NASDAQ:PYPL": "payments",
    "NYSE:PFE": "pharma",
    "NASDAQ:SLM": "consumer_lender",
}


def profile_for(company_id: str) -> DriverProfile:
    return PROFILES[COMPANY_PROFILE.get(str(company_id), "software_subscription")]


def operating_driver_payload(build: OperatingDriverBuild | None) -> dict | None:
    """Stable, JSON-ready fingerprint of the revenue build used by valuation."""
    if build is None:
        return None
    projection = build.projection.copy()
    records: list[dict[str, float | int | str | None]] = []
    if not projection.empty:
        keep = [
            column for column in (
                "scenario", "year", "revenue", "revenue_growth",
                "net_store_adds", "average_stores", "ending_stores",
                "stores_rpu_growth", "e_commerce_rpu_growth",
                "other_channels_rpu_growth",
            ) if column in projection.columns
        ]
        projection = projection[keep].sort_values(
            [column for column in ("scenario", "year") if column in keep]
        )
        for row in projection.to_dict("records"):
            records.append({
                key: (
                    None if pd.isna(value) else
                    round(float(value), 10) if isinstance(value, (int, float, np.number)) else
                    str(value)
                )
                for key, value in row.items()
            })
    return {
        "model_id": build.profile.model_id,
        "tier": build.tier,
        "status": build.status,
        "projection": records,
    }


def normalize_operating_kpis(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["company_id"] = out["company_id"].astype(str)
    out["metric_id"] = out["metric_id"].astype(str).str.strip().str.lower()
    out["period"] = pd.to_datetime(out["period"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    if "retrieved_at" in out.columns:
        out["retrieved_at"] = pd.to_datetime(out["retrieved_at"], errors="coerce")
    return out.dropna(subset=["company_id", "period", "metric_id", "value"])


def reconcile_operating_kpis(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare Capital IQ and filing values without overwriting either source."""
    columns = [
        "metric_id", "scope", "period", "capiq_value", "filing_value",
        "difference_pct", "status",
    ]
    if frame.empty or "source_type" not in frame.columns:
        return pd.DataFrame(columns=columns)
    rows: list[dict] = []
    keys = ["metric_id", "scope", "period"]
    for key, group in frame.groupby(keys, dropna=False):
        source = group["source_type"].astype(str).str.lower()
        capiq = group[source.str.contains("capital_iq")]["value"]
        filing = group[source.str.contains("filing")]["value"]
        c_val = float(capiq.iloc[-1]) if not capiq.empty else None
        f_val = float(filing.iloc[-1]) if not filing.empty else None
        if c_val is not None and f_val is not None:
            denominator = max(abs(f_val), 1e-9)
            diff = abs(c_val - f_val) / denominator
            status = "matched" if diff <= 0.01 else "mismatch"
        else:
            diff = None
            status = "single source"
        rows.append({
            "metric_id": key[0], "scope": key[1], "period": key[2],
            "capiq_value": c_val, "filing_value": f_val,
            "difference_pct": diff, "status": status,
        })
    return pd.DataFrame(rows, columns=columns)


def _metric_rows(frame: pd.DataFrame, metric_id: str, *, annual: bool = False) -> pd.DataFrame:
    rows = frame[frame["metric_id"] == metric_id].copy()
    if annual and "period_type" in rows.columns:
        rows = rows[rows["period_type"].astype(str).str.lower() == "annual"]
    # Prefer filing rows for the operating model because filings define the
    # metric. Capital IQ remains the independent reconciliation source.
    if "source_type" in rows.columns:
        rows["_priority"] = rows["source_type"].astype(str).str.lower().map(
            lambda value: 0 if "filing" in value else 1
        )
        rows = rows.sort_values(["period", "_priority"]).drop_duplicates(
            ["period", "metric_id", "scope"], keep="first"
        )
    return rows.sort_values("period")


def _latest_value(frame: pd.DataFrame, metric_id: str, *, annual: bool = False) -> float | None:
    rows = _metric_rows(frame, metric_id, annual=annual)
    return None if rows.empty else float(rows.iloc[-1]["value"])


def _last_growth(frame: pd.DataFrame, metric_id: str) -> float | None:
    rows = _metric_rows(frame, metric_id, annual=True)
    values = rows["value"].astype(float)
    if len(values) < 2 or values.iloc[-2] == 0:
        return None
    return float(values.iloc[-1] / values.iloc[-2] - 1.0)


def _linear(start: float, end: float, horizon: int) -> list[float]:
    if horizon <= 1:
        return [float(end)]
    return [float(value) for value in np.linspace(start, end, horizon)]


def _raw_path(raw: dict, scenario: str, key: str, default: list[float], horizon: int) -> list[float]:
    value = ((raw.get("scenarios") or {}).get(scenario) or {}).get(key)
    if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
        return list(default[:horizon])
    if isinstance(value, (int, float)):
        return [float(value)] * horizon
    if isinstance(value, dict):
        start = float(value.get("start", default[0]))
        end = float(value.get("end", default[-1]))
        return _linear(start, end, horizon)
    values = [float(item) for item in value]
    if not values:
        return list(default[:horizon])
    values.extend([values[-1]] * max(horizon - len(values), 0))
    return values[:horizon]


def _projection_from_segments(segments: list[dict], horizon: int, scenario: str) -> pd.DataFrame:
    states = [
        {
            "name": segment["name"],
            "units": float(segment["units"]),
            "rpu": float(segment["revenue_per_unit"]),
            "adds": segment.get("unit_adds", {}).get(scenario, [0.0] * horizon),
            "growth": segment.get("rpu_growth", {}).get(scenario, [0.0] * horizon),
        }
        for segment in segments
    ]
    rows: list[dict] = []
    prior_total = sum(item["units"] * item["rpu"] for item in states)
    for year in range(horizon):
        row: dict[str, float | int | str] = {"scenario": scenario, "year": year + 1}
        total = 0.0
        for item in states:
            adds = float(item["adds"][year])
            growth = float(item["growth"][year])
            item["units"] += adds
            item["rpu"] *= 1.0 + growth
            revenue = item["units"] * item["rpu"]
            slug = str(item["name"]).lower().replace(" ", "_").replace("-", "_")
            row[f"{slug}_units"] = item["units"]
            row[f"{slug}_unit_adds"] = adds
            row[f"{slug}_rpu_growth"] = growth
            row[f"{slug}_revenue"] = revenue
            total += revenue
        row["revenue"] = total
        row["revenue_growth"] = total / prior_total - 1.0 if prior_total else np.nan
        prior_total = total
        rows.append(row)
    return pd.DataFrame(rows)


def _retail_omnichannel_build(
    company_id: str,
    profile: DriverProfile,
    kpis: pd.DataFrame,
    revenue_ttm: float,
    scenario_growth: dict[str, list[float]],
    raw: dict,
    horizon: int,
) -> OperatingDriverBuild | None:
    store_count = _latest_value(kpis, "store_count_total")
    store_revenue = _latest_value(kpis, "revenue_store_channel", annual=True)
    ecommerce = _latest_value(kpis, "revenue_ecommerce", annual=True)
    other = _latest_value(kpis, "revenue_other_channels", annual=True)
    if any(value is None or value <= 0 for value in (store_count, store_revenue, ecommerce, other)):
        return None

    source_total = float(store_revenue + ecommerce + other)
    scale = float(revenue_ttm) / source_total
    initial = {
        "Stores": float(store_revenue) * scale,
        "E-commerce": float(ecommerce) * scale,
        "Other channels": float(other) * scale,
    }

    counts = _metric_rows(kpis, "store_count_total", annual=True)
    count_values = counts["value"].astype(float).tolist()
    historical_adds = (
        float(count_values[-1] - count_values[-2]) if len(count_values) >= 2 else 0.0
    )
    historical_adds = max(historical_adds, 0.0)

    store_rows = _metric_rows(kpis, "revenue_store_channel", annual=True)
    store_rpu_growth = None
    if len(store_rows) >= 2 and len(count_values) >= 3:
        prior_avg = (count_values[-3] + count_values[-2]) / 2.0
        current_avg = (count_values[-2] + count_values[-1]) / 2.0
        if prior_avg > 0 and current_avg > 0:
            prior_rpu = float(store_rows.iloc[-2]["value"]) / prior_avg
            current_rpu = float(store_rows.iloc[-1]["value"]) / current_avg
            if prior_rpu > 0:
                store_rpu_growth = current_rpu / prior_rpu - 1.0
    store_rpu_growth = float(np.clip(store_rpu_growth or 0.0, -0.20, 0.20))
    ecom_growth = float(np.clip(_last_growth(kpis, "revenue_ecommerce") or 0.0, -0.30, 0.40))
    other_growth = float(np.clip(_last_growth(kpis, "revenue_other_channels") or 0.0, -0.30, 0.40))

    manual = bool(raw.get("scenarios")) and not bool(raw.get("calibrate_to_consolidated", False))
    segment_paths: dict[str, dict[str, list[float]]] = {}
    for scenario in ("bear", "base", "bull"):
        targets = list(scenario_growth[scenario][:horizon])
        terminal = float(targets[-1])
        shift = {"bear": -0.025, "base": 0.0, "bull": 0.025}[scenario]
        add_factor = {"bear": 0.60, "base": 1.00, "bull": 1.30}[scenario]
        adds_default = [round(historical_adds * add_factor, 1)] * horizon
        store_default = _linear(store_rpu_growth + shift, terminal, horizon)
        ecom_default = _linear(ecom_growth + shift, terminal + 0.005, horizon)
        other_default = _linear(other_growth + shift, terminal, horizon)

        adds = _raw_path(raw, scenario, "net_store_adds", adds_default, horizon)
        store_growth = _raw_path(raw, scenario, "store_productivity_growth", store_default, horizon)
        ecom_path = _raw_path(raw, scenario, "ecommerce_growth", ecom_default, horizon)
        other_path = _raw_path(raw, scenario, "other_growth", other_default, horizon)

        scenario_raw = ((raw.get("scenarios") or {}).get(scenario) or {})
        supplied_lengths = [
            len(value)
            for key in (
                "net_store_adds", "store_productivity_growth",
                "ecommerce_growth", "other_growth",
            )
            if isinstance((value := scenario_raw.get(key)), (list, tuple))
        ]
        explicit_driver_years = min(max(supplied_lengths, default=horizon), horizon)
        calibrate_transition_tail = manual and explicit_driver_years < horizon

        if not manual or calibrate_transition_tail:
            # Automatic driver paths are reconciled to the approved consolidated
            # growth case. For a manual case, only forecast years beyond the
            # explicitly supplied driver path are reconciled; this preserves the
            # underwritten build and lets the DCF transition converge to the
            # terminal growth rate instead of repeating the final manual year.
            ending_units = float(store_count)
            average_units = float(store_count)
            levels = dict(initial)
            calibrated_store: list[float] = []
            calibrated_ecom: list[float] = []
            calibrated_other: list[float] = []
            total = sum(levels.values())
            for year in range(horizon):
                ending_units_new = ending_units + adds[year]
                average_units_new = (ending_units + ending_units_new) / 2.0
                provisional_store = levels["Stores"] * (average_units_new / average_units) * (1.0 + store_growth[year])
                provisional_ecom = levels["E-commerce"] * (1.0 + ecom_path[year])
                provisional_other = levels["Other channels"] * (1.0 + other_path[year])
                desired = total * (1.0 + targets[year])
                should_reconcile = not manual or year >= explicit_driver_years
                factor = (
                    desired / (provisional_store + provisional_ecom + provisional_other)
                    if should_reconcile else 1.0
                )
                calibrated_store.append((1.0 + store_growth[year]) * factor - 1.0)
                calibrated_ecom.append((1.0 + ecom_path[year]) * factor - 1.0)
                calibrated_other.append((1.0 + other_path[year]) * factor - 1.0)
                levels = {
                    "Stores": provisional_store * factor,
                    "E-commerce": provisional_ecom * factor,
                    "Other channels": provisional_other * factor,
                }
                total = sum(levels.values())
                ending_units = ending_units_new
                average_units = average_units_new
            store_growth, ecom_path, other_path = calibrated_store, calibrated_ecom, calibrated_other

        segment_paths[scenario] = {
            "net_store_adds": adds,
            "store_productivity_growth": store_growth,
            "ecommerce_growth": ecom_path,
            "other_growth": other_path,
            "explicit_driver_years": explicit_driver_years,
        }

    def average_store_additions(net_adds: list[float]) -> list[float]:
        # Revenue is earned on average stores, not period-end stores. The first
        # year receives half of in-year openings; subsequent years receive half
        # of the prior and current year's additions.
        return [net_adds[0] / 2.0] + [
            (net_adds[index - 1] + net_adds[index]) / 2.0
            for index in range(1, len(net_adds))
        ]

    segments = [
        {
            "name": "Stores",
            "units": float(store_count),
            "revenue_per_unit": initial["Stores"] / float(store_count),
            "unit_adds": {
                name: average_store_additions(values["net_store_adds"])
                for name, values in segment_paths.items()
            },
            "rpu_growth": {name: values["store_productivity_growth"] for name, values in segment_paths.items()},
            "source": "operating KPIs: stores x revenue/store",
        },
        {
            "name": "E-commerce",
            "units": 1.0,
            "revenue_per_unit": initial["E-commerce"],
            "unit_adds": {name: [0.0] * horizon for name in segment_paths},
            "rpu_growth": {name: values["ecommerce_growth"] for name, values in segment_paths.items()},
            "source": "operating KPI: e-commerce channel revenue",
        },
        {
            "name": "Other channels",
            "units": 1.0,
            "revenue_per_unit": initial["Other channels"],
            "unit_adds": {name: [0.0] * horizon for name in segment_paths},
            "rpu_growth": {name: values["other_growth"] for name, values in segment_paths.items()},
            "source": "operating KPI: other-channel revenue",
        },
    ]
    projection = pd.concat(
        [_projection_from_segments(segments, horizon, scenario) for scenario in ("bear", "base", "bull")],
        ignore_index=True,
    )
    for scenario, values in segment_paths.items():
        mask = projection["scenario"] == scenario
        additions = values["net_store_adds"]
        projection.loc[mask, "net_store_adds"] = additions
        projection.loc[mask, "ending_stores"] = (
            float(store_count) + np.cumsum(additions)
        )
        projection.loc[mask, "average_stores"] = projection.loc[mask, "stores_units"].to_numpy()
    historical_metrics = list(profile.primary_metrics + profile.supporting_metrics)
    historical = kpis[kpis["metric_id"].isin(historical_metrics)].copy()
    sources = kpis[[
        column for column in (
            "source_type", "source_name", "source_url", "filing_form",
            "retrieved_at", "definition",
        ) if column in kpis.columns
    ]].drop_duplicates()
    notes = [
        f"Annual channel revenue scaled {scale:.3f}x to reconcile with the Capital IQ LTM revenue anchor.",
        (
            "Manual physical-driver paths are the revenue source used by the DCF; "
            "the top-down growth scenario is used only to converge any additional "
            "transition years to the terminal rate."
            if manual else
            "Automatic physical-driver paths preserve the reviewed consolidated "
            "scenario unless manual driver overrides are saved."
        ),
        "Store productivity uses average beginning/end store count where two annual observations are available.",
    ]
    return OperatingDriverBuild(
        company_id=company_id,
        profile=profile,
        tier=3,
        tier_label="Tier 3 | Physical driver build",
        status="manual driver case" if manual else "source-anchored and reconciled",
        segments=segments,
        historical=historical,
        projection=projection,
        sources=sources,
        reconciliation=reconcile_operating_kpis(kpis),
        available_metrics=sorted(kpis["metric_id"].unique().tolist()),
        missing_metrics=[],
        notes=notes,
        model_inputs={
            "latest_store_count": float(store_count),
            "historical_net_adds": historical_adds,
            "historical_store_productivity_growth": store_rpu_growth,
            "historical_ecommerce_growth": ecom_growth,
            "historical_other_growth": other_growth,
            "scenario_paths": segment_paths,
            "annual_channel_total": source_total,
            "ltm_revenue_anchor": float(revenue_ttm),
            "scale_to_ltm": scale,
        },
    )


def build_operating_driver_model(
    row: pd.Series,
    operating_kpis: pd.DataFrame | None,
    company_segments: pd.DataFrame | None,
    scenario_growth: dict[str, list[float]],
    raw: dict | None,
    horizon: int,
) -> OperatingDriverBuild:
    company_id = str(row.get("company_id"))
    profile = profile_for(company_id)
    kpis = normalize_operating_kpis(operating_kpis)
    if not kpis.empty:
        kpis = kpis[kpis["company_id"] == company_id].copy()
    available = sorted(kpis["metric_id"].unique().tolist()) if not kpis.empty else []
    missing = [metric for metric in profile.primary_metrics if metric not in available]
    revenue_ttm = float(row.get("revenue_ttm")) if pd.notna(row.get("revenue_ttm")) else 0.0

    if profile.model_id == "retail_omnichannel" and not missing and revenue_ttm > 0:
        physical = _retail_omnichannel_build(
            company_id, profile, kpis, revenue_ttm, scenario_growth, raw or {}, horizon
        )
        if physical is not None:
            return physical

    segments = company_segments.copy() if company_segments is not None else pd.DataFrame()
    if not segments.empty and "company_id" in segments.columns:
        segments = segments[segments["company_id"].astype(str) == company_id].copy()
        segments["revenue_usd"] = pd.to_numeric(segments.get("revenue_usd"), errors="coerce")
        segments = segments[segments["revenue_usd"] > 0]
    if len(segments) >= 2:
        tier, label, status = 2, "Tier 2 | Reported segment build", "segment fallback"
        notes = [
            "Capital IQ business/geographic segments explain mix and relative growth.",
            "Physical KPI coverage is incomplete; the required metrics are shown for the next Excel refresh.",
        ]
    else:
        tier, label, status = 1, "Tier 1 | Consolidated growth", "consolidated fallback"
        notes = [
            "No complete physical-driver set or multi-segment disclosure is loaded.",
            "The DCF remains usable on reviewed consolidated growth, while driver coverage is explicitly pending.",
        ]
    return OperatingDriverBuild(
        company_id=company_id,
        profile=profile,
        tier=tier,
        tier_label=label,
        status=status,
        historical=kpis,
        segment_history=segments,
        sources=(kpis[[column for column in (
            "source_type", "source_name", "source_url", "filing_form", "retrieved_at", "definition"
        ) if column in kpis.columns]].drop_duplicates() if not kpis.empty else pd.DataFrame()),
        reconciliation=reconcile_operating_kpis(kpis),
        available_metrics=available,
        missing_metrics=missing,
        notes=notes,
    )
