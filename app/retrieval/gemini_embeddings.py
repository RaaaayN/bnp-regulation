"""Optional Gemini embeddings for semantic regulatory retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from google import genai
from google.genai import types
from pydantic import SecretStr

from app.config import Settings, get_settings

_CACHE_VERSION = "gemini-embeddings-v1"


class GeminiEmbeddingUnavailable(RuntimeError):
    """Raised when optional semantic retrieval has not been configured."""


class GeminiEmbeddingError(RuntimeError):
    """Raised when an embedding cannot be produced after bounded retries."""


class _Models(Protocol):
    def embed_content(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    models: _Models


class GeminiEmbedder:
    """Produce query/document embeddings with task-aware cache keys."""

    def __init__(
        self,
        *,
        api_key: SecretStr | str | None = None,
        model: str = "gemini-embedding-001",
        dimensions: int | None = 768,
        cache_dir: Path | str = Path("artifacts/gemini-cache/embeddings"),
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        client: _Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if dimensions is not None and dimensions < 1:
            raise ValueError("dimensions must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")

        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if client is None and not secret:
            raise GeminiEmbeddingUnavailable(
                "Gemini embeddings are disabled: configure GEMINI_API_KEY or RIA_GEMINI_API_KEY"
            )
        self._client: _Client = client or genai.Client(api_key=secret)
        self.model = model
        self.dimensions = dimensions
        self.cache_dir = Path(cache_dir)
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> GeminiEmbedder:
        configured = settings or get_settings()
        return cls(
            api_key=configured.gemini_api_key,
            model=configured.gemini_embedding_model,
            dimensions=configured.gemini_embedding_dimensions,
            cache_dir=configured.gemini_cache_dir / "embeddings",
            max_attempts=configured.gemini_max_attempts,
            backoff_seconds=configured.gemini_backoff_seconds,
        )

    def embed_query(self, text: str) -> tuple[float, ...]:
        """Embed a search query using Gemini's retrieval-query task space."""

        return self._embed(text, task_type="RETRIEVAL_QUERY")

    def embed_document(self, text: str, *, title: str | None = None) -> tuple[float, ...]:
        """Embed a corpus passage using Gemini's retrieval-document task space."""

        return self._embed(text, task_type="RETRIEVAL_DOCUMENT", title=title)

    def embed_documents(
        self, documents: Iterable[str]
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed_document(document) for document in documents)

    def _embed(
        self, text: str, *, task_type: str, title: str | None = None
    ) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("embedding input cannot be empty")
        path = self._cache_path(text, task_type=task_type, title=title)
        cached = self._read_cache(path)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self._client.models.embed_content(
                    model=self.model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        title=title,
                        output_dimensionality=self.dimensions,
                    ),
                )
                embeddings = getattr(response, "embeddings", None)
                values = embeddings[0].values if embeddings else None
                if not values:
                    raise ValueError("Gemini returned no embedding values")
                vector = tuple(float(value) for value in values)
                self._write_cache(path, vector)
                return vector
            except Exception as exc:  # SDK transport and response errors share no stable base class
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self._sleep(self.backoff_seconds * (2**attempt))
        raise GeminiEmbeddingError(
            f"Gemini embedding failed after {self.max_attempts} attempt(s)"
        ) from last_error

    def _cache_path(self, text: str, *, task_type: str, title: str | None) -> Path:
        material = {
            "version": _CACHE_VERSION,
            "model": self.model,
            "dimensions": self.dimensions,
            "task_type": task_type,
            "title": title,
            "text": text,
        }
        digest = hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.cache_dir / f"{digest}.json"

    @staticmethod
    def _read_cache(path: Path) -> tuple[float, ...] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            vector = tuple(float(item) for item in value["embedding"])
            return vector or None
        except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_cache(path: Path, vector: tuple[float, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"embedding": vector}) + "\n", encoding="utf-8")
        temporary.replace(path)


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Return cosine similarity, with zero for either zero-magnitude vector."""

    left_vector = tuple(left)
    right_vector = tuple(right)
    if len(left_vector) != len(right_vector):
        raise ValueError("embedding dimensions must match")
    dot_product = sum(a * b for a, b in zip(left_vector, right_vector, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left_vector))
    right_norm = math.sqrt(sum(value * value for value in right_vector))
    if not left_norm or not right_norm:
        return 0.0
    return dot_product / (left_norm * right_norm)
