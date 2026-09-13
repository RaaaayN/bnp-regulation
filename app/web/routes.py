"""Routes for the self-contained portfolio demo."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

_APP_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _APP_ROOT.parent
_TEMPLATE = _APP_ROOT / "templates" / "demo.html"
_REPORT_CANDIDATES = (
    _PROJECT_ROOT / "artifacts" / "evaluation-report-v2.json",
    _PROJECT_ROOT / "artifacts" / "evaluation-report.json",
    _PROJECT_ROOT / "reports" / "evaluation_report.json",
    _PROJECT_ROOT / "artifacts" / "evaluation_report.json",
    _PROJECT_ROOT / "evaluation_report.json",
)


@router.get("/", response_class=HTMLResponse)
@router.get("/demo", response_class=HTMLResponse)
async def demo() -> HTMLResponse:
    """Render the interactive demonstration dashboard."""

    return HTMLResponse(_TEMPLATE.read_text(encoding="utf-8"))


def _find_report() -> Path | None:
    configured = os.getenv("RIA_METRICS_REPORT")
    candidates = ((Path(configured),) if configured else ()) + _REPORT_CANDIDATES
    return next((path for path in candidates if path.is_file()), None)


@router.get("/demo/metrics")
async def demo_metrics() -> dict[str, Any]:
    """Expose a benchmark report when one is available to the process."""

    report = _find_report()
    if report is None:
        return {"available": False, "metrics": {}, "source": None}
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "metrics": {}, "source": report.name}
    if not isinstance(payload, dict):
        return {"available": False, "metrics": {}, "source": report.name}
    return {"available": True, "metrics": payload, "source": report.name}
