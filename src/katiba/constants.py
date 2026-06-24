from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
PROJECT_DIR = SRC_DIR.parent

SCRIPTS_DIR = PACKAGE_DIR / "scripts"

OCR_OUTPUT_DIR = PROJECT_DIR / "deepseek-ocr-output"

OUTPUT_DIR = PROJECT_DIR / "output"
COMBINED_TEXT_PATH = OUTPUT_DIR / "constitution_combined.mmd"
PAGE_INDEX_PATH = OUTPUT_DIR / "page_index.json"
BOUNDARIES_JSONL = OUTPUT_DIR / "boundaries.jsonl"
BOUNDARIES_HTML = OUTPUT_DIR / "boundaries_visualization.html"
BOUNDARIES_CLEAN = OUTPUT_DIR / "boundaries_clean.json"

LOGS_DIR = PROJECT_DIR / "logs"

INPUT_DIR = PROJECT_DIR / "input"
THE_CONSTITUTION_OF_KENYA_2010_PATH = INPUT_DIR / "The_Constitution_of_Kenya_2010.pdf"
