import json
import textwrap
import time

from google import genai
from google.genai import types

from katiba.constants import OUTPUT_DIR, THE_CONSTITUTION_OF_KENYA_2010_PATH
from katiba.logger import get_logger, setup_logging
from katiba.schemas import ChapterFull, ConstitutionSkeleton
from katiba.settings import gemini_settings

setup_logging()
logger = get_logger(__name__)

CHAPTERS_DIR = OUTPUT_DIR / "chapters"


#  Prompts

SKELETON_PROMPT = textwrap.dedent("""
    From the Constitution of Kenya 2010 PDF, extract ONLY the chapter
    structure — no article text, no clause text.

    For each of the 18 chapters return:
    - chapter_number (1-18)
    - chapter_name (exact name from the document)
    - has_parts (true if the chapter contains named Parts, false otherwise)
    - part_names (list of part names if has_parts is true, else null)

    Return all 18 chapters in order.
""")


def chapter_prompt(chapter_number: int, chapter_name: str) -> str:
    return textwrap.dedent(f"""
        The attached PDF is the Constitution of Kenya 2010, uploaded by the user.
        Extract the COMPLETE content of Chapter {chapter_number}: {chapter_name}
        DIRECTLY from the uploaded PDF document.

        You are reading and transcribing user-provided content, not generating
        from memory. Extract verbatim from the PDF only.

        Return every article in this chapter with:
        - article_number (exact number from the document)
        - article_title (the marginal note / title of the article)
        - clauses: every clause (1), (2), (3)... with its full verbatim text

        If this chapter has Parts, nest articles under their correct part.
        If no Parts, put articles directly under the chapter.

        Include ALL articles and ALL clauses — do not truncate or summarize.
    """)


#  Upload PDF


def upload_pdf(client: genai.Client) -> types.File:
    logger.info(f"Uploading {THE_CONSTITUTION_OF_KENYA_2010_PATH.name}...")
    uploaded = client.files.upload(
        file=THE_CONSTITUTION_OF_KENYA_2010_PATH,
        config={"mime_type": "application/pdf"},
    )
    logger.info(f"Uploaded — URI: {uploaded.uri}")
    return uploaded


#  Extract skeleton


def extract_skeleton(
    client: genai.Client,
    pdf: types.File,
) -> ConstitutionSkeleton:
    logger.info("Extracting chapter skeleton...")

    response = client.models.generate_content(
        model=gemini_settings.gemini_model,
        contents=[
            types.Part.from_uri(file_uri=pdf.uri, mime_type=pdf.mime_type),
            types.Part.from_text(text=SKELETON_PROMPT),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ConstitutionSkeleton,
            temperature=0.0,
        ),
    )

    if not response.text:
        logger.error(
            f"Empty response — finish reason: {response.candidates[0].finish_reason}"
        )
        raise ValueError("Empty skeleton response from Gemini")

    skeleton = ConstitutionSkeleton.model_validate_json(response.text)
    logger.info(f"Skeleton extracted — {len(skeleton.chapters)} chapters found")

    if len(skeleton.chapters) != 18:
        logger.warning(f"⚠ Expected 18 chapters, got {len(skeleton.chapters)}")

    return skeleton


#  Extract one chapter


def extract_chapter(
    client: genai.Client,
    pdf: types.File,
    chapter_number: int,
    chapter_name: str,
) -> ChapterFull:
    response = client.models.generate_content(
        model=gemini_settings.gemini_model,
        contents=[
            types.Part.from_uri(file_uri=pdf.uri, mime_type=pdf.mime_type),
            types.Part.from_text(text=chapter_prompt(chapter_number, chapter_name)),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ChapterFull,
            temperature=0.0,
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
            ],
        ),
    )

    if not response.text:
        finish = response.candidates[0].finish_reason
        raise ValueError(
            f"Empty response for chapter {chapter_number} — finish reason: {finish}"
        )

    return ChapterFull.model_validate_json(response.text)


#  Main


def extract_structure() -> None:
    client = genai.Client(api_key=gemini_settings.gemini_api_key.get_secret_value())

    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)

    pdf = upload_pdf(client)

    try:
        # Pass 1 — skeleton
        skeleton = extract_skeleton(client, pdf)
        skeleton_path = OUTPUT_DIR / "constitution_skeleton.json"
        skeleton_path.write_text(skeleton.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Skeleton saved to {skeleton_path}")

        # Pass 2 — one chapter at a time, resumable
        for ch in skeleton.chapters:
            chapter_path = CHAPTERS_DIR / f"chapter_{ch.chapter_number:02d}.json"

            if chapter_path.exists():
                logger.info(f"Chapter {ch.chapter_number} already extracted — skipping")
                continue

            logger.info(f"Extracting Chapter {ch.chapter_number}: {ch.chapter_name}...")

            try:
                chapter = extract_chapter(
                    client, pdf, ch.chapter_number, ch.chapter_name
                )

                article_count = len(chapter.articles or []) + sum(
                    len(p.articles) for p in (chapter.parts or [])
                )
                logger.info(
                    f"  Chapter {ch.chapter_number} done — {article_count} articles"
                )

                chapter_path.write_text(
                    chapter.model_dump_json(indent=2), encoding="utf-8"
                )

                # Small delay between chapters to avoid rate limits
                time.sleep(2)

            except Exception as e:
                logger.error(f"  ✗ Chapter {ch.chapter_number} failed: {e}")
                continue  # skip and resume next run

        # Assemble final structure from saved chapter files
        chapters = []
        for ch in skeleton.chapters:
            chapter_path = CHAPTERS_DIR / f"chapter_{ch.chapter_number:02d}.json"
            if chapter_path.exists():
                chapters.append(
                    ChapterFull.model_validate_json(
                        chapter_path.read_text(encoding="utf-8")
                    )
                )
            else:
                logger.warning(f"⚠ Chapter {ch.chapter_number} missing from output")

        final = {"chapters": [ch.model_dump() for ch in chapters]}
        final_path = OUTPUT_DIR / "constitution_structure.json"
        final_path.write_text(
            json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        extracted = len(chapters)
        logger.info(f"Done — {extracted}/18 chapters extracted → {final_path}")
        if extracted < 18:
            logger.warning("Re-run the script to retry failed chapters")

    finally:
        client.files.delete(name=pdf.name)
        logger.info("PDF deleted from Gemini File API")


if __name__ == "__main__":
    extract_structure()
