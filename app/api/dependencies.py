from fastapi import Request

from app.retrieval import HybridRetriever


def get_retriever(request: Request) -> HybridRetriever:
    return request.app.state.retriever
