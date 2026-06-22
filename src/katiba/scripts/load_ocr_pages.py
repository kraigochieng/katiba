# scripts/load_pages.py
from pathlib import Path

from katiba.schemas import OCRPage


def get_page_number(path: Path):
    parts = path.name.split("_")
    return int(parts[1])


def load_ocr_pages(input_dir: Path) -> list[OCRPage]:
    page_dirs = []

    for item in input_dir.iterdir():
        if item.is_dir():
            page_dirs.append(item)

    page_dirs.sort(key=get_page_number)

    pages, missing = [], []

    for page_dir in page_dirs:
        result_file = page_dir / "result.mmd"

        if not result_file.exists():
            missing.append(page_dir.name)
            continue

        pages.append(
            OCRPage(
                page_number=int(page_dir.name.split("_")[1]),
                page_name=page_dir.name,
                text=result_file.read_text(encoding="utf-8").strip(),
            )
        )
    if missing:
        print(f"Warning: missing result.mmd for {missing}")
    return pages
