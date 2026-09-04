"""Evidence gate for claims produced by analysis services."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

from app.domain import (
    Citation,
    Claim,
    ClaimReview,
    RegulatorySection,
    ReviewResult,
    ReviewStatus,
)

_SPACE_RE = re.compile(r"\s+")


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return _SPACE_RE.sub(" ", value).strip()


class ClaimReviewer:
    """Verify citation excerpts and apply a fail-closed evidence policy.

    A citation is valid only when its document and section exist, optional
    version/page metadata agree, and the normalised quote occurs verbatim in the
    source.  This intentionally avoids fuzzy matching: audit evidence must be
    reproducible, not merely similar.
    """

    def review_claims(
        self,
        claims: Iterable[Claim],
        sources: Iterable[RegulatorySection] | Mapping[str, RegulatorySection | str],
        *,
        remove_unsupported: bool = True,
    ) -> ReviewResult:
        source_index = self._index_sources(sources)
        reviews = tuple(self.review_claim(claim, source_index) for claim in claims)
        accepted: list[Claim] = []
        flagged: list[ClaimReview] = []
        for review in reviews:
            if review.status is ReviewStatus.SUPPORTED:
                accepted.append(review.claim)
            elif review.status is ReviewStatus.PARTIALLY_SUPPORTED:
                flagged.append(review)
                # A partially supported claim may remain visible, but never
                # without an explicit flag.
                if not remove_unsupported:
                    accepted.append(review.claim)
            else:
                flagged.append(review)
                if not remove_unsupported:
                    accepted.append(review.claim)
        return ReviewResult(
            accepted_claims=tuple(accepted),
            flagged_claims=tuple(flagged),
            reviews=reviews,
        )

    def review_claim(
        self,
        claim: Claim,
        sources: Iterable[RegulatorySection]
        | Mapping[str, RegulatorySection | str]
        | Mapping[str, tuple[RegulatorySection, ...]],
    ) -> ClaimReview:
        source_index = (
            sources if self._is_index(sources) else self._index_sources(sources)  # type: ignore[arg-type]
        )
        supported: list[Citation] = []
        unsupported: list[Citation] = []
        for citation in claim.citations:
            if self._citation_is_supported(citation, source_index):  # type: ignore[arg-type]
                supported.append(citation)
            else:
                unsupported.append(citation)

        if supported and not unsupported:
            status = ReviewStatus.SUPPORTED
            reason = "Every citation resolves to an exact passage in its source."
        elif supported:
            status = ReviewStatus.PARTIALLY_SUPPORTED
            reason = "At least one citation could not be verified against its source."
        else:
            status = ReviewStatus.UNSUPPORTED
            reason = (
                "The claim has no citation."
                if not claim.citations
                else "No citation could be verified against its source."
            )
        return ClaimReview(
            claim=claim,
            status=status,
            supported_citations=tuple(supported),
            unsupported_citations=tuple(unsupported),
            reason=reason,
        )

    @staticmethod
    def _is_index(value: object) -> bool:
        if not isinstance(value, Mapping):
            return False
        return all(
            isinstance(item, tuple)
            and all(isinstance(source, RegulatorySection) for source in item)
            for item in value.values()
        )

    @staticmethod
    def _index_sources(
        sources: Iterable[RegulatorySection] | Mapping[str, RegulatorySection | str],
    ) -> dict[str, tuple[RegulatorySection, ...]]:
        index: dict[str, list[RegulatorySection]] = {}
        if isinstance(sources, Mapping):
            iterable: list[RegulatorySection] = []
            for key, value in sources.items():
                if isinstance(value, RegulatorySection):
                    iterable.append(value)
                elif isinstance(value, str):
                    try:
                        document_id, section_id = key.split(":", 1)
                    except ValueError as exc:
                        raise ValueError(
                            "string source keys must use 'document_id:section_id'"
                        ) from exc
                    iterable.append(
                        RegulatorySection(
                            document_id=document_id,
                            section_id=section_id,
                            text=value,
                        )
                    )
                else:
                    raise TypeError("source mappings must contain RegulatorySection or str values")
        else:
            iterable = list(sources)
        for source in iterable:
            index.setdefault(source.source_id, []).append(source)
        return {key: tuple(value) for key, value in index.items()}

    @staticmethod
    def _citation_is_supported(
        citation: Citation,
        sources: Mapping[str, tuple[RegulatorySection, ...]],
    ) -> bool:
        quote = _normalise(citation.quote)
        if not quote:
            return False
        for source in sources.get(citation.source_id, ()):
            if citation.version is not None and citation.version != source.version:
                continue
            if citation.page is not None and citation.page != source.page:
                continue
            if quote in _normalise(source.text):
                return True
        return False
