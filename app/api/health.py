from datetime import UTC, datetime

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["operations"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
    }

