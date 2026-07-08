"""Traffic-light thresholds, profiled by business model.

One global threshold set cannot judge this universe: an EBITDA framework is
meaningless for lenders (their debt funds receivables), and managed-care
margins are structurally thin. Each business model therefore gets:

- a rule set (metric -> green/amber cutoffs), and
- a *not meaningful* list: metrics whose signal is reported as ``"n/m"``
  instead of a false green/red.
"""

from __future__ import annotations

# Baseline profile for operating companies.
DEFAULT_THRESHOLDS = {
    "revenue_yoy_growth": {"direction": "higher", "green": 0.10, "yellow": 0.02},
    "gross_margin": {"direction": "higher", "green": 0.45, "yellow": 0.30},
    "ebitda_margin": {"direction": "higher", "green": 0.22, "yellow": 0.12},
    "ebitda_margin_ttm": {"direction": "higher", "green": 0.22, "yellow": 0.12},
    "net_income_margin_ttm": {"direction": "higher", "green": 0.12, "yellow": 0.04},
    "fcf_conversion_ttm": {"direction": "higher", "green": 0.60, "yellow": 0.30},
    "capex_intensity_ttm": {"direction": "lower", "green": 0.06, "yellow": 0.12},
    "net_debt_to_ebitda_ttm": {"direction": "lower", "green": 2.0, "yellow": 3.5},
    "interest_coverage_ttm": {"direction": "higher", "green": 4.0, "yellow": 2.0},
    "ev_to_ebitda_ttm": {"direction": "lower", "green": 10.0, "yellow": 16.0},
    "roic_ttm": {"direction": "higher", "green": 0.15, "yellow": 0.08},
}

# Metrics where the EBITDA / enterprise-value framework says nothing about a
# financial institution's economics.
FINANCIAL_NOT_MEANINGFUL = [
    "gross_margin",
    "ebitda_margin",
    "ebitda_margin_ttm",
    "fcf_conversion_ttm",
    "capex_intensity_ttm",
    "net_debt_to_ebitda_ttm",
    "interest_coverage_ttm",
    "ev_to_ebitda_ttm",
]

PROFILES: dict[str, dict] = {
    "operating": {
        "rules": DEFAULT_THRESHOLDS,
        "not_meaningful": [],
    },
    "financial": {
        # Lenders, banks, brokers: judge growth, bottom-line margin, and P/E.
        "rules": {
            "revenue_yoy_growth": {"direction": "higher", "green": 0.10, "yellow": 0.02},
            "net_income_margin_ttm": {"direction": "higher", "green": 0.15, "yellow": 0.05},
            "pe_ttm": {"direction": "lower", "green": 12.0, "yellow": 20.0},
            "roe_ttm": {"direction": "higher", "green": 0.15, "yellow": 0.08},
        },
        "not_meaningful": FINANCIAL_NOT_MEANINGFUL + ["roic_ttm"],
    },
    "insurer": {
        # Managed care / health services: structurally thin margins are normal.
        "rules": {
            "revenue_yoy_growth": {"direction": "higher", "green": 0.08, "yellow": 0.02},
            "gross_margin": {"direction": "higher", "green": 0.15, "yellow": 0.08},
            "ebitda_margin": {"direction": "higher", "green": 0.08, "yellow": 0.04},
            "ebitda_margin_ttm": {"direction": "higher", "green": 0.08, "yellow": 0.04},
            "net_income_margin_ttm": {"direction": "higher", "green": 0.04, "yellow": 0.015},
            "fcf_conversion_ttm": {"direction": "higher", "green": 0.60, "yellow": 0.30},
            "capex_intensity_ttm": {"direction": "lower", "green": 0.04, "yellow": 0.08},
            "net_debt_to_ebitda_ttm": {"direction": "lower", "green": 2.0, "yellow": 3.5},
            "interest_coverage_ttm": {"direction": "higher", "green": 4.0, "yellow": 2.0},
            "ev_to_ebitda_ttm": {"direction": "lower", "green": 11.0, "yellow": 15.0},
            "pe_ttm": {"direction": "lower", "green": 14.0, "yellow": 22.0},
        },
        "not_meaningful": [],
    },
}


def thresholds_for(business_model: str) -> dict:
    profile = PROFILES.get(str(business_model).lower(), PROFILES["operating"])
    return profile["rules"]


def not_meaningful_for(business_model: str) -> list[str]:
    profile = PROFILES.get(str(business_model).lower(), PROFILES["operating"])
    return profile["not_meaningful"]


def all_signal_metrics() -> list[str]:
    metrics: set[str] = set()
    for profile in PROFILES.values():
        metrics.update(profile["rules"].keys())
        metrics.update(profile["not_meaningful"])
    return sorted(metrics)
