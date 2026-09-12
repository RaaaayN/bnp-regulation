import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.evaluation.synthetic_dataset import (
    DatasetValidationError,
    dataset_statistics,
    load_synthetic_dataset,
    validate_synthetic_dataset,
    validate_sidecar_manifest,
)
from scripts.build_synthetic_benchmark import build_dataset, main


def test_expanded_benchmark_has_required_scale_and_balanced_splits() -> None:
    data = build_dataset()
    stats = dataset_statistics(data)

    assert stats["documents"] == 30
    assert stats["retrieval_queries"] == 60
    assert stats["change_cases"] == 120
    assert stats["grounding_claims"] == 60
    assert stats["material_changes"] == 60
    assert stats["non_material_changes"] == 60
    assert stats["by_split"] == {
        split: {
            "documents": 10,
            "retrieval_queries": 20,
            "change_cases": 40,
            "grounding_claims": 20,
        }
        for split in ("train", "dev", "test")
    }


def test_expanded_benchmark_is_deterministic_and_marks_synthetic_provenance() -> None:
    first = build_dataset()
    second = build_dataset()

    assert first == second
    assert first["dataset"]["provenance"]["kind"] == "synthetic"
    assert "not quotations" in first["dataset"]["provenance"]["disclaimer"]
    assert all(
        document["provenance"]["kind"] == "synthetic"
        for document in first["retrieval"]["documents"]
    )


def test_challenge_set_contains_hard_negatives_paraphrases_and_renumbering() -> None:
    data = build_dataset()
    query_tags = {
        tag for query in data["retrieval"]["queries"] for tag in query["challenge_tags"]
    }
    change_tags = {
        tag for case in data["changes"]["cases"] for tag in case["challenge_tags"]
    }

    assert "hard_negative" in query_tags
    assert "paraphrase_without_lexical_overlap" in query_tags
    assert "section_renumbering" in change_tags
    assert {query["difficulty"] for query in data["retrieval"]["queries"]} == {
        "easy",
        "medium",
        "hard",
    }


def test_validator_rejects_family_leakage() -> None:
    data = build_dataset()
    leaked = deepcopy(data)
    leaked["retrieval"]["queries"][0]["family_id"] = leaked["retrieval"]["queries"][-1][
        "family_id"
    ]

    with pytest.raises(DatasetValidationError, match="family leakage"):
        validate_synthetic_dataset(leaked)


def test_builder_writes_loadable_dataset_and_checksum_manifest(tmp_path: Path) -> None:
    dataset_path = tmp_path / "benchmark.json"
    manifest_path = tmp_path / "manifest.json"

    assert main(["--output", str(dataset_path), "--manifest", str(manifest_path)]) == 0
    data = load_synthetic_dataset(dataset_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_sidecar_manifest(data, manifest, dataset_path)


def test_checked_in_dataset_matches_the_generator() -> None:
    assert load_synthetic_dataset() == build_dataset()
