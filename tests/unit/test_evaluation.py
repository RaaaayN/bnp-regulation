import pytest

from app.evaluation import RetrievalCase, evaluate_change_detection, evaluate_retrieval


def test_retrieval_metrics_are_reproducible() -> None:
    metrics = evaluate_retrieval(
        [
            RetrievalCase(frozenset({"a"}), ("x", "a", "z")),
            RetrievalCase(frozenset({"b"}), ("b", "y")),
            RetrievalCase(frozenset({"c"}), ("x", "y", "c")),
        ],
        k=2,
    )

    assert metrics.recall_at_k == pytest.approx(0.6667)
    assert metrics.mean_reciprocal_rank == pytest.approx(0.6111)


def test_change_detection_metrics() -> None:
    metrics = evaluate_change_detection(
        [True, True, False, False],
        [True, False, True, False],
    )

    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5


def test_change_detection_rejects_misaligned_labels() -> None:
    with pytest.raises(ValueError, match="same length"):
        evaluate_change_detection([True], [])
