# src/katiba/scripts/load_to_neo4j.py

import json
from pathlib import Path

from neo4j import Driver, GraphDatabase

from katiba.constants import OUTPUT_DIR
from katiba.logger import get_logger, setup_logging
from katiba.settings import neo4j_settings

setup_logging()
logger = get_logger(__name__)

STRUCTURE_PATH = OUTPUT_DIR / "constitution_structure.json"


# ── Cypher queries ────────────────────────────────────────────────────────────

CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT constitution_unique IF NOT EXISTS FOR (c:Constitution) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT chapter_unique IF NOT EXISTS FOR (c:Chapter) REQUIRE c.chapter_number IS UNIQUE",
    "CREATE CONSTRAINT article_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.article_number IS UNIQUE",
]

CREATE_INDEXES = [
    "CREATE INDEX part_index IF NOT EXISTS FOR (p:Part) ON (p.chapter_number, p.part_number)",
    "CREATE INDEX clause_index IF NOT EXISTS FOR (c:Clause) ON (c.article_number, c.clause_number)",
]

CREATE_CONSTITUTION = """
MERGE (c:Constitution {name: 'Constitution of Kenya 2010'})
SET c.year = 2010,
    c.country = 'Kenya'
RETURN c
"""

CREATE_CHAPTER = """
MERGE (ch:Chapter {chapter_number: $chapter_number})
SET ch.chapter_name = $chapter_name,
    ch.has_parts = $has_parts
WITH ch
MATCH (c:Constitution {name: 'Constitution of Kenya 2010'})
MERGE (c)-[:HAS_CHAPTER]->(ch)
RETURN ch
"""

CREATE_PART = """
MATCH (ch:Chapter {chapter_number: $chapter_number})
MERGE (p:Part {chapter_number: $chapter_number, part_number: $part_number})
SET p.part_name = $part_name
MERGE (ch)-[:HAS_PART]->(p)
RETURN p
"""

CREATE_ARTICLE_UNDER_CHAPTER = """
MATCH (ch:Chapter {chapter_number: $chapter_number})
MERGE (a:Article {article_number: $article_number})
SET a.article_title = $article_title,
    a.chapter_number = $chapter_number,
    a.has_part = false
MERGE (ch)-[:HAS_ARTICLE]->(a)
RETURN a
"""

CREATE_ARTICLE_UNDER_PART = """
MATCH (p:Part {chapter_number: $chapter_number, part_number: $part_number})
MERGE (a:Article {article_number: $article_number})
SET a.article_title = $article_title,
    a.chapter_number = $chapter_number,
    a.part_number = $part_number,
    a.has_part = true
MERGE (p)-[:HAS_ARTICLE]->(a)
RETURN a
"""

CREATE_CLAUSE = """
MATCH (a:Article {article_number: $article_number})
MERGE (cl:Clause {article_number: $article_number, clause_number: $clause_number})
SET cl.text = $text
MERGE (a)-[:HAS_CLAUSE]->(cl)
RETURN cl
"""


# ── Loader ────────────────────────────────────────────────────────────────────


def create_constraints_and_indexes(driver: Driver) -> None:
    with driver.session() as session:
        for query in CREATE_CONSTRAINTS:
            session.run(query)
        for query in CREATE_INDEXES:
            session.run(query)
    logger.info("Constraints and indexes created")


def load_constitution(driver: Driver, data: dict) -> None:
    with driver.session() as session:
        session.run(CREATE_CONSTITUTION)
    logger.info("Constitution root node created")


def load_chapter(driver: Driver, chapter: dict) -> None:
    chapter_number = chapter["chapter_number"]
    chapter_name = chapter["chapter_name"]
    has_parts = chapter.get("has_parts", False)

    with driver.session() as session:
        session.run(
            CREATE_CHAPTER,
            chapter_number=chapter_number,
            chapter_name=chapter_name,
            has_parts=has_parts,
        )

    if has_parts and chapter.get("parts"):
        for part in chapter["parts"]:
            load_part(driver, chapter_number, part)
    elif chapter.get("articles"):
        for article in chapter["articles"]:
            load_article_under_chapter(driver, chapter_number, article)

    article_count = len(chapter.get("articles") or []) + sum(
        len(p.get("articles", [])) for p in (chapter.get("parts") or [])
    )
    logger.info(f"  Chapter {chapter_number:2} loaded — {article_count} articles")


def load_part(driver: Driver, chapter_number: int, part: dict) -> None:
    part_number = part["part_number"]
    part_name = part["part_name"]

    with driver.session() as session:
        session.run(
            CREATE_PART,
            chapter_number=chapter_number,
            part_number=part_number,
            part_name=part_name,
        )

    for article in part.get("articles", []):
        load_article_under_part(driver, chapter_number, part_number, article)


def load_article_under_chapter(
    driver: Driver, chapter_number: int, article: dict
) -> None:
    with driver.session() as session:
        session.run(
            CREATE_ARTICLE_UNDER_CHAPTER,
            article_number=article["article_number"],
            article_title=article["article_title"],
            chapter_number=chapter_number,
        )
    for clause in article.get("clauses", []):
        load_clause(driver, article["article_number"], clause)


def load_article_under_part(
    driver: Driver, chapter_number: int, part_number: int, article: dict
) -> None:
    with driver.session() as session:
        session.run(
            CREATE_ARTICLE_UNDER_PART,
            article_number=article["article_number"],
            article_title=article["article_title"],
            chapter_number=chapter_number,
            part_number=part_number,
        )
    for clause in article.get("clauses", []):
        load_clause(driver, article["article_number"], clause)


def load_clause(driver: Driver, article_number: int, clause: dict) -> None:
    with driver.session() as session:
        session.run(
            CREATE_CLAUSE,
            article_number=article_number,
            clause_number=clause["clause_number"],
            text=clause["text"],
        )


# ── Validation ────────────────────────────────────────────────────────────────


def validate_load(driver: Driver) -> None:
    with driver.session() as session:
        counts = {
            "Constitution": session.run(
                "MATCH (n:Constitution) RETURN count(n) as c"
            ).single()["c"],
            "Chapter": session.run("MATCH (n:Chapter) RETURN count(n) as c").single()[
                "c"
            ],
            "Part": session.run("MATCH (n:Part) RETURN count(n) as c").single()["c"],
            "Article": session.run("MATCH (n:Article) RETURN count(n) as c").single()[
                "c"
            ],
            "Clause": session.run("MATCH (n:Clause) RETURN count(n) as c").single()[
                "c"
            ],
        }

    logger.info("=== Neo4j node counts ===")
    expected = {"Constitution": 1, "Chapter": 18, "Article": 264}
    for label, count in counts.items():
        exp = expected.get(label)
        flag = f"  ⚠ expected {exp}" if exp and count != exp else ""
        logger.info(f"  {label:15}: {count:4}{flag}")

    # Relationship counts
    with driver.session() as session:
        rels = {
            "HAS_CHAPTER": session.run(
                "MATCH ()-[r:HAS_CHAPTER]->() RETURN count(r) as c"
            ).single()["c"],
            "HAS_PART": session.run(
                "MATCH ()-[r:HAS_PART]->() RETURN count(r) as c"
            ).single()["c"],
            "HAS_ARTICLE": session.run(
                "MATCH ()-[r:HAS_ARTICLE]->() RETURN count(r) as c"
            ).single()["c"],
            "HAS_CLAUSE": session.run(
                "MATCH ()-[r:HAS_CLAUSE]->() RETURN count(r) as c"
            ).single()["c"],
        }

    logger.info("=== Neo4j relationship counts ===")
    for rel, count in rels.items():
        logger.info(f"  {rel:15}: {count:4}")


# ── Main ──────────────────────────────────────────────────────────────────────


def load_to_neo4j() -> None:
    logger.info(f"Loading from {STRUCTURE_PATH}")
    data = json.loads(STRUCTURE_PATH.read_text(encoding="utf-8"))

    driver = GraphDatabase.driver(
        f"bolt://localhost:{neo4j_settings.neo4j_bolt_port}",
        auth=(
            neo4j_settings.neo4j_user,
            neo4j_settings.neo4j_password.get_secret_value(),
        ),
    )

    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j")

        create_constraints_and_indexes(driver)
        load_constitution(driver, data)

        chapters = data.get("chapters", [])
        logger.info(f"Loading {len(chapters)} chapters...")

        for chapter in chapters:
            load_chapter(driver, chapter)

        validate_load(driver)
        logger.info("Load complete")

    finally:
        driver.close()


if __name__ == "__main__":
    load_to_neo4j()
