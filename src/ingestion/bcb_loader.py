from __future__ import annotations

import pandas as pd
import requests


def fetch_sgs_series(series_code: int, start: str, end: str) -> pd.DataFrame:
    """Fetch a Banco Central SGS time series.

    Dates should use dd/mm/yyyy, matching the SGS public API convention.
    """

    url = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs."
        f"{series_code}/dados?formato=json&dataInicial={start}&dataFinal={end}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    if df.empty:
        return pd.DataFrame(columns=["date", "value", "series_code"])
    df["date"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df["value"] = pd.to_numeric(df["valor"].str.replace(",", ".", regex=False), errors="coerce")
    df["series_code"] = series_code
    return df[["date", "value", "series_code"]]

