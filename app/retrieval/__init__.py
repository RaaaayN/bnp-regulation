"""In-memory lexical retrieval with explicit evidence thresholds."""

from .index import InMemoryIndex, LexicalRetriever, SearchResult

__all__ = [
    "GeminiEmbedder",
    "InMemoryIndex",
    "LexicalRetriever",
    "SearchResult",
    "cosine_similarity",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Load the optional Gemini SDK only when an embedding symbol is requested."""

    if name in {"GeminiEmbedder", "cosine_similarity"}:
        from .gemini_embeddings import GeminiEmbedder, cosine_similarity

        return {"GeminiEmbedder": GeminiEmbedder, "cosine_similarity": cosine_similarity}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
