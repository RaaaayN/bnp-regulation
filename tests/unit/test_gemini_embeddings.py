from pathlib import Path
from types import SimpleNamespace

import pytest

from app.retrieval.gemini_embeddings import (
    GeminiEmbedder,
    GeminiEmbeddingUnavailable,
    cosine_similarity,
)


class FakeModels:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[dict[str, object]] = []

    def embed_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self.vectors.pop(0))]
        )


def test_refuses_to_start_without_api_key() -> None:
    with pytest.raises(GeminiEmbeddingUnavailable, match="disabled"):
        GeminiEmbedder(api_key=None)


def test_uses_distinct_retrieval_tasks_and_cache_keys(tmp_path: Path) -> None:
    models = FakeModels([[1.0, 0.0], [0.0, 1.0]])
    embedder = GeminiEmbedder(
        client=SimpleNamespace(models=models), dimensions=2, cache_dir=tmp_path
    )

    assert embedder.embed_query("incident reporting") == (1.0, 0.0)
    assert embedder.embed_query("incident reporting") == (1.0, 0.0)
    assert embedder.embed_document("incident reporting", title="DORA") == (0.0, 1.0)

    assert len(models.calls) == 2
    query_config = models.calls[0]["config"]
    document_config = models.calls[1]["config"]
    assert query_config.task_type == "RETRIEVAL_QUERY"
    assert document_config.task_type == "RETRIEVAL_DOCUMENT"
    assert document_config.title == "DORA"
    assert query_config.output_dimensionality == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_cosine_similarity_handles_direction_zero_and_dimensions() -> None:
    assert cosine_similarity((1, 0), (1, 0)) == pytest.approx(1.0)
    assert cosine_similarity((1, 0), (0, 1)) == pytest.approx(0.0)
    assert cosine_similarity((0, 0), (1, 0)) == 0.0
    with pytest.raises(ValueError, match="dimensions"):
        cosine_similarity((1,), (1, 2))
