#!/usr/bin/env python3
"""Build the versioned synthetic challenge set and its checksum manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.evaluation.synthetic_dataset import (
    SPLIT_NAMES,
    SYNTHETIC_DATASET_PATH,
    SYNTHETIC_MANIFEST_PATH,
    canonical_json_bytes,
    dataset_statistics,
    sha256_json,
    validate_synthetic_dataset,
)

TOPICS = (
    "payment continuity",
    "identity assurance",
    "vendor oversight",
    "liquidity monitoring",
    "model governance",
    "incident escalation",
    "customer screening",
    "data lineage",
    "access recertification",
    "recovery testing",
    "collateral controls",
    "fraud monitoring",
    "complaints handling",
    "outsourcing inventory",
    "market surveillance",
    "capital planning",
    "audit evidence",
    "cloud exit planning",
    "transaction tracing",
    "risk acceptance",
    "business continuity",
    "sanctions filtering",
    "records disposal",
    "credit review",
    "operational resilience",
    "privacy response",
    "third-party assurance",
    "treasury controls",
    "conduct monitoring",
    "change governance",
)


def build_dataset() -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    grounding_sources: list[dict[str, Any]] = []
    grounding_claims: list[dict[str, Any]] = []
    split_payload = {
        split: {
            "document_ids": [],
            "retrieval_query_ids": [],
            "change_case_ids": [],
            "grounding_claim_ids": [],
        }
        for split in SPLIT_NAMES
    }

    for index, topic in enumerate(TOPICS):
        split = SPLIT_NAMES[index // 10]
        local = (index % 10) + 1
        family = f"{split}-{topic.replace(' ', '-')}"
        source = f"SYN-{split.upper()}-{local:02d}"
        document_id = f"doc-{split}-{local:02d}"
        base_article = 100 + index * 10
        years = 3 + (index % 7)
        months = 3 * (1 + (index % 4))
        artifact = f"{topic} control evidence"
        plan = f"{topic} operating plan"
        heading = f"{topic.title()} controls"
        content = (
            f"# {heading}\n\n"
            f"Article {base_article + 1} - Evidence preservation\n\n"
            f"Regulated firms must retain {artifact} for {years} years after closure.\n\n"
            f"Article {base_article + 2} - Governance approval\n\n"
            f"The oversight committee must approve the {plan} every {months} months.\n\n"
            f"Article {base_article + 3} - Similar but non-applicable scenario\n\n"
            f"Service providers may retain draft {topic} evidence for {years + 2} years, "
            f"and an advisory panel may discuss the plan every {months + 3} months."
        )
        document = {
            "id": document_id,
            "source": source,
            "title": f"Synthetic {topic.title()} Standard",
            "jurisdiction": "SYNTHETIC",
            "published_at": "2026-01-01",
            "content": content,
            "split": split,
            "family_id": family,
            "provenance": {
                "kind": "synthetic",
                "generator": "scripts/build_synthetic_benchmark.py",
                "source_url": None,
            },
        }
        documents.append(document)
        split_payload[split]["document_ids"].append(document_id)

        query_specs = (
            (
                f"For how many years must regulated firms retain {artifact}?",
                f"{source} > {heading} > Article {base_article + 1}",
                ["exact_terms", "hard_negative"],
            ),
            (
                f"At what cadence does the governing body formally sign off the operating "
                f"blueprint in synthetic scenario {split.upper()}-{local:02d}?",
                f"{source} > {heading} > Article {base_article + 2}",
                ["paraphrase_without_lexical_overlap", "hard_negative"],
            ),
        )
        for offset, (question, citation, tags) in enumerate(query_specs, start=1):
            query_number = index * 2 + offset
            difficulty = ("easy", "medium", "hard")[(query_number - 1) % 3]
            query_id = f"ret-{query_number:03d}"
            queries.append(
                {
                    "id": query_id,
                    "split": split,
                    "family_id": family,
                    "difficulty": difficulty,
                    "question": question,
                    "relevant_citations": [citation],
                    "challenge_tags": tags,
                }
            )
            split_payload[split]["retrieval_query_ids"].append(query_id)

        case_specs = _change_specs(index, split, local, family, topic, base_article)
        changes.extend(case_specs)
        split_payload[split]["change_case_ids"].extend(case["id"] for case in case_specs)

        evidence_id = f"evidence-{split}-{local:02d}"
        evidence_text = f"Regulated firms must retain {artifact} for {years} years after closure."
        grounding_sources.append(
            {
                "document_id": evidence_id,
                "section_id": str(base_article + 1),
                "title": "Evidence preservation",
                "text": evidence_text,
                "page": local,
                "version": "v2",
            }
        )
        claim_specs = _grounding_specs(
            index=index,
            split=split,
            local=local,
            family=family,
            evidence_id=evidence_id,
            section_id=str(base_article + 1),
            artifact=artifact,
            years=years,
            evidence_text=evidence_text,
        )
        grounding_claims.extend(claim_specs)
        split_payload[split]["grounding_claim_ids"].extend(
            case["claim_id"] for case in claim_specs
        )

    data: dict[str, Any] = {
        "schema_version": "2.0",
        "dataset": {
            "id": "regulatory-intelligence-synthetic-challenge-set",
            "title": "Regulatory intelligence synthetic challenge benchmark",
            "version": "2.0.0",
            "language": "en",
            "license": "Generated test data; distributed under the repository license",
            "provenance": {
                "kind": "synthetic",
                "generator": "scripts/build_synthetic_benchmark.py",
                "disclaimer": (
                    "All clauses, identifiers, dates and labels are fictional test fixtures. "
                    "They are not quotations from, summaries of, or legal interpretations of "
                    "any regulation or supervisory publication."
                ),
            },
        },
        "manifest": {
            "seed": 20260915,
            "generator_version": "1.0.0",
            "split_policy": (
                "Group-disjoint by family_id and source: 10 families per split; no document, "
                "query, change case or family appears in multiple splits."
            ),
            "challenge_tags": [
                "exact_terms",
                "hard_negative",
                "paraphrase_without_lexical_overlap",
                "modal_strengthening",
                "numeric_threshold_change",
                "deadline_change",
                "section_renumbering",
                "structure_only",
                "cosmetic_edit",
                "added_requirement",
                "removed_requirement",
            ],
            "counts": {},
        },
        "splits": split_payload,
        "retrieval": {"k": 5, "documents": documents, "queries": queries},
        "changes": {"materiality_threshold": 0.35, "cases": changes},
        "grounding": {"sources": grounding_sources, "claims": grounding_claims},
    }
    data["manifest"]["counts"] = dataset_statistics(data)
    validate_synthetic_dataset(data)
    return data


def _grounding_specs(
    *,
    index: int,
    split: str,
    local: int,
    family: str,
    evidence_id: str,
    section_id: str,
    artifact: str,
    years: int,
    evidence_text: str,
) -> list[dict[str, Any]]:
    valid = {
        "document_id": evidence_id,
        "section_id": section_id,
        "quote": evidence_text,
        "page": local,
        "version": "v2",
    }
    invalid = {
        "document_id": evidence_id,
        "section_id": section_id,
        "quote": f"The retention period is {years + 20} years.",
        "page": local,
        "version": "v2",
    }
    statuses = (
        ("supported", [valid]),
        ("partially_supported", [valid, invalid]),
        ("unsupported", [invalid]),
    )
    first = statuses[(index * 2) % len(statuses)]
    second = statuses[(index * 2 + 1) % len(statuses)]
    rows = []
    for offset, (status, citations) in enumerate((first, second), start=1):
        claim_number = index * 2 + offset
        rows.append(
            {
                "claim_id": f"grd-{claim_number:03d}",
                "split": split,
                "family_id": family,
                "difficulty": ("easy", "medium", "hard")[(claim_number - 1) % 3],
                "text": f"The retention rule for {artifact} is {years} years.",
                "expected_status": status,
                "citations": citations,
                "challenge_tags": ["exact_citation" if status == "supported" else "citation_gate"],
            }
        )
    return rows


def _change_specs(
    index: int, split: str, local: int, family: str, topic: str, article: int
) -> list[dict[str, Any]]:
    base_id = index * 4
    document_id = f"synthetic-{split}-{local:02d}"

    def section(section_id: str, text: str, version: str, title: str) -> dict[str, Any]:
        return {
            "document_id": document_id,
            "section_id": section_id,
            "title": title,
            "text": text,
            "page": local + 1,
            "version": version,
        }

    rows: list[tuple[bool, dict[str, Any] | None, dict[str, Any] | None, str, list[str]]] = []
    rows.append(
        (
            True,
            section(
                str(article + 4),
                f"Firms should document {topic} exceptions.",
                "v1",
                "Exceptions",
            ),
            section(
                str(article + 4),
                f"Firms must document {topic} exceptions.",
                "v2",
                "Exceptions",
            ),
            "easy",
            ["modal_strengthening"],
        )
    )
    if index % 3 == 0:
        rows.append(
            (
                True,
                None,
                section(
                    str(article + 5),
                    f"Firms must establish a documented {topic} escalation route.",
                    "v2",
                    "Escalation route",
                ),
                "medium",
                ["added_requirement", "structure_only"],
            )
        )
    elif index % 3 == 1:
        rows.append(
            (
                True,
                section(
                    str(article + 5),
                    f"Firms must maintain the {topic} control for 8 years.",
                    "v1",
                    "Control period",
                ),
                None,
                "medium",
                ["removed_requirement", "structure_only"],
            )
        )
    else:
        rows.append(
            (
                True,
                section(
                    str(article + 5),
                    f"Firms must review {topic} alerts within 72 hours.",
                    "v1",
                    "Alert review",
                ),
                section(
                    str(article + 5),
                    f"Firms must review {topic} alerts within 24 hours.",
                    "v2",
                    "Alert review",
                ),
                "medium",
                ["numeric_threshold_change", "deadline_change"],
            )
        )
    rows.extend(
        (
            (
                False,
                section(
                    str(article + 6),
                    f"Firms must monitor {topic} events.",
                    "v1",
                    "Monitoring",
                ),
                section(
                    f"{article + 6}A", f"Firms must monitor {topic} events.", "v2", "Monitoring"
                ),
                "hard",
                ["section_renumbering", "structure_only"],
            ),
            (
                False,
                section(
                    str(article + 7),
                    f"Teams should record material {topic} observations.",
                    "v1",
                    "Observations",
                ),
                section(
                    str(article + 7),
                    f"Teams should record relevant material {topic} observations.",
                    "v2",
                    "Observations",
                ),
                "hard",
                ["cosmetic_edit", "hard_negative"],
            ),
        )
    )
    result = []
    for offset, (expected, previous, current, _difficulty, tags) in enumerate(rows, start=1):
        # Rotate difficulty independently of the expected label. This prevents
        # per-difficulty metrics from containing only positives or negatives.
        difficulty = ("easy", "medium", "hard")[(index + offset - 1) % 3]
        result.append(
            {
                "id": f"chg-{base_id + offset:03d}",
                "split": split,
                "family_id": family,
                "difficulty": difficulty,
                "expected_material": expected,
                "previous": previous,
                "current": current,
                "challenge_tags": tags,
            }
        )
    return result


def write_dataset(data: dict[str, Any], dataset_path: Path, manifest_path: Path) -> None:
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_bytes(canonical_json_bytes(data))
    sidecar = {
        "schema_version": "1.0",
        "dataset_file": dataset_path.name,
        "dataset_sha256": sha256_json(data),
        "counts": dataset_statistics(data),
        "provenance": data["dataset"]["provenance"],
        "rebuild": "python scripts/build_synthetic_benchmark.py",
    }
    manifest_path.write_bytes(canonical_json_bytes(sidecar))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SYNTHETIC_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=SYNTHETIC_MANIFEST_PATH)
    args = parser.parse_args(argv)
    data = build_dataset()
    write_dataset(data, args.output, args.manifest)
    print(json.dumps(dataset_statistics(data), indent=2, sort_keys=True))
    print(f"Dataset written to {args.output} (sha256={sha256_json(data)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
