"""Acquire immutable snapshots of official EUR-Lex regulatory sources."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

EUR_LEX_HOST = "eur-lex.europa.eu"
CELLAR_HOST = "publications.europa.eu"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "regulatory-intelligence-assistant/0.1 (public corpus acquisition)"


class PublicCorpusError(RuntimeError):
    """Raised when a source or downloaded snapshot violates provenance rules."""


class HttpResponse(Protocol):
    """Subset of urllib's response used by the downloader and its tests."""

    headers: Any
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> HttpResponse: ...

    def __exit__(self, *args: object) -> None: ...


Fetcher = Callable[[Request, float], HttpResponse]


def load_source_manifest(path: Path) -> dict[str, Any]:
    """Load and validate the checked-in allowlist of primary sources."""

    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_source_manifest(manifest)
    return manifest


def validate_source_manifest(manifest: dict[str, Any]) -> None:
    """Fail closed unless every source is an official, unique EUR-Lex record."""

    if manifest.get("schema_version") != "1.0":
        raise PublicCorpusError("source manifest schema_version must be 1.0")
    corpus = manifest.get("corpus", {})
    if not corpus.get("provenance_policy") or not corpus.get("rights_notice_url"):
        raise PublicCorpusError("corpus provenance policy and rights notice are required")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise PublicCorpusError("source manifest must contain at least one source")

    ids: set[str] = set()
    celex_ids: set[str] = set()
    for source in sources:
        required = {
            "id",
            "short_title",
            "celex",
            "eli",
            "official_url",
            "acquisition_url",
            "jurisdiction",
            "document_type",
        }
        missing = required - source.keys()
        if missing:
            raise PublicCorpusError(f"source is missing fields: {sorted(missing)}")
        if source["id"] in ids or source["celex"] in celex_ids:
            raise PublicCorpusError("source ids and CELEX identifiers must be unique")
        ids.add(source["id"])
        celex_ids.add(source["celex"])
        _require_official_url(source["official_url"])
        _require_acquisition_url(source["acquisition_url"])
        if f"CELEX:{source['celex']}" not in source["official_url"]:
            raise PublicCorpusError(f"official_url does not match CELEX {source['celex']}")
        if not source["acquisition_url"].endswith(f"/resource/celex/{source['celex']}"):
            raise PublicCorpusError(f"acquisition_url does not match CELEX {source['celex']}")
        eli = urlparse(source["eli"])
        if eli.scheme != "http" or eli.netloc != "data.europa.eu":
            raise PublicCorpusError(f"invalid ELI identifier for {source['id']}")


def acquire_corpus(
    source_manifest_path: Path,
    output_dir: Path,
    *,
    timeout: float = 30.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    fetcher: Fetcher | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Download all allowlisted sources and write a provenance sidecar."""

    manifest = load_source_manifest(source_manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetcher or _urlopen
    clock = now or (lambda: datetime.now(UTC))
    snapshots = [
        acquire_source(
            source,
            output_dir,
            timeout=timeout,
            max_bytes=max_bytes,
            fetcher=fetch,
            retrieved_at=clock(),
        )
        for source in manifest["sources"]
    ]
    provenance = {
        "schema_version": "1.0",
        "source_manifest": source_manifest_path.name,
        "source_manifest_sha256": hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
        "generated_at": clock().isoformat().replace("+00:00", "Z"),
        "rights_notice_url": manifest["corpus"]["rights_notice_url"],
        "snapshots": snapshots,
    }
    provenance_path = output_dir / "provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return provenance


def acquire_source(
    source: dict[str, Any],
    output_dir: Path,
    *,
    timeout: float,
    max_bytes: int,
    fetcher: Fetcher,
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Download one source after validating origin, type and size."""

    url = source["acquisition_url"]
    _require_acquisition_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xhtml+xml",
            "Accept-Language": "eng",
            "Accept-Max-Cs-Size": str(max_bytes),
        },
    )
    with fetcher(request, timeout) as response:
        resolved_url = response.geturl()
        _require_acquisition_url(resolved_url, allow_cellar_resource=True)
        if response.status != 200:
            raise PublicCorpusError(f"unexpected HTTP status for {source['id']}: {response.status}")
        content_type = response.headers.get_content_type().lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise PublicCorpusError(f"unexpected content type for {source['id']}: {content_type}")
        body = response.read(max_bytes + 1)

    if len(body) > max_bytes:
        raise PublicCorpusError(f"source exceeds {max_bytes} bytes: {source['id']}")
    if not body.strip():
        raise PublicCorpusError(f"empty response for {source['id']}")
    prefix = body.lstrip()[:100].lower()
    if not (prefix.startswith(b"<?xml") or b"<html" in prefix):
        raise PublicCorpusError(f"downloaded document is not structured markup: {source['id']}")

    filename = f"{source['id']}.html"
    destination = output_dir / filename
    destination.write_bytes(body)
    return {
        "source_id": source["id"],
        "celex": source["celex"],
        "eli": source["eli"],
        "eur_lex_url": source["official_url"],
        "requested_url": url,
        "resolved_url": resolved_url,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "content_type": content_type,
        "file": filename,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _require_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != EUR_LEX_HOST:
        raise PublicCorpusError(f"source URL is not official EUR-Lex HTTPS: {url}")


def _require_acquisition_url(url: str, *, allow_cellar_resource: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != CELLAR_HOST:
        raise PublicCorpusError(f"source URL is not official Cellar HTTPS: {url}")
    expected_prefix = "/resource/cellar/" if allow_cellar_resource else "/resource/celex/"
    if not parsed.path.startswith(expected_prefix):
        raise PublicCorpusError(f"unexpected Cellar resource path: {url}")


class _SafeCellarRedirectHandler(HTTPRedirectHandler):
    """Keep Cellar redirects on its official host and upgrade its HTTP locations."""

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        parsed = urlsplit(new_url)
        if parsed.hostname != CELLAR_HOST or not parsed.path.startswith("/resource/cellar/"):
            raise PublicCorpusError(f"Cellar redirected to an untrusted URL: {new_url}")
        safe_url = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        return super().redirect_request(
            request, file_pointer, code, message, headers, safe_url
        )


def _urlopen(request: Request, timeout: float) -> HttpResponse:
    return build_opener(_SafeCellarRedirectHandler).open(request, timeout=timeout)
