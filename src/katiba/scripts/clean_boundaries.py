"""
scripts/clean_boundaries.py

Takes raw LangExtract output (boundaries.jsonl) and produces a clean,
deduplicated, Neo4j-ready JSON file (boundaries_clean.json).

Strategy:
- Filter to grounded extractions only (char_interval is not None)
- Split ToC into table_of_contents (real ToC) and schedules_list (schedule index)
- Body starts at BODY_START (just before preamble at pos ~13500)
- For each structural type, keep only the first grounded occurrence per
  unique identifier (chapter_number, article_number, etc.)
- Filter out false positives (schedules misidentified as chapters)
"""

import json
from collections import Counter
from pathlib import Path

from katiba.constants import BOUNDARIES_CLEAN, BOUNDARIES_JSONL
from katiba.logger import get_logger, setup_logging
from katiba.settings import app_settings

setup_logging()
logger = get_logger(__name__)


# Everything before this position is either ToC or secondary index material.
# Preamble body starts at ~13545, Chapter One body at ~14612.
BODY_START = 13500

EXPECTED = {
    "cover_page": 1,
    "table_of_contents": 1,
    "preamble": 1,
    "chapter": 18,
    "article": 264,
}


def load_extractions(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.loads(f.readline())
    return data["extractions"]


def is_grounded(e: dict) -> bool:
    return e.get("char_interval") is not None


def attrs(e: dict) -> dict:
    return e.get("attributes") or {}


def deduplicate(extractions: list[dict]) -> dict:
    grounded = [e for e in extractions if is_grounded(e)]
    grounded_sorted = sorted(grounded, key=lambda e: e["char_interval"]["start_pos"])

    results = {
        "cover_page": None,
        "table_of_contents": None,
        "schedules_list": None,
        "preamble": None,
        "chapters": {},
        "parts": {},
        "articles": {},
        "clauses": {},
    }

    for e in grounded_sorted:
        cls = e["extraction_class"]
        pos = e["char_interval"]["start_pos"]
        a = attrs(e)

        if cls == "cover_page":
            if results["cover_page"] is None:
                results["cover_page"] = e

        elif cls == "table_of_contents":
            if pos < 5000 and results["table_of_contents"] is None:
                results["table_of_contents"] = e
            elif pos > 10000 and results["schedules_list"] is None:
                results["schedules_list"] = e

        elif cls == "preamble":
            if BODY_START <= pos <= 14700 and results["preamble"] is None:
                results["preamble"] = e

        elif cls == "chapter":
            num = a.get("chapter_number")
            text = e["extraction_text"]
            is_false_positive = (
                "SCHEDULE" in text.upper() and "CHAPTER" not in text.upper()
            )
            if num and pos >= BODY_START and not is_false_positive:
                try:
                    num = int(num)
                except (ValueError, TypeError):
                    continue
                if num not in results["chapters"]:
                    results["chapters"][num] = e

        elif cls == "part":
            chapter_num = a.get("chapter_number")
            part_num = a.get("part_number")
            if chapter_num and part_num and pos >= BODY_START:
                try:
                    key = (int(chapter_num), int(part_num))
                except (ValueError, TypeError):
                    continue
                if key not in results["parts"]:
                    results["parts"][key] = e

        elif cls == "article":
            num = a.get("article_number")
            if num and pos >= BODY_START:
                try:
                    num = int(num)
                except (ValueError, TypeError):
                    continue
                if num not in results["articles"]:
                    results["articles"][num] = e

        elif cls == "clause":
            article_num = a.get("article_number")
            clause_num = a.get("clause_number")
            if article_num and clause_num and pos >= BODY_START:
                try:
                    key = (int(article_num), int(clause_num))
                except (ValueError, TypeError):
                    continue
                if key not in results["clauses"]:
                    results["clauses"][key] = e

    return results


def validate(results: dict) -> None:
    logger.info("=== Validation ===")

    for key, expected in EXPECTED.items():
        if key in ("chapter", "article"):
            actual = len(results[f"{key}s"])
        else:
            actual = 1 if results[key] else 0

        flag = "✅" if actual == expected else "⚠"
        logger.info(f"  {flag} {key}: {actual} (expected {expected})")

    missing_chapters = [i for i in range(1, 19) if i not in results["chapters"]]
    missing_articles = [i for i in range(1, 265) if i not in results["articles"]]

    if missing_chapters:
        logger.warning(f"  Missing chapters: {missing_chapters}")
    if missing_articles:
        logger.warning(
            f"  Missing articles ({len(missing_articles)}): {missing_articles}"
        )

    logger.info(f"  parts: {len(results['parts'])}")
    logger.info(f"  clauses: {len(results['clauses'])}")
    logger.info(
        f"  schedules_list: {'found' if results['schedules_list'] else 'not found'}"
    )


def to_clean_record(e: dict) -> dict:
    """Strip LangExtract internals, keep only what Neo4j loader needs."""
    return {
        "extraction_class": e["extraction_class"],
        "extraction_text": e["extraction_text"],
        "start_pos": e["char_interval"]["start_pos"],
        "end_pos": e["char_interval"]["end_pos"],
        "alignment_status": e["alignment_status"],
        "attributes": e.get("attributes") or {},
    }


def build_output(results: dict) -> dict:
    output = {}

    if results["cover_page"]:
        output["cover_page"] = to_clean_record(results["cover_page"])

    if results["table_of_contents"]:
        output["table_of_contents"] = to_clean_record(results["table_of_contents"])

    if results["schedules_list"]:
        output["schedules_list"] = to_clean_record(results["schedules_list"])

    if results["preamble"]:
        output["preamble"] = to_clean_record(results["preamble"])

    output["chapters"] = [
        to_clean_record(results["chapters"][num]) for num in sorted(results["chapters"])
    ]

    output["parts"] = [
        to_clean_record(results["parts"][key]) for key in sorted(results["parts"])
    ]

    output["articles"] = [
        to_clean_record(results["articles"][num]) for num in sorted(results["articles"])
    ]

    output["clauses"] = [
        to_clean_record(results["clauses"][key]) for key in sorted(results["clauses"])
    ]

    return output


def clean_boundaries() -> None:
    logger.info(f"Loading {BOUNDARIES_JSONL}...")
    extractions = load_extractions(BOUNDARIES_JSONL)
    logger.info(f"Loaded {len(extractions)} raw extractions")

    logger.info("Deduplicating...")
    results = deduplicate(extractions)

    validate(results)

    output = build_output(results)
    BOUNDARIES_CLEAN.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Clean boundaries written to {BOUNDARIES_CLEAN}")


if __name__ == "__main__":
    clean_boundaries()
