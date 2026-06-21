
from pydantic import BaseModel, Field

class OCRPage(BaseModel):
    page_number: int = Field(gt=0)
    page_name: str
    text: str

class PageIndexEntry(BaseModel):
    page_number: int = Field(gt=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)