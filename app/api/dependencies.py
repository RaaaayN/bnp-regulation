from fastapi import Request

from app.retrieval import LexicalRetriever


def get_retriever(request: Request) -> LexicalRetriever:
    return request.app.state.retriever
