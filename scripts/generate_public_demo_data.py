from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import SAMPLE_PUBLIC_DIR
from src.utils import ensure_dir, write_csv

COMPANIES = [
    {
        "company_id": "TOTS3.SA",
        "ticker": "TOTS3.SA",
        "company_name": "TOTVS S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "LWSA3.SA",
        "ticker": "LWSA3.SA",
        "company_name": "LWSA S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "BMOB3.SA",
        "ticker": "BMOB3.SA",
        "company_name": "Bemobi Mobile Tech S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "CSUD3.SA",
        "ticker": "CSUD3.SA",
        "company_name": "CSU Digital S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "VLID3.SA",
        "ticker": "VLID3.SA",
        "company_name": "Valid Solucoes S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "NGRD3.SA",
        "ticker": "NGRD3.SA",
        "company_name": "Neogrid S.A.",
        "sector": "Software-Enabled Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "PRNR3.SA",
        "ticker": "PRNR3.SA",
        "company_name": "Priner Servicos Industriais S.A.",
        "sector": "B2B Services",
        "exchange": "B3",
        "currency": "BRL",
        "source": "B3-listed public company universe",
    },
    {
        "company_id": "GOOGL",
        "ticker": "GOOGL",
        "company_name": "Alphabet Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "MSFT",
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "META",
        "ticker": "META",
        "company_name": "Meta Platforms, Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "AMZN",
        "ticker": "AMZN",
        "company_name": "Amazon.com, Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "ADBE",
        "ticker": "ADBE",
        "company_name": "Adobe Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "CRM",
        "ticker": "CRM",
        "company_name": "Salesforce, Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NYSE",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
    {
        "company_id": "NFLX",
        "ticker": "NFLX",
        "company_name": "Netflix, Inc.",
        "sector": "Mega-Cap Tech & Digital Platforms",
        "exchange": "NASDAQ",
        "currency": "USD",
        "source": "US mega-cap technology public universe",
    },
]


def _first_available(df: pd.DataFrame, labels: list[str], date: pd.Timestamp) -> float | None:
    for label in labels:
        if label in df.index and date in df.columns:
            value = df.loc[label, date]
            if pd.notna(value):
                return float(value)
    return None


def _to_millions(value: float | None) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value / 1_000_000


def _positive_outflow(value: float | None) -> float | None:
    if value is None:
        return None
    return abs(value)


def _price_asof(history: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if history.empty:
        return None
    index = history.index.tz_localize(None) if history.index.tz is not None else history.index
    eligible = history.loc[index <= date]
    if eligible.empty:
        return None
    return float(eligible["Close"].iloc[-1])


def _company_rows(company: dict[str, str]) -> tuple[list[dict], list[dict]]:
    ticker = yf.Ticker(company["ticker"])
    income = ticker.quarterly_income_stmt
    balance = ticker.quarterly_balance_sheet
    cashflow = ticker.quarterly_cashflow
    info = ticker.info
    history = ticker.history(period="5y", auto_adjust=False)
    current_shares = info.get("sharesOutstanding")

    financial_rows: list[dict] = []
    market_rows: list[dict] = []
    dates = sorted(income.columns, reverse=True)[:10]

    for raw_date in dates:
        period = pd.Timestamp(raw_date).to_period("Q").to_timestamp("Q")
        revenue = _to_millions(_first_available(income, ["Total Revenue", "Operating Revenue"], raw_date))
        gross_profit = _to_millions(_first_available(income, ["Gross Profit"], raw_date))
        operating_income = _to_millions(_first_available(income, ["Operating Income"], raw_date))
        d_and_a = _to_millions(_first_available(
            cashflow,
            ["Depreciation And Amortization", "Depreciation Amortization Depletion", "Depreciation"],
            raw_date,
        ))
        if operating_income is not None:
            ebit = operating_income
            ebitda = operating_income + (d_and_a or 0.0)
        else:
            ebit = _to_millions(_first_available(income, ["EBIT"], raw_date))
            ebitda = _to_millions(_first_available(income, ["Normalized EBITDA", "EBITDA"], raw_date))
        net_income = _to_millions(_first_available(income, ["Net Income"], raw_date))
        cfo = _to_millions(_first_available(cashflow, ["Operating Cash Flow"], raw_date))
        capex = _to_millions(_positive_outflow(_first_available(cashflow, ["Capital Expenditure"], raw_date)))
        cash = _to_millions(
            _first_available(
                balance,
                ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"],
                raw_date,
            )
        )
        total_debt = _to_millions(_first_available(balance, ["Total Debt"], raw_date))
        net_debt = _to_millions(_first_available(balance, ["Net Debt"], raw_date))
        working_capital = _to_millions(_first_available(balance, ["Working Capital"], raw_date))
        interest_expense = _to_millions(
            _positive_outflow(
                _first_available(
                    income,
                    ["Interest Expense", "Interest Expense Non Operating"],
                    raw_date,
                )
            )
        )
        fcf = None if cfo is None or capex is None else cfo - capex

        if all(value is None for value in [revenue, gross_profit, ebitda, ebit, net_income, cfo]):
            continue

        price = _price_asof(history, period)
        period_shares = _first_available(income, ["Diluted Average Shares", "Basic Average Shares"], raw_date)
        shares = period_shares if period_shares is not None else current_shares
        market_cap = None if price is None or shares is None else price * shares / 1_000_000
        enterprise_value = None if market_cap is None or net_debt is None else market_cap + net_debt

        financial_rows.append(
            {
                "company_id": company["company_id"],
                "period": period.date().isoformat(),
                "revenue": revenue,
                "gross_profit": gross_profit,
                "ebitda": ebitda,
                "ebit": ebit,
                "d_and_a": d_and_a,
                "net_income": net_income,
                "cfo": cfo,
                "capex": capex,
                "fcf": fcf,
                "cash": cash,
                "total_debt": total_debt,
                "net_debt": net_debt,
                "working_capital": working_capital,
                "interest_expense": interest_expense,
                "source": "Yahoo Finance public market data via yfinance",
            }
        )
        market_rows.append(
            {
                "company_id": company["company_id"],
                "period": period.date().isoformat(),
                "share_price": price,
                "shares_outstanding": shares,
                "market_cap": market_cap,
                "enterprise_value": enterprise_value,
                "source": "Yahoo Finance public market data via yfinance",
            }
        )

    return financial_rows, market_rows


def main() -> None:
    ensure_dir(SAMPLE_PUBLIC_DIR)
    companies = pd.DataFrame(COMPANIES)
    all_financials: list[dict] = []
    all_market: list[dict] = []

    for company in COMPANIES:
        financial_rows, market_rows = _company_rows(company)
        all_financials.extend(financial_rows)
        all_market.extend(market_rows)

    financials = pd.DataFrame(all_financials).sort_values(["company_id", "period"])
    market_data = pd.DataFrame(all_market).sort_values(["company_id", "period"])
    estimates = pd.DataFrame(
        columns=[
            "company_id",
            "period",
            "revenue_consensus",
            "ebitda_consensus",
            "guidance_low",
            "guidance_high",
            "source",
        ]
    )
    source_log = pd.DataFrame(
        [
            {
                "table_name": "companies",
                "source_name": "Public company demo universe",
                "source_url": "https://www.b3.com.br/; https://finance.yahoo.com/",
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "notes": "Demo universe includes Brazilian software/services names and a US mega-cap technology comp set centered on Alphabet/Google.",
            },
            {
                "table_name": "financials_quarterly",
                "source_name": "Yahoo Finance public market data via yfinance",
                "source_url": "https://finance.yahoo.com/",
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "notes": "Public-demo dataset only. Replace with CVM or Capital IQ exports for diligence work.",
            },
            {
                "table_name": "market_data",
                "source_name": "Yahoo Finance public market data via yfinance",
                "source_url": "https://finance.yahoo.com/",
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "notes": "Market cap calculated from public closing price and shares outstanding where available.",
            },
            {
                "table_name": "estimates",
                "source_name": "Synthetic demo estimates",
                "source_url": "data/templates/estimates_template.csv",
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "notes": "Generated deterministically from public-demo actuals for UI testing; not street consensus.",
            },
        ]
    )

    write_csv(companies, SAMPLE_PUBLIC_DIR / "companies.csv")
    write_csv(financials, SAMPLE_PUBLIC_DIR / "financials_quarterly.csv")
    write_csv(market_data, SAMPLE_PUBLIC_DIR / "market_data.csv")
    write_csv(estimates, SAMPLE_PUBLIC_DIR / "estimates.csv")
    write_csv(source_log, SAMPLE_PUBLIC_DIR / "source_log.csv")
    print(f"Public demo data written to {SAMPLE_PUBLIC_DIR}")


if __name__ == "__main__":
    main()
