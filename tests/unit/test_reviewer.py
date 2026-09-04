from app.domain import Citation, Claim, RegulatorySection, ReviewStatus
from app.services import ClaimReviewer


def source(version: str = "2026") -> RegulatorySection:
    return RegulatorySection(
        document_id="eba",
        section_id="12.3",
        text="Institutions must review the monitoring framework annually.",
        page=37,
        version=version,
    )


def citation(quote: str, *, version: str = "2026") -> Citation:
    return Citation(
        document_id="eba",
        section_id="12.3",
        quote=quote,
        page=37,
        version=version,
    )


def test_reviewer_accepts_only_exactly_verifiable_citations() -> None:
    claim = Claim(
        claim_id="c-1",
        text="An annual monitoring review is mandatory.",
        citations=(citation("institutions MUST review the monitoring framework annually."),),
    )

    result = ClaimReviewer().review_claims([claim], [source()])

    assert result.accepted_claims == (claim,)
    assert result.reviews[0].status is ReviewStatus.SUPPORTED
    assert result.flagged_claims == ()


def test_reviewer_removes_unsupported_claims_by_default() -> None:
    claim = Claim(
        claim_id="c-2",
        text="Reviews are required monthly.",
        citations=(citation("Institutions must review the framework monthly."),),
    )

    result = ClaimReviewer().review_claims([claim], [source()])

    assert result.accepted_claims == ()
    assert result.flagged_claims[0].status is ReviewStatus.UNSUPPORTED


def test_reviewer_flags_partial_support_and_can_preserve_for_manual_review() -> None:
    claim = Claim(
        claim_id="c-3",
        text="The obligation and its timing changed.",
        citations=(
            citation("Institutions must review the monitoring framework annually."),
            citation("This passage does not exist."),
        ),
    )

    result = ClaimReviewer().review_claims([claim], [source()], remove_unsupported=False)

    assert result.accepted_claims == (claim,)
    assert result.flagged_claims[0].status is ReviewStatus.PARTIALLY_SUPPORTED


def test_reviewer_rejects_matching_text_from_the_wrong_version() -> None:
    claim = Claim(
        claim_id="c-4",
        text="A claim tied to an unavailable version.",
        citations=(citation(source().text, version="2025"),),
    )

    result = ClaimReviewer().review_claims([claim], [source("2026")])

    assert result.reviews[0].status is ReviewStatus.UNSUPPORTED
