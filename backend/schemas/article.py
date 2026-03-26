from pydantic import BaseModel, HttpUrl, field_validator
from datetime import datetime


class ArticleRequest(BaseModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: HttpUrl) -> HttpUrl:
        if v.scheme not in ("http", "https"):
            raise ValueError("URL must use http or https")
        return v


class Article(BaseModel):
    url: str
    title: str
    text: str
    author: str | None = None
    published_date: datetime | None = None
    source_domain: str
    char_count: int
    extraction_method: str  # "trafilatura" | "beautifulsoup"
