import json
from pathlib import Path

from app.domain import ReviewStatus
from app.evaluation.benchmark import main, run_benchmark
from app.evaluation.metrics import (
    RetrievalCase,
    evaluate_retrieval,
    evaluate_reviewer_classification,
)

DATASET = Path("datasets/regulatory_golden_v1.json")


def test_benchmark_calculates_metrics_from_golden_dataset() -> None:
    report = run_benchmark(DATASET)

    assert report["benchmark"]["dataset"] == "EU banking regulatory intelligence golden set"
    assert report["benchmark"]["deterministic"] is True
    assert len(report["benchmark"]["sha256"]) == 64
    assert report["summary"]["retrieval"]["evaluated_cases"] == 6
    assert 0.0 <= report["summary"]["retrieval"]["recall_at_k"] <= 1.0
    assert 0.0 <= report["summary"]["retrieval"]["mean_reciprocal_rank"] <= 1.0
    assert report["summary"]["change_detection"]["true_positives"] > 0
    evidence = report["summary"]["evidence"]
    assert evidence["reviewer_classification"]["accuracy"] == 1.0
    assert evidence["reviewer_classification"]["evaluated_cases"] == 3
    assert evidence["claim_set_composition"]["evaluated_claims"] > 3
    assert evidence["claim_set_composition"]["evaluated_citations"] > 3


def test_benchmark_report_is_reproducible() -> None:
    assert run_benchmark(DATASET) == run_benchmark(DATASET)


def test_cli_writes_configurable_json_report(tmp_path: Path) -> None:
    output = tmp_path / "custom-report.json"

    exit_code = main(["--dataset", str(DATASET), "--output", str(output)])

    assert exit_code == 0
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == run_benchmark(DATASET)


def test_recall_at_k_counts_every_relevant_passage() -> None:
    metrics = evaluate_retrieval(
        [RetrievalCase(frozenset({"relevant-a", "relevant-b"}), ("relevant-a", "noise"))],
        k=2,
    )

    assert metrics.recall_at_k == 0.5


def test_recall_at_k_treats_empty_relevance_judgment_as_zero() -> None:
    metrics = evaluate_retrieval([RetrievalCase(frozenset(), ("retrieved",))], k=1)

    assert metrics.recall_at_k == 0.0
    assert metrics.mean_reciprocal_rank == 0.0


def test_reviewer_accuracy_is_calculated_from_expected_statuses() -> None:
    metrics = evaluate_reviewer_classification(
        [ReviewStatus.SUPPORTED, ReviewStatus.UNSUPPORTED],
        [ReviewStatus.SUPPORTED, ReviewStatus.PARTIALLY_SUPPORTED],
    )

    assert metrics.accuracy == 0.5
    assert metrics.correct == 1
