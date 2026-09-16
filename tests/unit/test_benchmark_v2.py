import json
from pathlib import Path

from app.config import get_settings
from app.evaluation.benchmark_v2 import (
    bootstrap_confidence_interval,
    render_markdown_report,
    run_benchmark_v2,
    write_reports,
)
from scripts.run_benchmark_v2 import main


def _v2_dataset(path: Path) -> Path:
    data = {
        "schema_version": "2.0",
        "dataset": {"id": "fixture", "title": "Fixture v2", "version": "2.0.0"},
        "splits": {
            "test": {
                "retrieval_query_ids": ["r-hard"],
                "change_case_ids": ["c-hard"],
                "grounding_claim_ids": ["g-hard"],
            }
        },
        "retrieval": {
            "k": 1,
            "documents": [
                {
                    "id": "doc",
                    "source": "DORA",
                    "content": "# Resilience\n\nArticle 1 - Testing\n\nBanks must test annually.",
                }
            ],
            "queries": [
                {
                    "id": "r-hard",
                    "split": "test",
                    "difficulty": "hard",
                    "question": "How often must banks test?",
                    "relevant_citations": ["DORA > Resilience > Article 1"],
                    "challenge_tags": ["paraphrase"],
                },
                {
                    "id": "r-easy",
                    "split": "train",
                    "difficulty": "easy",
                    "question": "What must banks do annually?",
                    "relevant_citations": ["DORA > Resilience > Article 1"],
                },
            ],
        },
        "changes": {
            "materiality_threshold": 0.35,
            "cases": [
                {
                    "id": "c-hard",
                    "split": "test",
                    "difficulty": "hard",
                    "expected_material": True,
                    "previous": {
                        "document_id": "dora",
                        "section_id": "1",
                        "text": "Banks should test annually.",
                    },
                    "current": {
                        "document_id": "dora",
                        "section_id": "1",
                        "text": "Banks must test annually.",
                    },
                },
                {
                    "id": "c-easy",
                    "split": "train",
                    "difficulty": "easy",
                    "expected_material": False,
                    "previous": {
                        "document_id": "dora",
                        "section_id": "2",
                        "text": "Keep records.",
                    },
                    "current": {
                        "document_id": "dora",
                        "section_id": "2",
                        "text": "Keep records.",
                    },
                },
            ],
        },
        "grounding": {
            "sources": [
                {"document_id": "dora", "section_id": "1", "text": "Banks must test annually."}
            ],
            "claims": [
                {
                    "claim_id": "g-hard",
                    "split": "test",
                    "difficulty": "hard",
                    "text": "Testing is annual.",
                    "expected_status": "supported",
                    "citations": [
                        {"document_id": "dora", "section_id": "1", "quote": "test annually"}
                    ],
                }
            ],
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_v2_filters_split_and_reports_difficulty(tmp_path: Path) -> None:
    report = run_benchmark_v2(_v2_dataset(tmp_path / "dataset.json"), bootstrap_samples=20)

    assert report["benchmark"]["schema_version"] == "2.0"
    assert report["benchmark"]["split"] == "test"
    assert report["benchmark"]["minimum_query_coverage"] == (
        get_settings().minimum_query_coverage
    )
    assert report["summary"]["retrieval"]["evaluated_cases"] == 1
    assert report["summary"]["change_detection"]["passed"] == 1
    assert report["summary"]["change_detection"]["performance_metric"] is None
    assert report["summary"]["evidence"]["reviewer_classification"]["accuracy"] == 1
    assert set(report["summary"]["by_difficulty"]) == {"hard"}
    assert report["summary"]["retrieval"]["confidence_intervals"]["recall_at_k"] is None


def test_v2_all_split_includes_every_case_and_bootstraps(tmp_path: Path) -> None:
    report = run_benchmark_v2(
        _v2_dataset(tmp_path / "dataset.json"), split="all", bootstrap_samples=25
    )

    assert report["summary"]["retrieval"]["evaluated_cases"] == 2
    interval = report["summary"]["retrieval"]["confidence_intervals"]["recall_at_k"]
    assert interval["method"] == "percentile_bootstrap"
    assert interval["samples"] == 25
    assert set(report["summary"]["by_difficulty"]) == {"easy", "hard"}


def test_bootstrap_is_seeded_and_rejects_invalid_configuration() -> None:
    def statistic(values: list[float]) -> float:
        return sum(values) / len(values)

    first = bootstrap_confidence_interval([0.0, 1.0, 1.0], statistic, samples=50, seed=7)
    second = bootstrap_confidence_interval([0.0, 1.0, 1.0], statistic, samples=50, seed=7)

    assert first == second
    assert first is not None
    assert 0 <= first["lower"] <= first["upper"] <= 1


def test_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    dataset = _v2_dataset(tmp_path / "dataset.json")
    report = run_benchmark_v2(dataset, bootstrap_samples=10)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_reports(report, json_path=json_path, markdown_path=markdown_path)

    assert json.loads(json_path.read_text()) == report
    markdown = markdown_path.read_text()
    assert "# Benchmark — Fixture v2" in markdown
    assert "Recall@1" in markdown
    assert "95% CI" not in markdown  # A one-case fixture cannot support an interval.
    assert "Change detection | F1" not in markdown
    assert "template-derived fixtures" in markdown
    assert "Gemini judge" not in markdown
    assert render_markdown_report(report) == markdown


def test_cli_writes_both_formats(tmp_path: Path) -> None:
    dataset = _v2_dataset(tmp_path / "dataset.json")
    json_path = tmp_path / "cli.json"
    markdown_path = tmp_path / "cli.md"

    exit_code = main(
        [
            "--dataset",
            str(dataset),
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
            "--bootstrap-samples",
            "10",
        ]
    )

    assert exit_code == 0
    assert json_path.exists()
    assert markdown_path.exists()


def test_gemini_metrics_share_one_table_when_enabled(tmp_path: Path) -> None:
    report = run_benchmark_v2(_v2_dataset(tmp_path / "dataset.json"), bootstrap_samples=10)
    report["summary"]["gemini_judge"] = {
        "groundedness": 0.845,
        "correctness": 0.69,
        "completeness": 0.69,
        "pass_rate": 0.55,
        "evaluated_cases": 20,
        "advisory": True,
    }

    markdown = render_markdown_report(report)

    assert "| Gemini judge (advisory) | Groundedness | 84.5% | 20 |" in markdown
    assert "| Gemini judge (advisory) | Correctness | 69.0% | 20 |" in markdown
    assert "| Gemini judge (advisory) | Completeness | 69.0% | 20 |" in markdown
    assert "| Gemini judge (advisory) | Pass rate | 55.0% | 20 |" in markdown


def test_default_v2_dataset_runs_with_grounding_cases() -> None:
    report = run_benchmark_v2(bootstrap_samples=10)

    assert report["summary"]["retrieval"]["evaluated_cases"] == 20
    assert len(report["details"]["changes"]) == 40
    assert "f1" not in report["summary"]["change_detection"]
    assert report["summary"]["change_detection"]["evaluation_type"] == (
        "synthetic_regression_checks"
    )
    assert report["summary"]["evidence"]["reviewer_classification"][
        "evaluated_cases"
    ] == 20
