from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_PUBLIC_DIR = DATA_DIR / "sample" / "public_demo"
PROCESSED_DIR = DATA_DIR / "processed"
TEMPLATES_DIR = DATA_DIR / "templates"
PRIVATE_DATA_DIR = PROJECT_ROOT / "data_private"
PRIVATE_PROCESSED_DIR = PRIVATE_DATA_DIR / "processed"
PRIVATE_PROCESSED_DATASET = PRIVATE_PROCESSED_DIR / "monitoring_dataset.csv"
PRIVATE_SOURCE_LOG = PRIVATE_PROCESSED_DIR / "source_log.csv"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_SAMPLE_DIR = REPORTS_DIR / "sample"
TMP_DIR = PROJECT_ROOT / "tmp"

DEFAULT_PROCESSED_DATASET = PROCESSED_DIR / "monitoring_dataset.csv"
DEFAULT_SOURCE_LOG = PROCESSED_DIR / "source_log.csv"

# Side tables (optional; loaders fall back to empty frames when absent).
PRIVATE_CAPIQ_DIR = PRIVATE_DATA_DIR / "capiq_exports"
DEMO_VALUATION_HISTORY = SAMPLE_PUBLIC_DIR / "valuation_history.csv"
PRIVATE_VALUATION_HISTORY = PRIVATE_CAPIQ_DIR / "valuation_history.csv"
DEMO_ESTIMATES = SAMPLE_PUBLIC_DIR / "estimates.csv"
PRIVATE_ESTIMATES = PRIVATE_CAPIQ_DIR / "estimates.csv"
DEMO_THESES_DIR = DATA_DIR / "sample" / "theses"
PRIVATE_THESES_DIR = PRIVATE_DATA_DIR / "theses"
PRIVATE_REFRESH_LOG = PRIVATE_CAPIQ_DIR / "refresh_log.csv"
PRIVATE_CASE_HISTORY_DIR = PRIVATE_DATA_DIR / "case_history"
PRIVATE_MONITORING_DIR = PRIVATE_DATA_DIR / "monitoring"
DEMO_ASSUMPTIONS_DIR = DATA_DIR / "sample" / "assumptions"
PRIVATE_ASSUMPTIONS_DIR = PRIVATE_DATA_DIR / "assumptions"
