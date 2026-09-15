"""In-memory lexical retrieval with explicit evidence thresholds."""

from .gemini_embeddings import GeminiEmbedder, cosine_similarity
from .index import InMemoryIndex, LexicalRetriever, SearchResult

__all__ = [
    "GeminiEmbedder",
    "InMemoryIndex",
    "LexicalRetriever",
    "SearchResult",
    "cosine_similarity",
]
