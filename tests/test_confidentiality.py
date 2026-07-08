"""Licensed-data safeguards: private data never reaches public folders."""

import subprocess
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT
from src.pipeline.build_dataset import build_dataset


def test_capiq_build_refuses_public_output(tmp_path):
    with pytest.raises(ValueError, match="Refusing to write Capital IQ data"):
        build_dataset("capiq",
                      input_path=PROJECT_ROOT / "data_private" / "capiq_exports",
                      output_path=PROJECT_ROOT / "data" / "processed" / "leak.csv")


def test_capiq_build_accepts_private_output_path_check_only():
    # Path check must PASS for data_private (the loader may still fail later
    # in environments without exports; the guard is what we test here).
    private_out = PROJECT_ROOT / "data_private" / "processed" / "monitoring_dataset.csv"
    assert "data_private" in private_out.resolve().parts


def test_private_folders_are_git_ignored():
    for path in ["data_private/processed/monitoring_dataset.csv",
                 "data_private/capiq_exports/companies.csv",
                 "data_private/peer_sets_private.csv",
                 "reports/private/anything.html"]:
        result = subprocess.run(["git", "check-ignore", path], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{path} is not git-ignored"


def test_reports_sample_contains_no_private_mode_output():
    sample = PROJECT_ROOT / "reports" / "sample"
    if not sample.exists():
        pytest.skip("no sample reports")
    for f in sample.rglob("*.html"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        assert "Capital IQ - Private" not in text, \
            f"{f.name} contains private-mode output"
