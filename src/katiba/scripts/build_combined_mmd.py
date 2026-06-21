# scripts/build_combined_mmd.py
import json
from pathlib import Path

from scripts.load_ocr_pages import load_ocr_pages

from src.katiba.constants import COMBINED_TEXT_PATH, OCR_OUTPUT_DIR, PAGE_INDEX_PATH
from schemas import OCRPage, PageIndexEntry


def build_combined_with_index(
    pages: list[OCRPage],
) -> tuple[str, list[PageIndexEntry]]:
    parts: list[str] = []
    page_index: list[PageIndexEntry] = []
    cursor = 0

    for page in pages:
        text = page.text
        start, end = cursor, cursor + len(text)
        page_index.append(
            PageIndexEntry(
                page_number=page.page_number,
                start_offset=start,
                end_offset=end,
            )
        )
        parts.append(text)
        cursor = end + 2  # "\n\n" join separator

    return "\n\n".join(parts), page_index


if __name__ == "__main__":
    pages = load_ocr_pages(OCR_OUTPUT_DIR)
    combined_text, page_index = build_combined_with_index(pages)

    Path(COMBINED_TEXT_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(COMBINED_TEXT_PATH).write_text(combined_text, encoding="utf-8")
    Path(PAGE_INDEX_PATH).write_text(
        json.dumps([entry.model_dump() for entry in page_index], indent=2),
        encoding="utf-8",
    )

    print(f"{len(combined_text):,} chars → {COMBINED_TEXT_PATH}")
    print(f"{len(page_index)} pages → {PAGE_INDEX_PATH}")
