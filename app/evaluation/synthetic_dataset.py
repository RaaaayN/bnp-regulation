"""Validation helpers for the expanded synthetic regulatory benchmark."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SYNTHETIC_DATASET_PATH = Path("datasets/regulatory_benchmark_v2.json")
SYNTHETIC_MANIFEST_PATH = Path("datasets/regulatory_benchmark_v2.manifest.json")
SPLIT_NAMES = ("train", "dev", "test")
DIFFICULTIES = frozenset({"easy", "medium", "hard"})


class DatasetValidationError(ValueError):
    """Raised when a benchmark invariant is not satisfied."""


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON identically across platforms and Python invocations."""

    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_synthetic_dataset(path: Path = SYNTHETIC_DATASET_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_synthetic_dataset(data)
    return data


def dataset_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Return stable counts used by the sidecar manifest and CLI reporting."""

    queries = data["retrieval"]["queries"]
    changes = data["changes"]["cases"]
    grounding = data["grounding"]["claims"]
    return {
        "documents": len(data["retrieval"]["documents"]),
        "retrieval_queries": len(queries),
        "change_cases": len(changes),
        "grounding_claims": len(grounding),
        "material_changes": sum(case["expected_material"] for case in changes),
        "non_material_changes": sum(not case["expected_material"] for case in changes),
        "by_split": {
            split: {
                "documents": sum(doc["split"] == split for doc in data["retrieval"]["documents"]),
                "retrieval_queries": sum(case["split"] == split for case in queries),
                "change_cases": sum(case["split"] == split for case in changes),
                "grounding_claims": sum(case["split"] == split for case in grounding),
            }
            for split in SPLIT_NAMES
        },
        "by_difficulty": {
            difficulty: {
                "retrieval_queries": sum(case["difficulty"] == difficulty for case in queries),
                "change_cases": sum(case["difficulty"] == difficulty for case in changes),
                "grounding_claims": sum(
                    case["difficulty"] == difficulty for case in grounding
                ),
            }
            for difficulty in sorted(DIFFICULTIES)
        },
    }


def validate_synthetic_dataset(data: dict[str, Any]) -> None:
    """Validate provenance, referential integrity and group-disjoint splits."""

    required = {
        "schema_version",
        "dataset",
        "manifest",
        "splits",
        "retrieval",
        "changes",
        "grounding",
    }
    _require(not (required - data.keys()), f"missing fields: {sorted(required - data.keys())}")
    _require(data["schema_version"] == "2.0", "schema_version must be 2.0")
    provenance = data["dataset"].get("provenance", {})
    _require(provenance.get("kind") == "synthetic", "dataset must declare synthetic provenance")
    _require(bool(provenance.get("disclaimer")), "synthetic provenance requires a disclaimer")
    _require(set(data["splits"]) == set(SPLIT_NAMES), "splits must contain train/dev/test")

    documents = data["retrieval"].get("documents", [])
    queries = data["retrieval"].get("queries", [])
    changes = data["changes"].get("cases", [])
    grounding = data["grounding"].get("claims", [])
    _require(50 <= len(queries) <= 100, "benchmark must contain 50-100 retrieval queries")
    _require(len(changes) >= 100, "benchmark must contain at least 100 change cases")
    _require(bool(grounding), "benchmark must contain grounding claims")
    _require(len({doc["id"] for doc in documents}) == len(documents), "duplicate document id")
    _require(len({case["id"] for case in queries}) == len(queries), "duplicate query id")
    _require(len({case["id"] for case in changes}) == len(changes), "duplicate change id")
    _require(
        len({case["claim_id"] for case in grounding}) == len(grounding),
        "duplicate grounding claim id",
    )

    document_ids = {doc["id"] for doc in documents}
    source_to_split = {doc["source"]: doc["split"] for doc in documents}
    citations = {
        f'{doc["source"]} > {heading} > {article}'
        for doc in documents
        for heading, article in _document_sections(doc["content"])
    }
    family_splits: defaultdict[str, set[str]] = defaultdict(set)
    seen_tags: Counter[str] = Counter()

    for doc in documents:
        _validate_item(doc, "document")
        _require(doc["id"] in document_ids, "invalid document id")
        _require(doc["provenance"]["kind"] == "synthetic", "document provenance must be synthetic")
        family_splits[doc["family_id"]].add(doc["split"])

    split_ids: dict[str, dict[str, set[str]]] = {}
    for split in SPLIT_NAMES:
        payload = data["splits"][split]
        split_ids[split] = {key: set(values) for key, values in payload.items()}

    for case in queries:
        _validate_item(case, "retrieval query")
        _require(bool(case["relevant_citations"]), f'{case["id"]} has no relevance judgment')
        _require(
            set(case["relevant_citations"]) <= citations,
            f'{case["id"]} references an unknown citation',
        )
        for citation in case["relevant_citations"]:
            source = citation.split(" > ", 1)[0]
            _require(source_to_split[source] == case["split"], f'{case["id"]} crosses splits')
        family_splits[case["family_id"]].add(case["split"])
        seen_tags.update(case["challenge_tags"])

    for case in changes:
        _validate_item(case, "change case")
        _require(case.get("previous") or case.get("current"), f'{case["id"]} has no sections')
        family_splits[case["family_id"]].add(case["split"])
        seen_tags.update(case["challenge_tags"])

    grounding_source_ids = {
        f'{source["document_id"]}:{source["section_id"]}'
        for source in data["grounding"].get("sources", [])
    }
    for case in grounding:
        _validate_item(case, "grounding claim")
        _require(
            case["expected_status"] in {"supported", "partially_supported", "unsupported"},
            f'{case["claim_id"]} has invalid expected_status',
        )
        for citation in case.get("citations", []):
            source_id = f'{citation["document_id"]}:{citation["section_id"]}'
            # Deliberately invalid citations are allowed only for partial/unsupported cases.
            if case["expected_status"] == "supported":
                _require(
                    source_id in grounding_source_ids,
                    f'{case["claim_id"]} cites unknown source',
                )
        family_splits[case["family_id"]].add(case["split"])

    leaked = sorted(family for family, splits in family_splits.items() if len(splits) != 1)
    _require(not leaked, f"family leakage across splits: {leaked}")
    _require(seen_tags["hard_negative"] > 0, "hard negatives are required")
    _require(
        seen_tags["paraphrase_without_lexical_overlap"] > 0,
        "lexically divergent paraphrases are required",
    )
    _require(seen_tags["section_renumbering"] > 0, "section renumbering cases are required")

    expected_sets = {
        "document_ids": {doc["id"] for doc in documents},
        "retrieval_query_ids": {case["id"] for case in queries},
        "change_case_ids": {case["id"] for case in changes},
        "grounding_claim_ids": {case["claim_id"] for case in grounding},
    }
    for key, expected in expected_sets.items():
        declared = set().union(*(split_ids[split][key] for split in SPLIT_NAMES))
        _require(declared == expected, f"split manifest does not cover {key}")
        counts = Counter(
            identifier for split in SPLIT_NAMES for identifier in split_ids[split][key]
        )
        _require(all(count == 1 for count in counts.values()), f"{key} appears in multiple splits")
    for split in SPLIT_NAMES:
        _require(
            split_ids[split]["document_ids"]
            == {doc["id"] for doc in documents if doc["split"] == split},
            f"incorrect document_ids for {split}",
        )
        _require(
            split_ids[split]["retrieval_query_ids"]
            == {case["id"] for case in queries if case["split"] == split},
            f"incorrect retrieval_query_ids for {split}",
        )
        _require(
            split_ids[split]["change_case_ids"]
            == {case["id"] for case in changes if case["split"] == split},
            f"incorrect change_case_ids for {split}",
        )
        _require(
            split_ids[split]["grounding_claim_ids"]
            == {case["claim_id"] for case in grounding if case["split"] == split},
            f"incorrect grounding_claim_ids for {split}",
        )

    declared_counts = data["manifest"].get("counts")
    _require(declared_counts == dataset_statistics(data), "manifest counts are stale")


def validate_sidecar_manifest(
    data: dict[str, Any], manifest: dict[str, Any], dataset_path: Path
) -> None:
    _require(manifest.get("dataset_file") == dataset_path.name, "sidecar dataset_file mismatch")
    _require(manifest.get("dataset_sha256") == sha256_json(data), "sidecar checksum mismatch")
    _require(manifest.get("counts") == dataset_statistics(data), "sidecar counts mismatch")


def _validate_item(item: dict[str, Any], label: str) -> None:
    split = item.get("split")
    _require(split in SPLIT_NAMES, f"{label} has invalid split: {split}")
    _require(bool(item.get("family_id")), f"{label} has no family_id")
    if label != "document":
        _require(item.get("difficulty") in DIFFICULTIES, f"{label} has invalid difficulty")
        _require(bool(item.get("challenge_tags")), f"{label} has no challenge_tags")


def _document_sections(content: str) -> list[tuple[str, str]]:
    heading = ""
    sections: list[tuple[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            heading = line[2:]
        elif line.lower().startswith("article "):
            sections.append((heading, line.split(" - ", 1)[0]))
    return sections


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetValidationError(message)
