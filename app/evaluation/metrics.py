from dataclasses import dataclass

from app.domain import ClaimReview, ReviewStatus


@dataclass(frozen=True, slots=True)
class RetrievalCase:
    relevant_ids: frozenset[str]
    ranked_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_k: float
    mean_reciprocal_rank: float
    evaluated_cases: int


@dataclass(frozen=True, slots=True)
class ChangeDetectionMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True, slots=True)
class GroundingMetrics:
    """Evidence quality aggregated from deterministic claim reviews."""

    groundedness: float
    citation_accuracy: float
    grounded_claims: int
    evaluated_claims: int
    supported_citations: int
    evaluated_citations: int


@dataclass(frozen=True, slots=True)
class ReviewerClassificationMetrics:
    accuracy: float
    correct: int
    evaluated_cases: int


def evaluate_retrieval(cases: list[RetrievalCase], *, k: int = 5) -> RetrievalMetrics:
    """Compute macro Recall@K and MRR, assigning zero recall to empty judgments."""

    if k < 1:
        raise ValueError("k must be positive")
    if not cases:
        return RetrievalMetrics(0.0, 0.0, 0)

    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    for case in cases:
        top_k = case.ranked_ids[:k]
        case_recall = (
            len(case.relevant_ids.intersection(top_k)) / len(case.relevant_ids)
            if case.relevant_ids
            else 0.0
        )
        recall_sum += case_recall
        for rank, identifier in enumerate(case.ranked_ids, start=1):
            if identifier in case.relevant_ids:
                reciprocal_rank_sum += 1 / rank
                break

    count = len(cases)
    return RetrievalMetrics(
        recall_at_k=round(recall_sum / count, 4),
        mean_reciprocal_rank=round(reciprocal_rank_sum / count, 4),
        evaluated_cases=count,
    )


def evaluate_change_detection(
    expected_material: list[bool], predicted_material: list[bool]
) -> ChangeDetectionMetrics:
    if len(expected_material) != len(predicted_material):
        raise ValueError("expected and predicted labels must have the same length")

    true_positives = sum(
        expected and predicted
        for expected, predicted in zip(expected_material, predicted_material, strict=True)
    )
    false_positives = sum(
        not expected and predicted
        for expected, predicted in zip(expected_material, predicted_material, strict=True)
    )
    false_negatives = sum(
        expected and not predicted
        for expected, predicted in zip(expected_material, predicted_material, strict=True)
    )
    precision = _safe_ratio(true_positives, true_positives + false_positives)
    recall = _safe_ratio(true_positives, true_positives + false_negatives)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    return ChangeDetectionMetrics(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


def evaluate_grounding(reviews: list[ClaimReview]) -> GroundingMetrics:
    """Measure claim grounding and citation correctness.

    A claim is grounded when at least one of its citations is independently
    verifiable. Citation accuracy is stricter: every citation is counted, so a
    partially supported claim lowers that score. Claims without citations remain
    in the groundedness denominator but do not invent a citation denominator.
    """

    grounded_claims = sum(
        review.status in {ReviewStatus.SUPPORTED, ReviewStatus.PARTIALLY_SUPPORTED}
        for review in reviews
    )
    supported_citations = sum(len(review.supported_citations) for review in reviews)
    evaluated_citations = sum(
        len(review.supported_citations) + len(review.unsupported_citations) for review in reviews
    )
    return GroundingMetrics(
        groundedness=round(_safe_ratio(grounded_claims, len(reviews)), 4),
        citation_accuracy=round(_safe_ratio(supported_citations, evaluated_citations), 4),
        grounded_claims=grounded_claims,
        evaluated_claims=len(reviews),
        supported_citations=supported_citations,
        evaluated_citations=evaluated_citations,
    )


def evaluate_reviewer_classification(
    expected: list[ReviewStatus], predicted: list[ReviewStatus]
) -> ReviewerClassificationMetrics:
    """Score the reviewer's supported/partial/unsupported classification."""

    if len(expected) != len(predicted):
        raise ValueError("expected and predicted statuses must have the same length")
    correct = sum(wanted is actual for wanted, actual in zip(expected, predicted, strict=True))
    return ReviewerClassificationMetrics(
        accuracy=round(_safe_ratio(correct, len(expected)), 4),
        correct=correct,
        evaluated_cases=len(expected),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
