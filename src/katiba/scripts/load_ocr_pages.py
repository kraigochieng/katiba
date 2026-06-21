# scripts/load_pages.py
from pathlib import Path

from katiba.schemas import OCRPage


def load_ocr_pages(input_dir: Path) -> list[OCRPage]:
    page_dirs = sorted(
        [p for p in input_dir.iterdir() if p.is_dir()],
        key=lambda p: int(p.name.split("_")[1]),
    )
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
