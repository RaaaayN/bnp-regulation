#!/usr/bin/env python3
"""Download the allowlisted EUR-Lex corpus with auditable provenance."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.ingestion.public_corpus import DEFAULT_MAX_BYTES, acquire_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("datasets/public_sources.json"),
        help="Checked-in source allowlist",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/public-corpus/raw"),
        help="Destination for downloaded snapshots and provenance.json",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-request timeout in seconds"
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum accepted size for each source",
    )
    args = parser.parse_args()
    provenance = acquire_corpus(
        args.manifest,
        args.output_dir,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
    )
    print(f"Downloaded {len(provenance['snapshots'])} official EUR-Lex documents")
    print(f"Provenance: {args.output_dir / 'provenance.json'}")


if __name__ == "__main__":
    main()
