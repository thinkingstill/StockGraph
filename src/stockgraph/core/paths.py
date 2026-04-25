from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
SOURCE_DIR = PROJECT_ROOT / "source"
DATA_DIR = PROJECT_ROOT / "data"
SHARED_STATE_DIR = DATA_DIR / "shared_state"
REFERENCE_DATA_DIR = DATA_DIR / "reference"
MARKET_DATA_DIR = DATA_DIR / "market_overview"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_HTML_DIR = OUTPUT_DIR / "html"
MARKET_OUTPUT_DIR = OUTPUT_DIR / "market"
APP_OUTPUT_DIR = OUTPUT_DIR / "app"
APP_DATA_DIR = APP_OUTPUT_DIR / "data"


def ensure_runtime_dirs() -> None:
    SHARED_STATE_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MARKET_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML_DIR.mkdir(parents=True, exist_ok=True)
    MARKET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
