"""Validated data structures exchanged by the analysis services.

The models deliberately keep source passages alongside conclusions.  This makes
the output suitable for an audit trail and allows :mod:`app.services.reviewer`
to verify every citation without relying on an external model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Score = Annotated[float, Field(ge=0.0, le=1.0)]


class DomainModel(BaseModel):
    """Strict base model: silently ignored input is unsafe in an audit trail."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class MaterialityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class RegulatorySection(DomainModel):
    """One structurally meaningful unit from a regulatory document."""

    document_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    title: str = ""
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    version: str | None = None

    @property
    def source_id(self) -> str:
        """Stable key used by citations and evidence registries."""

        return f"{self.document_id}:{self.section_id}"


class Citation(DomainModel):
    """An exact, independently verifiable excerpt from a source section."""

    document_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    version: str | None = None

    @property
    def source_id(self) -> str:
        return f"{self.document_id}:{self.section_id}"


class Claim(DomainModel):
    """A conclusion which must be backed by at least one citation to be usable."""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()


class SectionChange(DomainModel):
    """Comparison result for a matched, added, or removed section."""

    change_id: str = Field(min_length=1)
    change_type: ChangeType
    previous_section: RegulatorySection | None = None
    current_section: RegulatorySection | None = None
    similarity_score: Score
    materiality_score: Score
    materiality: MaterialityLevel
    confidence_score: Score
    confidence: ConfidenceLevel
    signals: tuple[str, ...] = ()
    claims: tuple[Claim, ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> SectionChange:
        if self.change_type is ChangeType.ADDED and self.current_section is None:
            raise ValueError("an added change requires current_section")
        if self.change_type is ChangeType.REMOVED and self.previous_section is None:
            raise ValueError("a removed change requires previous_section")
        if self.change_type in {ChangeType.MODIFIED, ChangeType.UNCHANGED} and (
            self.previous_section is None or self.current_section is None
        ):
            raise ValueError("a matched change requires both section versions")
        return self


class ClaimReview(DomainModel):
    claim: Claim
    status: ReviewStatus
    supported_citations: tuple[Citation, ...] = ()
    unsupported_citations: tuple[Citation, ...] = ()
    reason: str


class ReviewResult(DomainModel):
    accepted_claims: tuple[Claim, ...] = ()
    flagged_claims: tuple[ClaimReview, ...] = ()
    reviews: tuple[ClaimReview, ...] = ()


class ImpactCandidate(DomainModel):
    """A known internal item connected to regulatory concepts."""

    item_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    item_type: str = Field(min_length=1)
    keywords: tuple[str, ...] = ()
    source: RegulatorySection | None = None


class ImpactAssessment(DomainModel):
    change_id: str = Field(min_length=1)
    candidate: ImpactCandidate
    relevance_score: Score
    confidence_score: Score
    rationale: str
    claims: tuple[Claim, ...] = ()
