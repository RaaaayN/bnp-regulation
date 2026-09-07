"""Value objects emitted by the ingestion pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Metadata shared by every chunk of an ingested document."""

    source: str
    title: str | None = None
    document_type: str | None = None
    jurisdiction: str | None = None
    published_at: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("metadata.source must not be empty")
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(sorted(self.attributes.items()))),
        )


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A searchable structural unit with a stable identifier and citation path."""

    id: str
    document_id: str
    text: str
    ordinal: int
    heading_path: tuple[str, ...]
    article: str | None
    metadata: DocumentMetadata

    @property
    def citation(self) -> str:
        parts = [self.metadata.source]
        parts.extend(self.heading_path)
        if self.article and self.article not in self.heading_path:
            parts.append(self.article)
        return " > ".join(parts)


@dataclass(frozen=True, slots=True)
class IngestedDocument:
    """Normalized document and its independently searchable chunks."""

    id: str
    metadata: DocumentMetadata
    text: str
    chunks: tuple[TextChunk, ...]
