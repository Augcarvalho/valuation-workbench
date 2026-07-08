from pathlib import Path
import subprocess

import pandas as pd

from src.config import PROJECT_ROOT, TEMPLATES_DIR
from src.ingestion.schema import COMPANY_COLUMNS, ESTIMATE_COLUMNS, FINANCIAL_COLUMNS, MARKET_COLUMNS


def test_capital_iq_templates_have_required_columns():
    expectations = {
        "companies_template.csv": COMPANY_COLUMNS,
        "financials_quarterly_template.csv": FINANCIAL_COLUMNS,
        "market_data_template.csv": MARKET_COLUMNS,
        "estimates_template.csv": ESTIMATE_COLUMNS,
    }
    for filename, columns in expectations.items():
        df = pd.read_csv(TEMPLATES_DIR / filename)
        assert set(columns).issubset(df.columns)


def test_private_data_folder_is_ignored():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data_private/" in gitignore
    assert "reports/private/" in gitignore


def test_git_hygiene_guard_passes():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from check_git_hygiene import run_checks

    assert run_checks() == []


def test_private_data_paths_are_git_ignored():
    for private_path in [
        "data_private/capiq_exports/raw_export.xlsx",
        "data_private/capiq_exports/valuation_history.csv",
        "data_private/theses/NASDAQ_LULU.yaml",
        "data_private/reports/ic_memo_LULU.html",
    ]:
        result = subprocess.run(
            ["git", "check-ignore", private_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{private_path} is NOT git-ignored: {result.stderr}"
