"""Public sample outputs must never carry private-mode content.

Complements test_confidentiality.py: that file guards the build paths; this one
scans what actually sits in reports/sample/ - the files a recruiter downloads.
"""


import pandas as pd
import pytest

from src.config import PROJECT_ROOT

SAMPLE_DIR = PROJECT_ROOT / "reports" / "sample"
PRIVATE_MARKER = "Capital IQ - Private"


def _private_tickers() -> set[str]:
    """The private book's tickers, read locally (never committed)."""
    path = PROJECT_ROOT / "data_private" / "universe.csv"
    if not path.exists():
        return set()
    tickers = pd.read_csv(path)["ticker"].astype(str)
    demo = set(pd.read_csv(PROJECT_ROOT / "data" / "sample" / "public_demo" / "companies.csv")["ticker"]
               .astype(str).str.replace(".SA", "", regex=False))
    return {t for t in tickers if t and t not in demo}


def test_sample_html_has_no_private_mode_marker():
    if not SAMPLE_DIR.exists():
        pytest.skip("no sample outputs yet")
    for f in SAMPLE_DIR.rglob("*.html"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        assert PRIVATE_MARKER not in text, f"{f.name} contains private-mode output"


def test_sample_html_has_no_local_absolute_paths():
    """Machine paths (C:\\Users\\<name>\\...) identify the analyst's machine."""
    if not SAMPLE_DIR.exists():
        pytest.skip("no sample outputs yet")
    for f in SAMPLE_DIR.rglob("*.html"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        assert "C:\\Users" not in text and "/c/Users" not in text, \
            f"{f.name} embeds a local absolute path"


def test_sample_html_names_no_private_tickers():
    if not SAMPLE_DIR.exists():
        pytest.skip("no sample outputs yet")
    private = _private_tickers()
    if not private:
        pytest.skip("private universe not present on this machine")
    for f in SAMPLE_DIR.rglob("*.html"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        hits = {t for t in private if f'"{t}"' in text or f">{t}<" in text}
        assert not hits, f"{f.name} references private watchlist tickers: {sorted(hits)[:5]}"
