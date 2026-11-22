"""Derive deterministic labels and lock a 50/150 stratified split."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claims_intake.data.io import load_polycontexts, write_jsonl
from claims_intake.data.labels import derive_labels_for_polycontext, stratified_claim_split


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/derived"))
    parser.add_argument("--n-dev", type=int, default=50)
    parser.add_argument("--n-test", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    if not (args.raw / "data.parquet").exists():
        print("Missing data/raw/data.parquet — run claims-download-data first.", file=sys.stderr)
        return 1

    rows = load_polycontexts(args.raw)
    labels = [derive_labels_for_polycontext(r) for r in rows]
    write_jsonl(args.out / "labels.jsonl", labels)

    split = stratified_claim_split(
        labels, n_dev=args.n_dev, n_test=args.n_test, seed=args.seed
    )
    split_path = args.out / "splits.json"
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(split, indent=2) + "\n")

    # Summary stats for the session log / README
    status_counts: dict[str, int] = {}
    for lab in labels:
        st = lab["policy_checks"]["policy_status"]["status"]
        status_counts[st] = status_counts.get(st, 0) + 1

    print(f"labels={len(labels)} -> {args.out / 'labels.jsonl'}")
    print(
        f"split seed={split['seed']} "
        f"dev={split['n_dev']} test={split['n_test']} -> {split_path}"
    )
    print(f"policy_status distribution (full set): {status_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
