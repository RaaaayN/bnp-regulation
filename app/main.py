from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.config import get_settings
from app.retrieval import HybridRetriever, InMemoryIndex


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    application.state.retriever = HybridRetriever(
        InMemoryIndex(), evidence_threshold=settings.evidence_threshold
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Evidence-grounded regulatory change analysis API.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
