from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import requests

from src.utils import ensure_dir

CVM_ITR_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip"
CVM_DFP_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip"


def download_cvm_zip(year: int, destination_dir: Path, filing: str = "ITR") -> Path:
    filing_upper = filing.upper()
    template = CVM_ITR_URL if filing_upper == "ITR" else CVM_DFP_URL
    url = template.format(year=year)
    ensure_dir(destination_dir)
    output_path = destination_dir / Path(url).name
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def list_cvm_zip_files(zip_path: Path) -> list[str]:
    with ZipFile(zip_path) as zf:
        return zf.namelist()


def read_cvm_statement(zip_path: Path, statement_keyword: str) -> pd.DataFrame:
    """Read a CVM statement CSV from an ITR/DFP zip file.

    Example statement keywords include "DRE", "BPA", "BPP", and "DFC_MD".
    """

    keyword = statement_keyword.upper()
    with ZipFile(zip_path) as zf:
        matches = [name for name in zf.namelist() if keyword in name.upper() and name.endswith(".csv")]
        if not matches:
            raise FileNotFoundError(f"No statement containing '{statement_keyword}' found in {zip_path}.")
        with zf.open(matches[0]) as file:
            return pd.read_csv(file, sep=";", encoding="latin1")


def filter_cvm_accounts(
    df: pd.DataFrame,
    company_names: list[str],
    account_codes: list[str],
) -> pd.DataFrame:
    names = [name.upper() for name in company_names]
    accounts = set(account_codes)
    out = df[
        df["DENOM_CIA"].str.upper().isin(names)
        & df["CD_CONTA"].astype(str).isin(accounts)
    ].copy()
    out["DT_REFER"] = pd.to_datetime(out["DT_REFER"], errors="coerce")
    out["VL_CONTA"] = pd.to_numeric(out["VL_CONTA"], errors="coerce")
    return out
