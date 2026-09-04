"""Deterministic ingestion primitives for regulatory documents."""

from .models import DocumentMetadata, IngestedDocument, TextChunk
from .parser import ingest, parse_html, parse_text

__all__ = [
    "DocumentMetadata",
    "IngestedDocument",
    "TextChunk",
    "ingest",
    "parse_html",
    "parse_text",
]
