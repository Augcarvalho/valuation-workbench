from __future__ import annotations

import numpy as np
import pandas as pd

from src.ingestion.classification import apply_classification
from src.ingestion.schema import NUMERIC_COLUMNS
from src.modeling.traffic_lights import add_traffic_lights
from src.utils import clean_numeric, coerce_period

TTM_COLUMNS = [
    "revenue",
    "gross_profit",
    "ebitda",
    "ebit",
    "net_income",
    "cfo",
    "capex",
    "fcf",
    "interest_expense",
    # Optional deep-dive fields (skipped when absent).
    "d_and_a",
    "sbc",
    "dividends_paid",
    "buybacks",
]

# Assumed cash tax rate for the NOPAT proxy in ROIC. Kept explicit and simple;
# refine per jurisdiction when tax detail is exported.
ASSUMED_TAX_RATE = 0.25

HIGHER_IS_BETTER = [
    "revenue_yoy_growth",
    "gross_margin",
    "ebitda_margin",
    "ebitda_margin_ttm",
    "net_income_margin_ttm",
    "fcf_conversion_ttm",
    "interest_coverage_ttm",
    "roic_ttm",
    "roe_ttm",
]

LOWER_IS_BETTER = [
    "net_debt_to_ebitda_ttm",
    "capex_intensity_ttm",
    "ev_to_revenue_ttm",
    "ev_to_ebitda_ttm",
    "pe_ttm",
]


def safe_divide(numerator: pd.Series | float, denominator: pd.Series | float) -> pd.Series:
    if isinstance(numerator, pd.Series):
        num = pd.to_numeric(numerator, errors="coerce")
    elif isinstance(denominator, pd.Series):
        num = pd.Series(numerator, index=denominator.index, dtype="float64")
    else:
        if denominator == 0 or pd.isna(denominator):
            return pd.Series([np.nan])
        return pd.Series([numerator / denominator])

    if isinstance(denominator, pd.Series):
        den = pd.to_numeric(denominator, errors="coerce").replace({0: np.nan})
        result = num / den
    else:
        if denominator == 0 or pd.isna(denominator):
            return pd.Series(np.nan, index=num.index)
        result = num / float(denominator)
    return result.replace([np.inf, -np.inf], np.nan)


def safe_divide_positive_denominator(
    numerator: pd.Series | float,
    denominator: pd.Series | float,
) -> pd.Series:
    if isinstance(denominator, pd.Series):
        positive_denominator = denominator.where(denominator > 0)
    else:
        positive_denominator = denominator if denominator is not None and not pd.isna(denominator) and denominator > 0 else np.nan
    return safe_divide(numerator, positive_denominator)


def _normalize_inputs(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    companies = inputs["companies"].copy()
    financials = inputs["financials"].copy()
    market = inputs.get("market_data", pd.DataFrame()).copy()
    estimates = inputs.get("estimates", pd.DataFrame()).copy()

    for df in [financials, market, estimates]:
        if not df.empty and "period" in df.columns:
            df["period"] = coerce_period(df["period"])

    for df in [financials, market, estimates]:
        for column in set(NUMERIC_COLUMNS).intersection(df.columns):
            df[column] = clean_numeric(df[column])

    companies = companies.rename(columns={"source": "company_source"})
    companies = apply_classification(companies)
    financials = financials.rename(columns={"source": "financial_source"})
    market = market.rename(columns={"source": "market_source"})
    estimates = estimates.rename(columns={"source": "estimate_source"})

    return {
        "companies": companies,
        "financials": financials,
        "market_data": market,
        "estimates": estimates,
    }


def prepare_monitoring_dataset(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    normalized = _normalize_inputs(inputs)
    companies = normalized["companies"]
    financials = normalized["financials"]
    market = normalized["market_data"]
    estimates = normalized["estimates"]

    df = financials.merge(companies, on="company_id", how="left")
    if not market.empty:
        df = df.merge(market, on=["company_id", "period"], how="left")
    if not estimates.empty:
        df = df.merge(estimates, on=["company_id", "period"], how="left")

    for column in ["fcf", "market_cap", "enterprise_value", "net_debt"]:
        if column not in df.columns:
            df[column] = np.nan

    df["fcf"] = df["fcf"].fillna(df["cfo"] - df["capex"])
    df["net_debt"] = df["net_debt"].fillna(df["total_debt"] - df["cash"])
    df["market_cap"] = df["market_cap"].fillna(
        safe_divide(df.get("share_price", np.nan) * df.get("shares_outstanding", np.nan), 1_000_000)
    )
    df["enterprise_value"] = df["enterprise_value"].fillna(df["market_cap"] + df["net_debt"])

    df = _normalize_adr_market_currency(df)

    df = df.sort_values(["company_id", "period"]).reset_index(drop=True)
    grouped = df.groupby("company_id", group_keys=False)

    # TTM values require a full four-quarter window. Partial windows used to be
    # summed silently (min_periods=1), which produced fake "TTM" readings for
    # the first quarters of each company's history.
    df["quarters_reported"] = grouped.cumcount() + 1
    df["ttm_complete"] = df["quarters_reported"] >= 4
    for column in TTM_COLUMNS:
        if column in df.columns:
            df[f"{column}_ttm"] = grouped[column].transform(
                lambda series: series.rolling(4, min_periods=4).sum()
            )

    df["revenue_yoy_growth"] = grouped["revenue"].pct_change(4, fill_method=None)
    df["ebitda_yoy_growth"] = grouped["ebitda"].pct_change(4, fill_method=None)
    df["gross_margin"] = safe_divide(df["gross_profit"], df["revenue"])
    df["ebitda_margin"] = safe_divide(df["ebitda"], df["revenue"])
    df["ebit_margin"] = safe_divide(df["ebit"], df["revenue"])
    df["net_income_margin"] = safe_divide(df["net_income"], df["revenue"])
    df["gross_margin_ttm"] = safe_divide(df["gross_profit_ttm"], df["revenue_ttm"])
    df["ebitda_margin_ttm"] = safe_divide(df["ebitda_ttm"], df["revenue_ttm"])
    df["net_income_margin_ttm"] = safe_divide(df["net_income_ttm"], df["revenue_ttm"])
    df["fcf_conversion_ttm"] = safe_divide_positive_denominator(df["fcf_ttm"], df["ebitda_ttm"])
    df["capex_intensity_ttm"] = safe_divide_positive_denominator(df["capex_ttm"], df["revenue_ttm"])
    df["working_capital_days"] = safe_divide(df["working_capital"], df["revenue_ttm"]) * 365
    df["net_debt_to_ebitda_ttm"] = safe_divide_positive_denominator(df["net_debt"], df["ebitda_ttm"])
    df["interest_coverage_ttm"] = safe_divide_positive_denominator(df["ebitda_ttm"], df["interest_expense_ttm"])
    df["ev_to_revenue_ttm"] = safe_divide_positive_denominator(df["enterprise_value"], df["revenue_ttm"])
    df["ev_to_ebitda_ttm"] = safe_divide_positive_denominator(df["enterprise_value"], df["ebitda_ttm"])
    df["pe_ttm"] = safe_divide_positive_denominator(df["market_cap"], df["net_income_ttm"])
    df["revenue_vs_consensus"] = safe_divide(df.get("revenue", np.nan), df.get("revenue_consensus", np.nan)) - 1
    df["ebitda_vs_consensus"] = safe_divide(df.get("ebitda", np.nan), df.get("ebitda_consensus", np.nan)) - 1

    df = add_capital_and_quality_metrics(df)
    df = add_usd_normalization(df)
    df = add_peer_percentiles(df)
    df = add_data_quality_score(df)
    df = add_traffic_lights(df)
    return df


def add_capital_and_quality_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Returns-on-capital, earnings-quality, and working-capital-cycle metrics.

    Every metric is guarded by column existence so datasets exported before
    the V2 schema (and the public demo) keep working; missing inputs simply
    yield NaN columns downstream code already tolerates.
    """
    out = df.copy()

    has = out.columns.__contains__

    # Returns on capital.
    if has("total_equity"):
        nopat = out.get("ebit_ttm", pd.Series(np.nan, index=out.index)) * (1 - ASSUMED_TAX_RATE)
        invested_capital = out.get("total_debt", np.nan) + out["total_equity"] - out.get("cash", np.nan)
        out["roic_ttm"] = safe_divide_positive_denominator(nopat, invested_capital)
        out["roe_ttm"] = safe_divide_positive_denominator(out.get("net_income_ttm", np.nan), out["total_equity"])
        if has("goodwill"):
            tangible_book = out["total_equity"] - out["goodwill"].fillna(0)
            out["p_tbv"] = safe_divide_positive_denominator(out.get("market_cap", np.nan), tangible_book)
    else:
        out["roic_ttm"] = np.nan
        out["roe_ttm"] = np.nan

    # Earnings quality: stock-based comp against cash generation.
    if has("sbc_ttm"):
        out["sbc_adjusted_fcf_ttm"] = out.get("fcf_ttm", np.nan) - out["sbc_ttm"]
        out["sbc_pct_of_fcf_ttm"] = safe_divide_positive_denominator(out["sbc_ttm"], out.get("fcf_ttm", np.nan))
        out["sbc_adjusted_fcf_conversion_ttm"] = safe_divide_positive_denominator(
            out["sbc_adjusted_fcf_ttm"], out.get("ebitda_ttm", np.nan)
        )

    # Capital returned to shareholders.
    if has("dividends_paid_ttm") or has("buybacks_ttm"):
        out["capital_returned_ttm"] = out.get("dividends_paid_ttm", pd.Series(0.0, index=out.index)).fillna(0) + \
            out.get("buybacks_ttm", pd.Series(0.0, index=out.index)).fillna(0)
        out["shareholder_yield_ttm"] = safe_divide_positive_denominator(
            out["capital_returned_ttm"], out.get("market_cap", np.nan)
        )

    # Cash conversion cycle from AR / inventory / AP.
    if has("ar") and has("ap"):
        cogs_ttm = out.get("revenue_ttm", np.nan) - out.get("gross_profit_ttm", np.nan)
        daily_revenue = out.get("revenue_ttm", np.nan) / 365.0
        daily_cogs = cogs_ttm / 365.0
        out["dso"] = safe_divide_positive_denominator(out["ar"], daily_revenue)
        out["dpo"] = safe_divide_positive_denominator(out["ap"], daily_cogs)
        if has("inventory"):
            out["dio"] = safe_divide_positive_denominator(out["inventory"], daily_cogs)
            out["cash_conversion_cycle"] = out["dso"] + out["dio"] - out["dpo"]
        else:
            out["cash_conversion_cycle"] = out["dso"] - out["dpo"]

    # Per-share compounding and dilution.
    if has("shares_diluted"):
        out["revenue_per_share_ttm"] = safe_divide_positive_denominator(out.get("revenue_ttm", np.nan), out["shares_diluted"])
        grouped = out.sort_values(["company_id", "period"]).groupby("company_id", group_keys=False)
        out["share_count_yoy"] = grouped["shares_diluted"].pct_change(4, fill_method=None)

    return out


_US_EXCHANGES = {"NYSE", "NASDAQ", "NASDAQGS", "NASDAQGM", "NASDAQCM", "NYSEAM"}


def _normalize_adr_market_currency(df: pd.DataFrame) -> pd.DataFrame:
    """Convert US-ADR market cap/TEV (quoted in USD) into the reporting currency.

    Capital IQ returns market values in the PRIMARY-listing currency. For
    ADRs whose primary listing is a US exchange but whose financials report
    in CNY/BRL/etc., market cap and TEV arrive in USD while debt/cash are
    local - which breaks every multiple and the EV bridge (PDD/JD pattern).

    Self-validating: the conversion is applied ONLY when it makes the
    equity-to-EV identity (cap + net debt vs reported TEV) materially more
    consistent than the unconverted values, so names whose market values
    already arrive in local currency (TSM/BABA pattern) are left untouched.
    """
    from src.config import DATA_DIR

    needed = {"currency", "exchange", "market_cap", "enterprise_value", "total_debt", "cash"}
    if not needed.issubset(df.columns):
        return df
    fx_path = DATA_DIR / "reference" / "fx_rates.csv"
    if not fx_path.exists():
        return df
    fx = pd.read_csv(fx_path).set_index("currency")["usd_per_unit"]

    exch = df["exchange"].astype(str).str.upper().str.replace(" ", "", regex=False)
    candidates = df.index[
        df["market_cap"].notna() & df["enterprise_value"].notna()
        & (df["currency"] != "USD") & df["currency"].isin(fx.index)
        & exch.isin(_US_EXCHANGES)
    ]
    for i in candidates:
        rate = float(fx[df.loc[i, "currency"]])
        if not rate or rate <= 0:
            continue
        cap, ev = float(df.loc[i, "market_cap"]), float(df.loc[i, "enterprise_value"])
        debt = float(df.loc[i, "total_debt"]) if pd.notna(df.loc[i, "total_debt"]) else 0.0
        cash_val = df.loc[i, "cash_st_invest"] if "cash_st_invest" in df.columns and pd.notna(df.loc[i, "cash_st_invest"]) else df.loc[i, "cash"]
        cash = float(cash_val) if pd.notna(cash_val) else 0.0

        def gap(c, e):
            return abs((c + debt - cash) / e - 1.0) if e else float("inf")

        raw_gap = gap(cap, ev)
        conv_gap = gap(cap / rate, ev / rate)
        # Materially better fit = the USD hypothesis is right; convert.
        if conv_gap < raw_gap * 0.5 and conv_gap < 0.35:
            df.loc[i, "market_cap"] = cap / rate
            df.loc[i, "enterprise_value"] = ev / rate
    return df


def add_usd_normalization(df: pd.DataFrame) -> pd.DataFrame:
    """USD-normalized size fields so cross-currency comparisons are honest.

    Uses the committed reference table ``data/reference/fx_rates.csv``
    (approximate, manually refreshed); unknown currencies yield NaN so charts
    can fall back rather than silently mixing units.
    """
    from src.config import DATA_DIR

    out = df.copy()
    fx_path = DATA_DIR / "reference" / "fx_rates.csv"
    if not fx_path.exists() or "currency" not in out.columns:
        out["fx_usd_per_unit"] = np.where(out.get("currency", "") == "USD", 1.0, np.nan)
    else:
        fx = pd.read_csv(fx_path)[["currency", "usd_per_unit"]]
        out = out.merge(fx, on="currency", how="left").rename(columns={"usd_per_unit": "fx_usd_per_unit"})

    for col in ["revenue_ttm", "market_cap", "enterprise_value"]:
        if col in out.columns:
            out[f"{col}_usd"] = out[col] * out["fx_usd_per_unit"]
    return out


def add_peer_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile ranks within the true comp set (peer_group), per period.

    Falls back to ``sector`` for inputs that predate the classification layer.
    """
    out = df.copy()
    group_col = "peer_group" if "peer_group" in out.columns else "sector"
    group_cols = [group_col, "period"]

    for metric in HIGHER_IS_BETTER:
        if metric in out.columns:
            out[f"{metric}_peer_pct"] = out.groupby(group_cols)[metric].transform(
                lambda series: series.rank(pct=True, ascending=True)
            )

    for metric in LOWER_IS_BETTER:
        if metric in out.columns:
            out[f"{metric}_peer_pct"] = out.groupby(group_cols)[metric].transform(
                lambda series: series.rank(pct=True, ascending=False)
            )

    return out


def add_data_quality_score(df: pd.DataFrame) -> pd.DataFrame:
    required = [
        "revenue",
        "ebitda",
        "cfo",
        "capex",
        "cash",
        "total_debt",
        "market_cap",
        "enterprise_value",
    ]
    available = [column for column in required if column in df.columns]
    out = df.copy()
    out["data_quality_score"] = out[available].notna().sum(axis=1) / len(available)
    return out


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values(["company_id", "period"])
        .groupby("company_id", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
