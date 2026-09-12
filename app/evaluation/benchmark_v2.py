"""Split-aware benchmark orchestration for the versioned regulatory dataset.

The deterministic production pipeline is always the baseline.  A Gemini judge
can optionally score retrieved answers, but its output is reported separately
and never changes the reproducible baseline metrics.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from app.domain import Citation, Claim, RegulatorySection, ReviewStatus
from app.ingestion import ingest
from app.retrieval import HybridRetriever, InMemoryIndex
from app.services import ChangeAnalysisService, ClaimReviewer

from .metrics import (
    RetrievalCase,
    evaluate_change_detection,
    evaluate_retrieval,
    evaluate_reviewer_classification,
)

DEFAULT_DATASET = Path("datasets/regulatory_benchmark_v2.json")
DEFAULT_JSON_OUTPUT = Path("artifacts/evaluation-report-v2.json")
DEFAULT_MARKDOWN_OUTPUT = Path("artifacts/evaluation-report-v2.md")
_DEFAULT_SPLIT = "test"
_DIFFICULTIES = ("easy", "medium", "hard", "unspecified")


class SemanticJudge(Protocol):
    """Structural protocol implemented by :class:`GeminiJudge`."""

    def judge(self, request: Any) -> Any: ...


def _section(value: dict[str, Any]) -> RegulatorySection:
    return RegulatorySection(**value)


def _dataset_metadata(data: dict[str, Any]) -> tuple[str, str]:
    metadata = data.get("dataset", "unnamed benchmark")
    if isinstance(metadata, str):
        return metadata, str(data.get("version", "unknown"))
    if isinstance(metadata, dict):
        return str(metadata.get("title", metadata.get("id", "unnamed benchmark"))), str(
            metadata.get("version", data.get("version", "unknown"))
        )
    raise ValueError("dataset metadata must be a string or object")


def _validate_dataset(data: dict[str, Any]) -> None:
    required = {"dataset", "retrieval", "changes", "grounding"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"dataset is missing required fields: {', '.join(sorted(missing))}")
    if not isinstance(data["retrieval"].get("documents"), list):
        raise ValueError("retrieval.documents must be a list")
    for collection, key in (
        (data["retrieval"], "queries"),
        (data["changes"], "cases"),
        (data["grounding"], "claims"),
    ):
        if not isinstance(collection.get(key), list):
            raise ValueError(f"{key} must be a list")


def _case_ids_for_split(
    data: dict[str, Any], split: str, *, manifest_key: str
) -> frozenset[str] | None:
    manifest = data.get("splits", {}).get(split)
    if not isinstance(manifest, dict) or manifest_key not in manifest:
        return None
    return frozenset(str(value) for value in manifest[manifest_key])


def _select_cases(
    cases: Iterable[dict[str, Any]],
    split: str,
    *,
    manifest_ids: frozenset[str] | None,
) -> list[dict[str, Any]]:
    cases = list(cases)
    if split == "all":
        return cases
    selected: list[dict[str, Any]] = []
    for case in cases:
        explicit_split = case.get("split")
        if explicit_split is not None:
            include = explicit_split == split
        elif manifest_ids is not None:
            include = str(case.get("id")) in manifest_ids
        else:
            # v1 compatibility: unsplit cases form the test acceptance set.
            include = split == _DEFAULT_SPLIT
        if include:
            selected.append(case)
    return selected


def _difficulty(case: dict[str, Any]) -> str:
    value = str(case.get("difficulty", "unspecified")).lower()
    return value if value in _DIFFICULTIES else "unspecified"


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_confidence_interval(
    values: Sequence[Any],
    statistic: Callable[[list[Any]], float],
    *,
    samples: int = 1000,
    confidence: float = 0.95,
    seed: int = 20260915,
) -> dict[str, Any] | None:
    """Return a deterministic percentile bootstrap CI, or ``None`` for n < 2."""

    if samples < 1:
        raise ValueError("bootstrap samples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    estimates = [
        statistic([values[rng.randrange(len(values))] for _ in values]) for _ in range(samples)
    ]
    alpha = (1.0 - confidence) / 2.0
    return {
        "lower": round(_percentile(estimates, alpha), 4),
        "upper": round(_percentile(estimates, 1.0 - alpha), 4),
        "confidence_level": confidence,
        "method": "percentile_bootstrap",
        "samples": samples,
    }


def _retrieval_summary(
    rows: Sequence[dict[str, Any]], *, k: int, bootstrap_samples: int, seed: int
) -> dict[str, Any]:
    cases = [
        RetrievalCase(frozenset(row["expected"]), tuple(row["retrieved"])) for row in rows
    ]
    metrics = asdict(evaluate_retrieval(cases, k=k))
    recall_values = [float(row["recall_at_k"]) for row in rows]
    rr_values = [float(row["reciprocal_rank"]) for row in rows]
    mean = lambda sample: sum(sample) / len(sample)  # noqa: E731 - local statistic
    metrics["confidence_intervals"] = {
        "recall_at_k": bootstrap_confidence_interval(
            recall_values, mean, samples=bootstrap_samples, seed=seed
        ),
        "mean_reciprocal_rank": bootstrap_confidence_interval(
            rr_values, mean, samples=bootstrap_samples, seed=seed + 1
        ),
    }
    return metrics


def _change_summary(
    rows: Sequence[dict[str, Any]], *, bootstrap_samples: int, seed: int
) -> dict[str, Any]:
    labels = [(bool(row["expected_material"]), bool(row["predicted_material"])) for row in rows]
    metrics = asdict(
        evaluate_change_detection(
            [expected for expected, _ in labels], [predicted for _, predicted in labels]
        )
    )

    def f1(sample: list[tuple[bool, bool]]) -> float:
        result = evaluate_change_detection(
            [expected for expected, _ in sample], [predicted for _, predicted in sample]
        )
        return result.f1

    metrics["confidence_intervals"] = {
        "f1": bootstrap_confidence_interval(
            labels, f1, samples=bootstrap_samples, seed=seed + 2
        )
    }
    return metrics


def _reviewer_summary(
    rows: Sequence[dict[str, Any]], *, bootstrap_samples: int, seed: int
) -> dict[str, Any]:
    expected = [ReviewStatus(row["expected_status"]) for row in rows]
    predicted = [ReviewStatus(row["status"]) for row in rows]
    metrics = asdict(evaluate_reviewer_classification(expected, predicted))
    correct = [wanted is actual for wanted, actual in zip(expected, predicted, strict=True)]
    mean = lambda sample: sum(sample) / len(sample)  # noqa: E731 - local statistic
    metrics["confidence_intervals"] = {
        "accuracy": bootstrap_confidence_interval(
            correct, mean, samples=bootstrap_samples, seed=seed + 3
        )
    }
    return metrics


def _by_difficulty(
    retrieval_rows: Sequence[dict[str, Any]],
    change_rows: Sequence[dict[str, Any]],
    review_rows: Sequence[dict[str, Any]],
    *,
    k: int,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    observed = sorted(
        {row["difficulty"] for row in [*retrieval_rows, *change_rows, *review_rows]},
        key=lambda value: (_DIFFICULTIES.index(value), value),
    )
    for difficulty in observed:
        retrieval = [row for row in retrieval_rows if row["difficulty"] == difficulty]
        changes = [row for row in change_rows if row["difficulty"] == difficulty]
        reviews = [row for row in review_rows if row["difficulty"] == difficulty]
        output[difficulty] = {
            "retrieval": _retrieval_summary(
                retrieval, k=k, bootstrap_samples=bootstrap_samples, seed=seed
            ),
            "change_detection": _change_summary(
                changes, bootstrap_samples=bootstrap_samples, seed=seed
            ),
            "reviewer_classification": _reviewer_summary(
                reviews, bootstrap_samples=bootstrap_samples, seed=seed
            ),
        }
    return output


def _run_semantic_judge(
    judge: SemanticJudge, case: dict[str, Any], results: Sequence[Any]
) -> dict[str, Any]:
    # Import lazily: deterministic runs must not require the optional client.
    from .gemini_judge import GeminiJudgeRequest

    evidence = tuple(result.text for result in results)
    answer = str(case.get("answer") or (results[0].text if results else ""))
    result = judge.judge(
        GeminiJudgeRequest(
            question=case["question"],
            answer=answer,
            evidence=evidence,
            reference_answer=case.get("reference_answer"),
        )
    )
    return result.model_dump(mode="json")


def run_benchmark_v2(
    dataset_path: Path = DEFAULT_DATASET,
    *,
    split: str = _DEFAULT_SPLIT,
    judge_mode: str = "deterministic",
    gemini_judge: SemanticJudge | None = None,
    bootstrap_samples: int = 1000,
    bootstrap_seed: int = 20260915,
) -> dict[str, Any]:
    """Run one dataset split and return a JSON-serialisable evaluation report."""

    if judge_mode not in {"deterministic", "gemini", "both"}:
        raise ValueError("judge_mode must be deterministic, gemini, or both")
    dataset_bytes = dataset_path.read_bytes()
    data = json.loads(dataset_bytes)
    _validate_dataset(data)
    title, version = _dataset_metadata(data)

    retrieval_cases = _select_cases(
        data["retrieval"]["queries"],
        split,
        manifest_ids=_case_ids_for_split(
            data, split, manifest_key="retrieval_query_ids"
        ),
    )
    change_cases = _select_cases(
        data["changes"]["cases"],
        split,
        manifest_ids=_case_ids_for_split(data, split, manifest_key="change_case_ids"),
    )
    grounding_cases = _select_cases(
        data["grounding"]["claims"],
        split,
        manifest_ids=_case_ids_for_split(data, split, manifest_key="grounding_claim_ids"),
    )

    index = InMemoryIndex()
    documents = data["retrieval"]["documents"]
    if split != "all" and any(item.get("split") is not None for item in documents):
        documents = [item for item in documents if item.get("split") == split]
    for item in documents:
        index.add(
            ingest(
                item["content"],
                source=item["source"],
                title=item.get("title"),
                document_type="regulatory_text",
                jurisdiction=item.get("jurisdiction"),
                published_at=item.get("published_at"),
            )
        )
    k = int(data["retrieval"].get("k", 5))
    retriever = HybridRetriever(index, evidence_threshold=0.0)
    retrieval_rows: list[dict[str, Any]] = []
    judge_rows: list[dict[str, Any]] = []
    if judge_mode in {"gemini", "both"} and gemini_judge is None:
        from .gemini_judge import GeminiJudge

        gemini_judge = GeminiJudge.from_settings()
    for case in retrieval_cases:
        results = retriever.search(case["question"], limit=k)
        ranked = tuple(result.citation for result in results)
        relevant = frozenset(case["relevant_citations"])
        top_k = ranked[:k]
        first_rank = next(
            (rank for rank, citation in enumerate(ranked, start=1) if citation in relevant), None
        )
        row = {
            "id": case["id"],
            "split": case.get("split", _DEFAULT_SPLIT),
            "difficulty": _difficulty(case),
            "challenge_tags": list(case.get("challenge_tags", [])),
            "question": case["question"],
            "expected": sorted(relevant),
            "retrieved": list(ranked),
            "hit_at_k": bool(relevant.intersection(top_k)),
            "recall_at_k": round(len(relevant.intersection(top_k)) / len(relevant), 4)
            if relevant
            else 0.0,
            "reciprocal_rank": round(1 / first_rank, 4) if first_rank else 0.0,
        }
        retrieval_rows.append(row)
        if gemini_judge is not None:
            judged = _run_semantic_judge(gemini_judge, case, results)
            judge_rows.append({"id": case["id"], "difficulty": _difficulty(case), **judged})

    analyser = ChangeAnalysisService()
    threshold = float(data["changes"].get("materiality_threshold", 0.35))
    change_rows: list[dict[str, Any]] = []
    for case in change_cases:
        previous = _section(case["previous"]) if case.get("previous") else None
        current = _section(case["current"]) if case.get("current") else None
        change = analyser.compare_sections(previous, current)
        change_rows.append(
            {
                "id": case["id"],
                "split": case.get("split", _DEFAULT_SPLIT),
                "difficulty": _difficulty(case),
                "challenge_tags": list(case.get("challenge_tags", [])),
                "expected_material": bool(case["expected_material"]),
                "predicted_material": change.materiality_score >= threshold,
                "change_type": change.change_type.value,
                "materiality": change.materiality.value,
                "materiality_score": change.materiality_score,
                "signals": list(change.signals),
            }
        )

    evidence_sources = [_section(source) for source in data["grounding"]["sources"]]
    evidence_claims = [
        Claim(
            claim_id=case["claim_id"],
            text=case["text"],
            citations=tuple(Citation(**citation) for citation in case.get("citations", [])),
        )
        for case in grounding_cases
    ]
    reviews = ClaimReviewer().review_claims(
        evidence_claims, evidence_sources, remove_unsupported=False
    ).reviews
    review_rows = [
        {
            "claim_id": case["claim_id"],
            "split": case.get("split", _DEFAULT_SPLIT),
            "difficulty": _difficulty(case),
            "expected_status": case["expected_status"],
            "status": review.status.value,
            "supported_citations": len(review.supported_citations),
            "unsupported_citations": len(review.unsupported_citations),
        }
        for case, review in zip(grounding_cases, reviews, strict=True)
    ]

    retrieval_summary = _retrieval_summary(
        retrieval_rows, k=k, bootstrap_samples=bootstrap_samples, seed=bootstrap_seed
    )
    changes_summary = _change_summary(
        change_rows, bootstrap_samples=bootstrap_samples, seed=bootstrap_seed
    )
    reviewer_summary = _reviewer_summary(
        review_rows, bootstrap_samples=bootstrap_samples, seed=bootstrap_seed
    )
    summary: dict[str, Any] = {
        "retrieval": retrieval_summary,
        "change_detection": changes_summary,
        "evidence": {"reviewer_classification": reviewer_summary},
        "by_difficulty": _by_difficulty(
            retrieval_rows,
            change_rows,
            review_rows,
            k=k,
            bootstrap_samples=bootstrap_samples,
            seed=bootstrap_seed,
        ),
    }
    if judge_rows:
        summary["gemini_judge"] = {
            metric: round(sum(float(row[metric]) for row in judge_rows) / len(judge_rows), 4)
            for metric in ("groundedness", "correctness", "completeness")
        }
        summary["gemini_judge"].update(
            {
                "pass_rate": round(
                    sum(bool(row["passed"]) for row in judge_rows) / len(judge_rows), 4
                ),
                "evaluated_cases": len(judge_rows),
                "advisory": True,
            }
        )

    return {
        "benchmark": {
            "dataset": title,
            "version": version,
            "schema_version": str(data.get("schema_version", "1.0")),
            "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "split": split,
            "baseline": "deterministic",
            "judge_mode": judge_mode,
            "bootstrap": {"samples": bootstrap_samples, "seed": bootstrap_seed},
        },
        "summary": summary,
        "details": {
            "retrieval": retrieval_rows,
            "changes": change_rows,
            "evidence_reviews": review_rows,
            "gemini_judge": judge_rows,
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a compact, portfolio-ready report from the canonical JSON data."""

    benchmark = report["benchmark"]
    summary = report["summary"]
    retrieval = summary["retrieval"]
    changes = summary["change_detection"]
    reviewer = summary["evidence"]["reviewer_classification"]
    lines = [
        f"# Benchmark — {benchmark['dataset']}",
        "",
        f"Dataset version: `{benchmark['version']}` · Split: `{benchmark['split']}` · "
        f"SHA-256: `{benchmark['sha256']}`",
        "",
        "## Results",
        "",
        "| Evaluation | Metric | Score | Cases |",
        "|---|---:|---:|---:|",
        f"| Retrieval | Recall@K | {retrieval['recall_at_k']:.1%} | "
        f"{retrieval['evaluated_cases']} |",
        f"| Retrieval | MRR | {retrieval['mean_reciprocal_rank']:.1%} | "
        f"{retrieval['evaluated_cases']} |",
        f"| Change detection | F1 | {changes['f1']:.1%} | "
        f"{len(report['details']['changes'])} |",
        f"| Evidence reviewer | Accuracy | {reviewer['accuracy']:.1%} | "
        f"{reviewer['evaluated_cases']} |",
    ]
    if "gemini_judge" in summary:
        judged = summary["gemini_judge"]
        lines.append(
            f"| Gemini judge (advisory) | Pass rate | {judged['pass_rate']:.1%} | "
            f"{judged['evaluated_cases']} |"
        )
    lines.extend(["", "## By difficulty", ""])
    for difficulty, metrics in summary["by_difficulty"].items():
        lines.append(
            f"- **{difficulty.title()}** — Recall@K "
            f"{metrics['retrieval']['recall_at_k']:.1%}, change F1 "
            f"{metrics['change_detection']['f1']:.1%}, reviewer accuracy "
            f"{metrics['reviewer_classification']['accuracy']:.1%}."
        )
    lines.extend(
        [
            "",
            "> Bootstrap confidence intervals use a fixed seed. Gemini scores are "
            "advisory and are kept separate from deterministic baseline metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    report: dict[str, Any], *, json_path: Path, markdown_path: Path | None = None
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
