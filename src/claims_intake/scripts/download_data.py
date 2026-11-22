"""Download GNOTHEIA v2 parquet files into data/raw/ and write a VERSION pin."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DATASET_REPO = "gratex/GNOTHEIA-synthetic-insurance-dataset-v2"
FILES = ("data.parquet", "rules-dataset.parquet")
EXPECTED_POLYCONTEXTS = 2305
EXPECTED_RULES = 496


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/raw"),
        help="Directory for parquet files (default: data/raw)",
    )
    parser.add_argument(
        "--revision",
        default="main",
        help="Hugging Face revision (branch, tag, or commit SHA)",
    )
    args = parser.parse_args(argv)

    try:
        from huggingface_hub import hf_hub_download
        import pandas as pd
    except ImportError:
        print(
            "Missing deps. Install with: pip install -e '.[data]'",
            file=sys.stderr,
        )
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name in FILES:
        local = hf_hub_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            filename=name,
            revision=args.revision,
            local_dir=str(args.out),
        )
        paths[name] = local
        print(f"downloaded {name} -> {local}")

    poly = pd.read_parquet(args.out / "data.parquet")
    rules = pd.read_parquet(args.out / "rules-dataset.parquet")
    n_poly, n_rules = len(poly), len(rules)
    print(f"polycontexts={n_poly} rules={n_rules}")

    if n_poly != EXPECTED_POLYCONTEXTS or n_rules != EXPECTED_RULES:
        print(
            f"WARNING: expected {EXPECTED_POLYCONTEXTS}/{EXPECTED_RULES}, "
            f"got {n_poly}/{n_rules}",
            file=sys.stderr,
        )

    version = {
        "repo": DATASET_REPO,
        "revision": args.revision,
        "polycontexts": n_poly,
        "rules": n_rules,
        "files": {name: {"sha256": _sha256(args.out / name)} for name in FILES},
    }
    version_path = args.out / "VERSION.json"
    version_path.write_text(json.dumps(version, indent=2) + "\n")
    print(f"wrote {version_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
