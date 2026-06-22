import json
import os
import textwrap
from collections import Counter
from pathlib import Path

import langextract as lx

from katiba.constants import (
    BOUNDARIES_HTML,
    BOUNDARIES_JSONL,
    COMBINED_TEXT_PATH,
    OUTPUT_DIR,
    PAGE_INDEX_PATH,
)
from katiba.logger import get_logger, setup_logging
from katiba.schemas import PageIndexEntry
from katiba.settings import gemini_settings, ollama_settings

setup_logging()
logger = get_logger(__name__)

# os.environ["LANGEXTRACT_API_KEY"] = gemini_settings.gemini_api_key.get_secret_value()

MODEL_ID = ollama_settings.ollama_model
MODEL_URL = ollama_settings.ollama_url
#  Prompt

PROMPT = textwrap.dedent("""
    Extract structural boundaries from the Constitution of Kenya 2010.

    Identify every boundary in document order using these classes:

    - cover_page: The very first page — starts with "# LAWS OF KENYA".
      Appears before the table of contents.

    - table_of_contents: Starts with "ARRANGEMENT OF ARTICLES" heading.
      Spans multiple pages (pages 2-10). Ends just before "## PREAMBLE".

    - preamble: Starts with "## PREAMBLE" heading followed by "We, the people
      of Kenya" (title case, not all caps). Ends with "## GOD BLESS KENYA".

    - chapter: Always rendered as "## CHAPTER X—..." or "## CHAPTER X-..."
      (some chapters use a plain hyphen instead of em dash — treat both as
      valid). 18 chapters total.

    - part: "## PART X—..." or "PART X—..." — OCR inconsistently renders
      some part headings with "## " prefix and some without. Only present
      in some chapters. Always include the chapter_number it belongs to.

    - article: "## " + marginal note + newline + article number + ".",
      e.g. "## Sovereignty of the people.\n1."
      OCR always renders marginal notes with a leading "## " prefix.
      Always include chapter_number and part_number (null if no parts).

    - clause: "(1)", "(2)", "(3)" etc. Only real clauses — not numbered list
      items inside Schedules. Always include the article_number.

    Use the EXACT verbatim opening text as it appears — do not clean up
    spacing, fix typos, or paraphrase. List in document order.
""")

#  Few-shot example
EXAMPLES = [
    lx.data.ExampleData(
        text=(
            # Cover page (page 1)
            "# LAWS OF KENYA\n"
            "# THE CONSTITUTION OF KENYA, 2010\n"
            "Published by the National Council for Law Reporting with the Authority of the Attorney- General\n"
            "www.kenyalaw.org\n\n"
            # Table of contents (pages 2-10, abbreviated)
            "# THE CONSTITUTION OF KENYA, 2010\n"
            "ARRANGEMENT OF ARTICLES\n"
            "PREAMBLE\n"
            "# CHAPTER ONE—SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION\n"
            "1—Sovereignty of the people.\n"
            "2—Supremacy of this Constitution.\n\n"
            # Preamble (page 11)
            "## PREAMBLE\n"
            "We, the people of Kenya\n"
            "ACKNOWLEDGING the supremacy of the Almighty God of all creation:\n"
            "HONOURING those who heroically struggled to bring freedom and justice to our land:\n"
            "ADOPT, ENACT and give this Constitution to ourselves and to our future generations.\n"
            "## GOD BLESS KENYA\n\n"
            # Chapter One, no parts (page 12)
            "## CHAPTER ONE—SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION\n"
            "## Sovereignty of the people.\n"
            "1. (1) All sovereign power belongs to the people of Kenya and shall be exercised only in accordance with this Constitution.\n"
            "(2) The people may exercise their sovereign power either directly or through their democratically elected representatives.\n\n"
            "## Supremacy of this Constitution.\n"
            "2. (1) This Constitution is the supreme law of the Republic and binds all persons and all State organs at both levels of government.\n\n"
            # Chapter Four, with parts — Part has no ## prefix (page 18)
            "## CHAPTER FOUR-THE BILL OF RIGHTS\n"
            "PART 1—GENERAL PROVISIONS RELATING TO THE BILL OF RIGHTS\n"
            "## Rights and fundamental freedoms.\n"
            "19. (1) The Bill of Rights is an integral part of Kenya's democratic state and is the framework for social, economic and cultural policies.\n"
            "(2) The purpose of recognising and protecting human rights and fundamental freedoms is to preserve the dignity of individuals and communities.\n\n"
            "## Application of Bill of Rights.\n"
            "20. (1) The Bill of Rights applies to all law and binds all State organs and all persons.\n"
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="cover_page",
                extraction_text="# LAWS OF KENYA\n# THE CONSTITUTION OF KENYA, 2010\nPublished by the National Council for Law Reporting",
                attributes={},
            ),
            lx.data.Extraction(
                extraction_class="table_of_contents",
                extraction_text="ARRANGEMENT OF ARTICLES\nPREAMBLE\n# CHAPTER ONE—SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION",
                attributes={},
            ),
            lx.data.Extraction(
                extraction_class="preamble",
                extraction_text="## PREAMBLE\nWe, the people of Kenya\nACKNOWLEDGING the supremacy of the Almighty God of all creation:",
                attributes={},
            ),
            # Chapter One — no parts
            lx.data.Extraction(
                extraction_class="chapter",
                extraction_text="## CHAPTER ONE—SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION",
                attributes={
                    "chapter_number": 1,
                    "chapter_name": "SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION",
                    "has_parts": False,
                },
            ),
            lx.data.Extraction(
                extraction_class="article",
                extraction_text="## Sovereignty of the people.\n1.",
                attributes={
                    "article_number": 1,
                    "article_title": "Sovereignty of the people.",
                    "chapter_number": 1,
                    "has_part": False,
                    "part_number": None,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(1) All sovereign power belongs to the people of Kenya",
                attributes={
                    "article_number": 1,
                    "clause_number": 1,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(2) The people may exercise their sovereign power",
                attributes={
                    "article_number": 1,
                    "clause_number": 2,
                },
            ),
            lx.data.Extraction(
                extraction_class="article",
                extraction_text="## Supremacy of this Constitution.\n2.",
                attributes={
                    "article_number": 2,
                    "article_title": "Supremacy of this Constitution.",
                    "chapter_number": 1,
                    "has_part": False,
                    "part_number": None,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(1) This Constitution is the supreme law of the Republic",
                attributes={
                    "article_number": 2,
                    "clause_number": 1,
                },
            ),
            # Chapter Four — has parts, Part without ## prefix
            lx.data.Extraction(
                extraction_class="chapter",
                extraction_text="## CHAPTER FOUR-THE BILL OF RIGHTS",
                attributes={
                    "chapter_number": 4,
                    "chapter_name": "THE BILL OF RIGHTS",
                    "has_parts": True,
                },
            ),
            lx.data.Extraction(
                extraction_class="part",
                extraction_text="PART 1—GENERAL PROVISIONS RELATING TO THE BILL OF RIGHTS",
                attributes={
                    "chapter_number": 4,
                    "part_number": 1,
                    "part_name": "GENERAL PROVISIONS RELATING TO THE BILL OF RIGHTS",
                },
            ),
            lx.data.Extraction(
                extraction_class="article",
                extraction_text="## Rights and fundamental freedoms.\n19.",
                attributes={
                    "article_number": 19,
                    "article_title": "Rights and fundamental freedoms.",
                    "chapter_number": 4,
                    "has_part": True,
                    "part_number": 1,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(1) The Bill of Rights is an integral part of Kenya's democratic state",
                attributes={
                    "article_number": 19,
                    "clause_number": 1,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(2) The purpose of recognising and protecting human rights",
                attributes={
                    "article_number": 19,
                    "clause_number": 2,
                },
            ),
            lx.data.Extraction(
                extraction_class="article",
                extraction_text="## Application of Bill of Rights.\n20.",
                attributes={
                    "article_number": 20,
                    "article_title": "Application of Bill of Rights.",
                    "chapter_number": 4,
                    "has_part": True,
                    "part_number": 1,
                },
            ),
            lx.data.Extraction(
                extraction_class="clause",
                extraction_text="(1) The Bill of Rights applies to all law",
                attributes={
                    "article_number": 20,
                    "clause_number": 1,
                },
            ),
        ],
    )
]
#  Page index helpers


def load_page_index(path: Path) -> list[PageIndexEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [PageIndexEntry(**entry) for entry in raw]


def resolve_page(page_index: list[PageIndexEntry], offset: int) -> int | None:
    for entry in page_index:
        if entry.start_offset <= offset < entry.end_offset:
            return entry.page_number
    return None


#  Validation

EXPECTED_COUNTS: dict[str, int] = {
    "cover_page": 1,
    "table_of_contents": 1,
    "preamble": 1,
    "chapter": 18,
    "article": 264,
}


def validate_counts(counts: Counter) -> None:
    print("\nExtraction counts:")
    for cls, count in sorted(counts.items()):
        expected = EXPECTED_COUNTS.get(cls)
        flag = (
            f"  ⚠ expected {expected}"
            if expected is not None and count != expected
            else ""
        )
        print(f"  {cls}: {count}{flag}")


#  Main


def extract_boundaries() -> None:
    combined_text = COMBINED_TEXT_PATH.read_text(encoding="utf-8")
    page_index = load_page_index(PAGE_INDEX_PATH)

    logger.info(f"Loaded {len(combined_text):,} chars, {len(page_index)} pages")
    logger.info(f"Running extraction with {MODEL_ID}...")

    # result = lx.extract(
    #     text_or_documents=combined_text,
    #     prompt_description=PROMPT,
    #     examples=EXAMPLES,
    #     model_id=gemini_settings.gemini_model,
    #     extraction_passes=3,
    #     max_workers=1,
    #     max_char_buffer=2000,
    #     temperature=0.0,
    # )

    result = lx.extract(
        text_or_documents=combined_text,
        prompt_description=PROMPT,
        examples=EXAMPLES,
        model_id=MODEL_ID,
        model_url=MODEL_URL,
        fence_output=False,
        use_schema_constraints=False,
        extraction_passes=3,
        max_workers=2,
        max_char_buffer=2000,
        temperature=0.0,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lx.io.save_annotated_documents(
        [result],
        output_name="boundaries.jsonl",
        output_dir=str(OUTPUT_DIR),
    )
    html = lx.visualize(str(BOUNDARIES_JSONL))
    BOUNDARIES_HTML.write_text(
        html.data if hasattr(html, "data") else html,
        encoding="utf-8",
    )

    grounded = [e for e in result.extractions if e.char_interval]
    grounded.sort(key=lambda e: e.char_interval.start_pos)

    for e in grounded:
        e.attributes["start_page"] = resolve_page(page_index, e.char_interval.start_pos)

    counts = Counter(e.extraction_class for e in grounded)
    validate_counts(counts)

    ungrounded = len(result.extractions) - len(grounded)
    if ungrounded:
        logger.info(f"\n⚠ {ungrounded} ungrounded extractions dropped")

    logger.info(f"\nVisualization → {BOUNDARIES_HTML}")


if __name__ == "__main__":
    extract_boundaries()
