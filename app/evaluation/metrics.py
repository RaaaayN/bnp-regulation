from dataclasses import dataclass


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


def evaluate_retrieval(cases: list[RetrievalCase], *, k: int = 5) -> RetrievalMetrics:
    if k < 1:
        raise ValueError("k must be positive")
    if not cases:
        return RetrievalMetrics(0.0, 0.0, 0)

    recalled = 0
    reciprocal_rank_sum = 0.0
    for case in cases:
        top_k = case.ranked_ids[:k]
        if case.relevant_ids.intersection(top_k):
            recalled += 1
        for rank, identifier in enumerate(case.ranked_ids, start=1):
            if identifier in case.relevant_ids:
                reciprocal_rank_sum += 1 / rank
                break

    count = len(cases)
    return RetrievalMetrics(
        recall_at_k=round(recalled / count, 4),
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


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
