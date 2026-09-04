"""Conservative, explainable mapping from changes to internal artefacts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from app.domain import Citation, Claim, ImpactAssessment, ImpactCandidate, SectionChange

_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "shall",
        "should",
        "must",
    }
)


def _tokens(text: str) -> set[str]:
    return {
        word.casefold()
        for word in _WORD_RE.findall(text)
        if len(word) > 2 and word.casefold() not in _STOP_WORDS
    }


class ImpactAnalysisService:
    """Rank explicitly configured internal items using auditable keyword overlap.

    It reports *potential* impacts only.  No assessment asserts that a policy or
    control must be changed; that determination remains with a human reviewer.
    """

    def analyse(
        self,
        change: SectionChange,
        candidates: Iterable[ImpactCandidate],
        *,
        minimum_relevance: float = 0.2,
    ) -> list[ImpactAssessment]:
        if not 0.0 <= minimum_relevance <= 1.0:
            raise ValueError("minimum_relevance must be between 0 and 1")
        regulatory_source = change.current_section or change.previous_section
        if regulatory_source is None:
            return []
        change_tokens = _tokens(regulatory_source.text)
        assessments: list[ImpactAssessment] = []
        for candidate in candidates:
            configured_keywords = _tokens(" ".join(candidate.keywords))
            candidate_tokens = configured_keywords or _tokens(candidate.name)
            if not candidate_tokens:
                continue
            overlap = sorted(change_tokens & candidate_tokens)
            relevance = round(len(overlap) / len(candidate_tokens), 4)
            if relevance < minimum_relevance:
                continue
            confidence = round(
                min(0.98, 0.5 + (0.4 * relevance) + (0.08 if candidate.source else 0)), 4
            )
            rationale = (
                f"Potential impact inferred from shared concepts: {', '.join(overlap)}. "
                "Human validation is required."
            )
            citations = [
                Citation(
                    document_id=regulatory_source.document_id,
                    section_id=regulatory_source.section_id,
                    quote=regulatory_source.text,
                    page=regulatory_source.page,
                    version=regulatory_source.version,
                )
            ]
            if candidate.source:
                citations.append(
                    Citation(
                        document_id=candidate.source.document_id,
                        section_id=candidate.source.section_id,
                        quote=candidate.source.text,
                        page=candidate.source.page,
                        version=candidate.source.version,
                    )
                )
            digest = hashlib.sha256(f"{change.change_id}|{candidate.item_id}".encode()).hexdigest()[
                :12
            ]
            claim = Claim(
                claim_id=f"impact-claim-{digest}",
                text=f"{candidate.name} may be impacted by this regulatory change.",
                citations=tuple(citations),
            )
            assessments.append(
                ImpactAssessment(
                    change_id=change.change_id,
                    candidate=candidate,
                    relevance_score=relevance,
                    confidence_score=confidence,
                    rationale=rationale,
                    claims=(claim,),
                )
            )
        return sorted(
            assessments,
            key=lambda item: (-item.relevance_score, item.candidate.item_id),
        )

    # American spelling for API clients while keeping the project's preferred
    # British/French-oriented spelling as the canonical implementation.
    analyze = analyse
