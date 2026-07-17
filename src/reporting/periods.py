"""Consistent temporal disclosures for tables and charts."""

from __future__ import annotations

import pandas as pd


def quarter_label(value) -> str:
    period = pd.Timestamp(value)
    return f"Q{period.quarter} {period.year}"


def financial_period_span(rows: pd.DataFrame) -> str:
    if rows is None or rows.empty or "period" not in rows.columns:
        return "latest reported quarter"
    periods = pd.to_datetime(rows["period"], errors="coerce").dropna()
    if periods.empty:
        return "latest reported quarter"
    low, high = periods.min(), periods.max()
    if low == high:
        return quarter_label(high)
    return f"{quarter_label(low)} to {quarter_label(high)}"


def source_as_of(source_log: pd.DataFrame, table_name: str) -> str | None:
    if source_log is None or source_log.empty:
        return None
    if not {"table_name", "retrieved_at"}.issubset(source_log.columns):
        return None
    match = source_log[source_log["table_name"].astype(str).eq(table_name)]
    if match.empty:
        return None
    dates = pd.to_datetime(match["retrieved_at"], errors="coerce").dropna()
    return dates.max().strftime("%d %b %Y") if not dates.empty else None


def peer_snapshot_context(store, peers: pd.DataFrame) -> str:
    period_text = financial_period_span(peers)
    if getattr(store, "mode", "private") == "demo":
        market_text = "Quarter-end market data aligned to each displayed period"
    else:
        market_date = source_as_of(getattr(store, "source_log", pd.DataFrame()), "market_data")
        market_text = f"Market snapshot retrieved {market_date}" if market_date else "Latest market snapshot"
    return f"{market_text} | Financials through {period_text}"


def company_snapshot_context(store, row: pd.Series) -> str:
    financials = quarter_label(row.get("period"))
    if getattr(store, "mode", "private") == "demo":
        market_text = f"Quarter-end market data through {financials}"
    else:
        market_date = source_as_of(getattr(store, "source_log", pd.DataFrame()), "market_data")
        market_text = f"Market snapshot retrieved {market_date}" if market_date else "Latest market snapshot"
    return f"{market_text} | Financials through {financials}"


def peer_metric_basis_note() -> str:
    return (
        "Revenue growth = latest reported quarter YoY. EBITDA margin, FCF conversion, "
        "net debt / EBITDA, EV / Revenue and EV / EBITDA = LTM. Peer statistics exclude "
        "the selected company; adjusted medians also exclude flagged outliers."
    )
