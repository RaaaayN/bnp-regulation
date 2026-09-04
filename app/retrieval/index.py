"""Dependency-free BM25-like and token-overlap retrieval."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from threading import RLock
from typing import Iterable

from app.ingestion import IngestedDocument, TextChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A ranked passage whose origin can be rendered directly to a user."""

    chunk: TextChunk
    score: float
    lexical_score: float
    similarity_score: float

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def source(self) -> str:
        return self.chunk.metadata.source

    @property
    def citation(self) -> str:
        return self.chunk.citation


class InMemoryIndex:
    """Thread-safe, replaceable index intended for small knowledge bases and tests."""

    def __init__(self) -> None:
        self._chunks: dict[str, TextChunk] = {}
        self._tokens: dict[str, tuple[str, ...]] = {}
        self._documents: dict[str, set[str]] = {}
        self._lock = RLock()

    def add(self, document: IngestedDocument) -> None:
        """Add or replace a document atomically."""

        with self._lock:
            self.remove(document.id)
            ids: set[str] = set()
            for chunk in document.chunks:
                self._chunks[chunk.id] = chunk
                self._tokens[chunk.id] = tokenize(chunk.text)
                ids.add(chunk.id)
            self._documents[document.id] = ids

    def add_many(self, documents: Iterable[IngestedDocument]) -> None:
        for document in documents:
            self.add(document)

    def remove(self, document_id: str) -> bool:
        """Remove one document, returning whether it existed."""

        with self._lock:
            chunk_ids = self._documents.pop(document_id, None)
            if chunk_ids is None:
                return False
            for chunk_id in chunk_ids:
                self._chunks.pop(chunk_id, None)
                self._tokens.pop(chunk_id, None)
            return True

    def snapshot(self) -> tuple[tuple[TextChunk, tuple[str, ...]], ...]:
        """Return a stable snapshot in insertion-independent order."""

        with self._lock:
            return tuple(
                (self._chunks[key], self._tokens[key]) for key in sorted(self._chunks)
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._chunks)


class HybridRetriever:
    """Rank chunks using BM25 plus Jaccard token similarity.

    Scores are normalized into [0, 1]. Results below ``evidence_threshold`` are
    excluded, so an empty list has the explicit meaning “insufficient evidence”.
    """

    def __init__(
        self,
        index: InMemoryIndex | None = None,
        *,
        lexical_weight: float = 0.75,
        evidence_threshold: float = 0.12,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not 0.0 <= lexical_weight <= 1.0:
            raise ValueError("lexical_weight must be between 0 and 1")
        if not 0.0 <= evidence_threshold <= 1.0:
            raise ValueError("evidence_threshold must be between 0 and 1")
        self.index = index or InMemoryIndex()
        self.lexical_weight = lexical_weight
        self.evidence_threshold = evidence_threshold
        self.k1 = k1
        self.b = b

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        snapshot = self.index.snapshot()
        if not snapshot:
            return []

        document_frequency = Counter()
        for _, tokens in snapshot:
            document_frequency.update(set(tokens))
        average_length = sum(len(tokens) for _, tokens in snapshot) / len(snapshot)
        query_counts = Counter(query_tokens)
        raw_lexical = [
            _bm25(tokens, query_counts, document_frequency, len(snapshot), average_length, self.k1, self.b)
            for _, tokens in snapshot
        ]
        max_lexical = max(raw_lexical, default=0.0)

        results: list[SearchResult] = []
        query_set = set(query_tokens)
        for (chunk, tokens), raw_score in zip(snapshot, raw_lexical, strict=True):
            lexical = raw_score / max_lexical if max_lexical else 0.0
            token_set = set(tokens)
            similarity = len(query_set & token_set) / len(query_set | token_set) if token_set else 0.0
            score = self.lexical_weight * lexical + (1 - self.lexical_weight) * similarity
            if score >= self.evidence_threshold:
                results.append(SearchResult(chunk, score, lexical, similarity))

        results.sort(key=lambda result: (-result.score, result.chunk.id))
        return results[:limit]


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize case- and accent-insensitively without language-specific state."""

    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(char for char in normalized if not unicodedata.combining(char))
    return tuple(_TOKEN_RE.findall(ascii_like))


def _bm25(
    tokens: tuple[str, ...],
    query_counts: Counter[str],
    document_frequency: Counter[str],
    collection_size: int,
    average_length: float,
    k1: float,
    b: float,
) -> float:
    frequencies = Counter(tokens)
    length_ratio = len(tokens) / average_length if average_length else 0.0
    score = 0.0
    for term, query_frequency in query_counts.items():
        frequency = frequencies[term]
        if not frequency:
            continue
        df = document_frequency[term]
        inverse_document_frequency = math.log(1 + (collection_size - df + 0.5) / (df + 0.5))
        saturation = frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * length_ratio))
        score += inverse_document_frequency * saturation * query_frequency
    return score
