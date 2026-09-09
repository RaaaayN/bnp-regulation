"""Reproducible end-to-end evaluation over the checked-in golden dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.domain import Citation, Claim, RegulatorySection, ReviewStatus
from app.ingestion import ingest
from app.retrieval import HybridRetriever, InMemoryIndex
from app.services import ChangeAnalysisService, ClaimReviewer

from .metrics import (
    RetrievalCase,
    evaluate_change_detection,
    evaluate_grounding,
    evaluate_retrieval,
    evaluate_reviewer_classification,
)

DEFAULT_DATASET = Path("datasets/regulatory_golden_v1.json")
DEFAULT_OUTPUT = Path("artifacts/evaluation-report.json")


def _section(value: dict[str, Any]) -> RegulatorySection:
    return RegulatorySection(**value)


def _load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"dataset", "version", "retrieval", "changes", "grounding"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"dataset is missing required fields: {', '.join(sorted(missing))}")
    return data


def run_benchmark(dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    """Execute all production components and return a JSON-serialisable report."""

    dataset_bytes = dataset_path.read_bytes()
    data = _load_dataset(dataset_path)

    index = InMemoryIndex()
    for item in data["retrieval"]["documents"]:
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
    retriever = HybridRetriever(index, evidence_threshold=0.0)
    retrieval_cases: list[RetrievalCase] = []
    retrieval_details: list[dict[str, Any]] = []
    k = int(data["retrieval"].get("k", 5))
    for case in data["retrieval"]["queries"]:
        results = retriever.search(case["question"], limit=k)
        ranked = tuple(result.citation for result in results)
        relevant = frozenset(case["relevant_citations"])
        retrieval_cases.append(RetrievalCase(relevant, ranked))
        retrieval_details.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected": sorted(relevant),
                "retrieved": list(ranked),
                "hit_at_k": bool(relevant.intersection(ranked[:k])),
            }
        )

    analyser = ChangeAnalysisService()
    expected_material: list[bool] = []
    predicted_material: list[bool] = []
    change_details: list[dict[str, Any]] = []
    threshold = float(data["changes"].get("materiality_threshold", 0.35))
    generated_claims: list[Claim] = []
    generated_sources: list[RegulatorySection] = []
    for case in data["changes"]["cases"]:
        previous = _section(case["previous"]) if case.get("previous") else None
        current = _section(case["current"]) if case.get("current") else None
        change = analyser.compare_sections(previous, current)
        expected = bool(case["expected_material"])
        predicted = change.materiality_score >= threshold
        expected_material.append(expected)
        predicted_material.append(predicted)
        generated_claims.extend(change.claims)
        generated_sources.extend(source for source in (previous, current) if source is not None)
        change_details.append(
            {
                "id": case["id"],
                "expected_material": expected,
                "predicted_material": predicted,
                "change_type": change.change_type.value,
                "materiality": change.materiality.value,
                "materiality_score": change.materiality_score,
                "signals": list(change.signals),
            }
        )

    evidence_sources = [_section(source) for source in data["grounding"]["sources"]]
    evidence_claims = [
        Claim(
            claim_id=claim["claim_id"],
            text=claim["text"],
            citations=tuple(Citation(**citation) for citation in claim.get("citations", [])),
        )
        for claim in data["grounding"]["claims"]
    ]
    reviewer = ClaimReviewer()
    reviews = reviewer.review_claims(
        [*generated_claims, *evidence_claims],
        [*generated_sources, *evidence_sources],
        remove_unsupported=False,
    ).reviews

    manual_review_count = len(evidence_claims)
    manual_reviews = reviews[-manual_review_count:] if manual_review_count else ()
    expected_statuses = [
        ReviewStatus(claim["expected_status"]) for claim in data["grounding"]["claims"]
    ]
    reviewer_metrics = evaluate_reviewer_classification(
        expected_statuses,
        [review.status for review in manual_reviews],
    )

    retrieval_metrics = evaluate_retrieval(retrieval_cases, k=k)
    change_metrics = evaluate_change_detection(expected_material, predicted_material)
    grounding_metrics = evaluate_grounding(list(reviews))
    return {
        "benchmark": {
            "dataset": data["dataset"],
            "version": data["version"],
            "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "deterministic": True,
        },
        "summary": {
            "retrieval": asdict(retrieval_metrics),
            "change_detection": asdict(change_metrics),
            "evidence": {
                "reviewer_classification": asdict(reviewer_metrics),
                "claim_set_composition": asdict(grounding_metrics),
            },
        },
        "details": {
            "retrieval": retrieval_details,
            "changes": change_details,
            "evidence_reviews": [
                {
                    "claim_id": review.claim.claim_id,
                    "status": review.status.value,
                    "expected_status": (
                        data["grounding"]["claims"][index - (len(reviews) - manual_review_count)][
                            "expected_status"
                        ]
                        if index >= len(reviews) - manual_review_count
                        else None
                    ),
                    "supported_citations": len(review.supported_citations),
                    "unsupported_citations": len(review.unsupported_citations),
                }
                for index, review in enumerate(reviews)
            ],
        },
    }


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_benchmark(args.dataset)
    write_report(report, args.output)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI wrapper
    raise SystemExit(main())
