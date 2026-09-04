"""Text and small-HTML ingestion with structural chunking."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from .models import DocumentMetadata, IngestedDocument, TextChunk

_ARTICLE_RE = re.compile(
    r"^(?P<label>(?:article|art\.)\s+[A-Z0-9][A-Z0-9.\-]*)(?:\s*[-:–—]\s*(?P<body>.*))?$",
    re.IGNORECASE,
)
_MARKDOWN_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_NUMBERED_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[IVXLCDM]+)[.)]?\s+\S+", re.IGNORECASE)
_SPACE_RE = re.compile(r"[ \t\f\v]+")


@dataclass(frozen=True, slots=True)
class _Block:
    kind: Literal["heading", "article", "paragraph"]
    text: str
    level: int = 0


class _StructuralHTMLParser(HTMLParser):
    """Extract only meaningful block text; scripts and styles are ignored."""

    _BLOCK_TAGS = {"p", "li", "blockquote", "td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self.title: str | None = None
        self._tag: str | None = None
        self._buffer: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "br" and self._tag:
            self._buffer.append("\n")
        if tag == "title" or tag in self._BLOCK_TAGS or re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._tag = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if not self._ignored_depth and tag == self._tag:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._tag:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        if not self._tag:
            return
        text = _normalize_inline(" ".join(self._buffer))
        tag = self._tag
        self._tag = None
        self._buffer.clear()
        if not text:
            return
        if tag == "title":
            self.title = text
        elif tag.startswith("h"):
            self.blocks.append(_Block("heading", text, int(tag[1])))
        else:
            match = _ARTICLE_RE.match(text)
            if match:
                self.blocks.append(_Block("article", match.group("label")))
                if match.group("body"):
                    self.blocks.append(_Block("paragraph", match.group("body")))
            else:
                self.blocks.append(_Block("paragraph", text))


def parse_text(content: str, metadata: DocumentMetadata) -> IngestedDocument:
    """Parse plain or Markdown-like text into structural paragraph chunks."""

    if not isinstance(content, str):
        raise TypeError("content must be a string")
    blocks: list[_Block] = []
    for raw_block in re.split(r"\n\s*\n", content.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue
        first, rest = lines[0], lines[1:]
        heading = _MARKDOWN_HEADING_RE.match(first)
        article = _ARTICLE_RE.match(first)
        if heading:
            blocks.append(_Block("heading", _normalize_inline(heading.group("title")), len(heading.group("marks"))))
            if rest:
                blocks.append(_Block("paragraph", _normalize_inline(" ".join(rest))))
        elif article:
            blocks.append(_Block("article", _normalize_inline(article.group("label"))))
            body = [article.group("body") or "", *rest]
            if any(body):
                blocks.append(_Block("paragraph", _normalize_inline(" ".join(body))))
        elif len(lines) == 1 and _looks_like_heading(first):
            blocks.append(_Block("heading", _normalize_inline(first), 2))
        else:
            blocks.append(_Block("paragraph", _normalize_inline(" ".join(lines))))
    return _build_document(blocks, metadata)


def parse_html(content: str, metadata: DocumentMetadata) -> IngestedDocument:
    """Parse a small HTML document without executing or retaining markup."""

    if not isinstance(content, str):
        raise TypeError("content must be a string")
    parser = _StructuralHTMLParser()
    parser.feed(content)
    parser.close()
    if metadata.title is None and parser.title:
        metadata = DocumentMetadata(
            source=metadata.source,
            title=parser.title,
            document_type=metadata.document_type,
            jurisdiction=metadata.jurisdiction,
            published_at=metadata.published_at,
            attributes=metadata.attributes,
        )
    return _build_document(parser.blocks, metadata)


def ingest(
    content: str,
    *,
    source: str,
    content_type: Literal["text", "html"] = "text",
    title: str | None = None,
    document_type: str | None = None,
    jurisdiction: str | None = None,
    published_at: str | None = None,
    attributes: dict[str, str] | None = None,
) -> IngestedDocument:
    """Convenience entry point for callers that do not already have metadata."""

    metadata = DocumentMetadata(
        source=source,
        title=title,
        document_type=document_type,
        jurisdiction=jurisdiction,
        published_at=published_at,
        attributes=attributes or {},
    )
    if content_type == "html":
        return parse_html(content, metadata)
    if content_type == "text":
        return parse_text(content, metadata)
    raise ValueError(f"unsupported content_type: {content_type}")


def _build_document(blocks: list[_Block], metadata: DocumentMetadata) -> IngestedDocument:
    normalized_blocks = [block for block in blocks if block.text]
    normalized_text = "\n\n".join(block.text for block in normalized_blocks)
    document_id = _stable_id(metadata.source, normalized_text)
    headings: list[str] = []
    article: str | None = None
    chunks: list[TextChunk] = []

    for block in normalized_blocks:
        if block.kind == "heading":
            level = max(1, block.level)
            headings[level - 1 :] = [block.text]
            article = None
            continue
        if block.kind == "article":
            article = block.text
            continue

        ordinal = len(chunks)
        chunks.append(
            TextChunk(
                id=_stable_id(document_id, str(ordinal), block.text),
                document_id=document_id,
                text=block.text,
                ordinal=ordinal,
                heading_path=tuple(headings),
                article=article,
                metadata=metadata,
            )
        )
    return IngestedDocument(document_id, metadata, normalized_text, tuple(chunks))


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if _NUMBERED_HEADING_RE.match(text):
        return True
    return 0 < len(words) <= 10 and text.isupper() and any(char.isalpha() for char in text)


def _normalize_inline(value: str) -> str:
    return _SPACE_RE.sub(" ", html.unescape(value)).strip()


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:20]
