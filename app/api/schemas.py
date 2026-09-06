from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IngestRequest(ApiModel):
    source: str = Field(min_length=1)
    content: str = Field(min_length=1)
    content_type: Literal["text", "html"] = "text"
    title: str | None = None
    document_type: str | None = None
    jurisdiction: str | None = None
    published_at: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class IngestResponse(ApiModel):
    document_id: str
    chunks_indexed: int
    injection_suspected: bool
    redacted_categories: tuple[str, ...]


class SearchRequest(ApiModel):
    query: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1, le=50)


class SearchHit(ApiModel):
    chunk_id: str
    document_id: str
    text: str
    citation: str
    score: float


class SearchResponse(ApiModel):
    status: Literal["evidence_found", "insufficient_evidence"]
    results: tuple[SearchHit, ...]
