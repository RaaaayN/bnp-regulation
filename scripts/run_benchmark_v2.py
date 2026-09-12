#!/usr/bin/env python3
"""Run the split-aware regulatory benchmark from the repository root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.benchmark_v2 import (
    DEFAULT_DATASET,
    DEFAULT_JSON_OUTPUT,
    DEFAULT_MARKDOWN_OUTPUT,
    run_benchmark_v2,
    write_reports,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", default="test", help="train, dev, test, or all")
    parser.add_argument(
        "--judge",
        choices=("deterministic", "gemini", "both"),
        default="deterministic",
        help="Gemini is advisory; deterministic metrics are always computed",
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260915)
    args = parser.parse_args(argv)

    report = run_benchmark_v2(
        args.dataset,
        split=args.split,
        judge_mode=args.judge,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    write_reports(report, json_path=args.json_output, markdown_path=args.markdown_output)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"JSON report written to {args.json_output}")
    print(f"Markdown report written to {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
