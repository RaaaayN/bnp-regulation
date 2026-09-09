import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUESTS = Counter(
    "ria_http_requests_total",
    "Number of HTTP requests handled by the application.",
    ("method", "path", "status"),
)
LATENCY = Histogram(
    "ria_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("method", "path"),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - started_at)
        return response


async def prometheus_metrics(_: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
