from typing import Optional

from pydantic import BaseModel, Field


class OCRPage(BaseModel):
    page_number: int = Field(gt=0)
    page_name: str
    text: str


class PageIndexEntry(BaseModel):
    page_number: int = Field(gt=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


# Constitution Schema
class Clause(BaseModel):
    clause_number: int
    text: str


class Article(BaseModel):
    article_number: int
    article_title: str
    clauses: list[Clause]


class Part(BaseModel):
    part_number: int
    part_name: str
    articles: list[Article]


class Chapter(BaseModel):
    chapter_number: int
    chapter_name: str
    has_parts: bool
    parts: list[Part] | None = None
    articles: list[Article] | None = None  # only when has_parts=False


class CoverPage(BaseModel):
    title: str
    publisher: str
    year: int


class ArrangementEntry(BaseModel):
    article_number: int
    article_title: str


class ArrangementOfArticles(BaseModel):
    entries: list[ArrangementEntry]


class ConstitutionStructure(BaseModel):
    cover_page: CoverPage
    arrangement_of_articles: ArrangementOfArticles
    chapters: list[Chapter]


class VerificationResult(BaseModel):
    is_correct: bool
    chapter_count: int
    article_count: int
    issues: list[str]
    corrected_structure: ConstitutionStructure | None = None


class ChapterSkeleton(BaseModel):
    chapter_number: int
    chapter_name: str
    has_parts: bool
    part_names: Optional[list[str]] = None  # just names, no articles yet


class ConstitutionSkeleton(BaseModel):
    chapters: list[ChapterSkeleton]


class ChapterFull(BaseModel):
    chapter_number: int
    chapter_name: str
    has_parts: bool
    parts: Optional[list[Part]] = None
    articles: Optional[list[Article]] = None
