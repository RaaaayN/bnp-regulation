from __future__ import annotations

import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.request import Request

import pytest

from app.ingestion.public_corpus import (
    PublicCorpusError,
    acquire_corpus,
    load_source_manifest,
    validate_source_manifest,
)


class FakeResponse:
    def __init__(self, url: str, body: bytes, content_type: str = "text/html") -> None:
        self._url = url
        self._body = body
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, amount: int = -1) -> bytes:
        return self._body[:amount]

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_checked_in_manifest_contains_expected_primary_sources() -> None:
    manifest = load_source_manifest(Path("datasets/public_sources.json"))

    assert {source["celex"] for source in manifest["sources"]} == {
        "32022R2554",
        "32016R0679",
        "32024R1689",
        "32023R1114",
        "32013R0575",
    }
    assert all("eur-lex.europa.eu" in source["official_url"] for source in manifest["sources"])


def test_acquisition_writes_bytes_and_complete_provenance(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "corpus": {
            "provenance_policy": "official sources only",
            "rights_notice_url": "https://eur-lex.europa.eu/content/legal-notice/legal-notice.html",
        },
        "sources": [
            {
                "id": "example",
                "short_title": "Example",
                "celex": "32022R2554",
                "eli": "http://data.europa.eu/eli/reg/2022/2554/oj",
                "official_url": (
                    "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
                    "?uri=CELEX:32022R2554"
                ),
                "acquisition_url": (
                    "https://publications.europa.eu/resource/celex/32022R2554"
                ),
                "jurisdiction": "European Union",
                "document_type": "Regulation",
            }
        ],
    }
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    body = b"<html><body>Official regulation content</body></html>"

    def fetcher(request: Request, timeout: float) -> FakeResponse:
        assert request.headers["User-agent"].startswith("regulatory-intelligence-assistant/")
        assert timeout == 4.0
        assert request.headers["Accept-language"] == "eng"
        return FakeResponse(
            "https://publications.europa.eu/resource/cellar/example/DOC_1", body
        )

    output = tmp_path / "raw"
    provenance = acquire_corpus(
        manifest_path,
        output,
        timeout=4.0,
        fetcher=fetcher,
        now=lambda: datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
    )

    snapshot = provenance["snapshots"][0]
    assert (output / "example.html").read_bytes() == body
    assert snapshot["sha256"] == "7f3d8b6da10f662320bf2c6b62af8d1349ad87ae7c6a20597c6bfd905fd21b14"
    assert snapshot["retrieved_at"] == "2026-09-15T12:00:00Z"
    assert json.loads((output / "provenance.json").read_text()) == provenance


def test_manifest_rejects_non_official_source() -> None:
    manifest = {
        "schema_version": "1.0",
        "corpus": {"provenance_policy": "x", "rights_notice_url": "x"},
        "sources": [
            {
                "id": "bad",
                "short_title": "Bad",
                "celex": "32022R2554",
                "eli": "http://data.europa.eu/eli/reg/2022/2554/oj",
                "official_url": "https://example.com/?uri=CELEX:32022R2554",
                "acquisition_url": (
                    "https://publications.europa.eu/resource/celex/32022R2554"
                ),
                "jurisdiction": "EU",
                "document_type": "Regulation",
            }
        ],
    }

    with pytest.raises(PublicCorpusError, match="not official EUR-Lex"):
        validate_source_manifest(manifest)


def test_acquisition_rejects_redirect_away_from_cellar(tmp_path: Path) -> None:
    manifest = load_source_manifest(Path("datasets/public_sources.json"))
    manifest["sources"] = manifest["sources"][:1]
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fetcher(_request: Request, _timeout: float) -> FakeResponse:
        return FakeResponse("https://attacker.example/document", b"<html>content</html>")

    with pytest.raises(PublicCorpusError, match="not official Cellar"):
        acquire_corpus(manifest_path, tmp_path / "raw", fetcher=fetcher)
