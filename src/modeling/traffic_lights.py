from __future__ import annotations

import pandas as pd

from src.modeling.thresholds import (
    DEFAULT_THRESHOLDS,
    all_signal_metrics,
    not_meaningful_for,
    thresholds_for,
)


def classify_signal(value: float, rule: dict[str, float | str]) -> str:
    if pd.isna(value):
        return "n/a"

    direction = rule["direction"]
    green = float(rule["green"])
    yellow = float(rule["yellow"])

    if direction == "higher":
        if value >= green:
            return "green"
        if value >= yellow:
            return "yellow"
        return "red"

    if value <= green:
        return "green"
    if value <= yellow:
        return "yellow"
    return "red"


def add_traffic_lights(df: pd.DataFrame, thresholds: dict | None = None) -> pd.DataFrame:
    """Attach ``<metric>_signal`` columns, profiled by ``business_model``.

    Signals are ``green`` / ``yellow`` / ``red`` where a threshold applies,
    ``n/m`` where the metric is not meaningful for the business model (e.g.
    EV/EBITDA for a lender), and ``n/a`` where the value is missing.

    Passing an explicit ``thresholds`` dict applies it to every row (legacy
    behaviour, used by tests and custom callers).
    """
    out = df.copy()

    if thresholds is not None:
        for metric, rule in thresholds.items():
            if metric in out.columns:
                out[f"{metric}_signal"] = out[metric].apply(lambda value: classify_signal(value, rule))
        return out

    business_model = (
        out["business_model"].astype(str).str.lower()
        if "business_model" in out.columns
        else pd.Series("operating", index=out.index)
    )

    for metric in all_signal_metrics():
        if metric in out.columns:
            out[f"{metric}_signal"] = "n/a"

    for model in business_model.unique():
        mask = business_model == model
        rules = thresholds_for(model) if model != "operating" else DEFAULT_THRESHOLDS
        for metric, rule in rules.items():
            if metric in out.columns:
                out.loc[mask, f"{metric}_signal"] = out.loc[mask, metric].apply(
                    lambda value: classify_signal(value, rule)
                )
        for metric in not_meaningful_for(model):
            if f"{metric}_signal" in out.columns:
                out.loc[mask, f"{metric}_signal"] = "n/m"

    return out
