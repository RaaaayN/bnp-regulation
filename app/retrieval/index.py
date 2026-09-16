"""Dependency-free BM25-like and token-overlap retrieval."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from threading import RLock

from app.ingestion import IngestedDocument, TextChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "au",
        "aux",
        "avec",
        "be",
        "by",
        "ce",
        "ces",
        "dans",
        "de",
        "des",
        "do",
        "does",
        "du",
        "en",
        "est",
        "et",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "la",
        "le",
        "les",
        "of",
        "on",
        "or",
        "ou",
        "par",
        "pour",
        "que",
        "quel",
        "quelle",
        "quelles",
        "quels",
        "qui",
        "sur",
        "that",
        "the",
        "their",
        "to",
        "un",
        "une",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A ranked passage whose origin can be rendered directly to a user."""

    chunk: TextChunk
    score: float
    lexical_score: float
    similarity_score: float
    ranking_score: float
    query_coverage: float

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
            return tuple((self._chunks[key], self._tokens[key]) for key in sorted(self._chunks))

    def __len__(self) -> int:
        with self._lock:
            return len(self._chunks)


class LexicalRetriever:
    """Rank chunks using two lexical signals: BM25 and Jaccard token overlap.

    Both constituent signals are lexical; no embedding or vector index is used
    by this code path.
    BM25 is normalized only for ranking. Admission is independent of that
    query-relative maximum: a result must cover ``minimum_query_coverage`` of
    the query's informative terms. Stop-word-only queries therefore return no
    evidence. The public score also includes coverage and stays in [0, 1].
    """

    def __init__(
        self,
        index: InMemoryIndex | None = None,
        *,
        minimum_query_coverage: float,
        lexical_weight: float = 0.75,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not 0.0 <= lexical_weight <= 1.0:
            raise ValueError("lexical_weight must be between 0 and 1")
        if not 0.0 <= minimum_query_coverage <= 1.0:
            raise ValueError("minimum_query_coverage must be between 0 and 1")
        self.index = index or InMemoryIndex()
        self.lexical_weight = lexical_weight
        self.minimum_query_coverage = minimum_query_coverage
        self.k1 = k1
        self.b = b

    def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        ranking_query_tokens = tokenize(query)
        informative_query_tokens = tuple(
            token for token in ranking_query_tokens if token not in _QUERY_STOP_WORDS
        )
        if not informative_query_tokens:
            return []
        snapshot = self.index.snapshot()
        if not snapshot:
            return []

        document_frequency = Counter()
        for _, tokens in snapshot:
            document_frequency.update(set(tokens))
        average_length = sum(len(tokens) for _, tokens in snapshot) / len(snapshot)
        query_counts = Counter(ranking_query_tokens)
        raw_lexical = [
            _bm25(
                tokens,
                query_counts,
                document_frequency,
                len(snapshot),
                average_length,
                self.k1,
                self.b,
            )
            for _, tokens in snapshot
        ]
        max_lexical = max(raw_lexical, default=0.0)

        results: list[SearchResult] = []
        ranking_query_set = set(ranking_query_tokens)
        informative_query_set = set(informative_query_tokens)
        for (chunk, tokens), raw_score in zip(snapshot, raw_lexical, strict=True):
            lexical = raw_score / max_lexical if max_lexical else 0.0
            token_set = set(tokens)
            similarity = (
                len(ranking_query_set & token_set) / len(ranking_query_set | token_set)
                if token_set
                else 0.0
            )
            query_coverage = len(informative_query_set & token_set) / len(
                informative_query_set
            )
            ranking_score = self.lexical_weight * lexical + (
                1 - self.lexical_weight
            ) * similarity
            score = ranking_score * query_coverage
            if raw_score > 0 and query_coverage >= self.minimum_query_coverage:
                results.append(
                    SearchResult(
                        chunk,
                        score,
                        lexical,
                        similarity,
                        ranking_score,
                        query_coverage,
                    )
                )

        results.sort(key=lambda result: (-result.ranking_score, result.chunk.id))
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
