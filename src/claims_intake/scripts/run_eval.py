"""Run offline eval on the locked split (dev by default)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claims_intake.data.io import load_polycontexts, write_jsonl
from claims_intake.data.labels import derive_labels_for_polycontext
from claims_intake.eval.metrics import (
    accuracy,
    confusion_pairs,
    field_exact_match,
    macro_f1,
    policy_check_status_accuracy,
)
from claims_intake.llm.client import create_llm_client
from claims_intake.pipeline.ingest import process_claim_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--splits", type=Path, default=Path("data/derived/splits.json"))
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--limit", type=int, default=5, help="Max claims (cost control)")
    parser.add_argument("--out", type=Path, default=Path("eval/results"))
    parser.add_argument("--skip-llm", action="store_true", help="Only deterministic label stats")
    parser.add_argument("--classify-only", action="store_true")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model-id", default=None)
    args = parser.parse_args(argv)

    if not (args.raw / "data.parquet").exists():
        print("Missing data/raw — run claims-download-data", file=sys.stderr)
        return 1

    splits = json.loads(args.splits.read_text())
    selected = list(splits[args.split])[: args.limit]

    rows = load_polycontexts(args.raw)
    by_claim = {str(r["data"]["claim"]["claimId"]): r for r in rows}

    client = None
    if not args.skip_llm:
        client = create_llm_client(provider=args.provider, model_id=args.model_id)

    y_true: list[str] = []
    y_pred: list[str] = []
    field_scores: list[float] = []
    cite_scores: list[float] = []
    per_field_hits: Counter[str] = Counter()
    per_field_n: Counter[str] = Counter()
    policy_acc_scores: list[float] = []
    policy_per_check_hits: Counter[str] = Counter()
    policy_per_check_n: Counter[str] = Counter()
    policy_status_counts: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    token_in = token_out = 0

    for cid in selected:
        row = by_claim[cid]
        poly = row["data"]
        labels = derive_labels_for_polycontext(row)

        for check_name, check in labels["policy_checks"].items():
            policy_status_counts[f"gold:{check_name}:{check['status']}"] += 1

        if client is None:
            continue

        try:
            result = process_claim_package(
                client,
                poly,
                classify=True,
                extract=not args.classify_only,
            )
        except Exception as exc:  # noqa: BLE001 — per-claim isolation for offline eval
            records.append({"claim_id": cid, "error": str(exc)})
            print(f"claim {cid} failed: {exc}", file=sys.stderr)
            continue

        gold_types = {str(d["document_id"]): d["document_type"] for d in labels["document_types"]}
        for c in result["classifications"]:
            y_true.append(gold_types[c["document_id"]])
            y_pred.append(c["document_type"])
            token_in += int(c.get("input_tokens") or 0)
            token_out += int(c.get("output_tokens") or 0)

        if result.get("extraction"):
            fem = field_exact_match(labels["extraction_gold"], result["extraction"]["fields"])
            field_scores.append(fem["field_accuracy"])
            cite_scores.append(fem["citation_rate"])
            for name, ok in (fem.get("per_field") or {}).items():
                per_field_n[name] += 1
                per_field_hits[name] += int(ok)
            token_in += int(result["extraction"].get("input_tokens") or 0)
            token_out += int(result["extraction"].get("output_tokens") or 0)

        pca = policy_check_status_accuracy(
            labels["policy_checks"],
            result.get("policy_checks") or [],
        )
        policy_acc_scores.append(pca["accuracy"])
        for name, ok in (pca.get("per_check") or {}).items():
            policy_per_check_n[name] += 1
            policy_per_check_hits[name] += int(ok)
            policy_status_counts[f"pred_match:{name}:{'hit' if ok else 'miss'}"] += 1

        records.append({"claim_id": cid, "result": result})

    per_field_accuracy = {
        name: (per_field_hits[name] / per_field_n[name]) if per_field_n[name] else None
        for name in sorted(per_field_n)
    }

    summary: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "split": args.split,
        "n_claims": len(selected),
        "model_id": None if client is None else client.model_id,
        "tokens": {"input": token_in, "output": token_out},
        "classification_accuracy": accuracy(y_true, y_pred) if y_true else None,
        "classification_macro_f1": macro_f1(y_true, y_pred) if y_true else None,
        "classification_errors": [
            {"gold": a, "pred": b, "n": n} for a, b, n in confusion_pairs(y_true, y_pred)
        ]
        if y_true
        else [],
        "extraction_field_accuracy_mean": (
            sum(field_scores) / len(field_scores) if field_scores else None
        ),
        "extraction_per_field_accuracy": per_field_accuracy,
        "extraction_citation_rate_mean": (
            sum(cite_scores) / len(cite_scores) if cite_scores else None
        ),
        "policy_check_status_accuracy_mean": (
            sum(policy_acc_scores) / len(policy_acc_scores) if policy_acc_scores else None
        ),
        "policy_check_per_check_accuracy": {
            name: (policy_per_check_hits[name] / policy_per_check_n[name])
            if policy_per_check_n[name]
            else None
            for name in sorted(policy_per_check_n)
        },
        "policy_check_status_counts": dict(policy_status_counts),
        "amount_conflict_note": (
            "Amount-conflict detector is not scored against independent labels; "
            "omitted from headline metrics."
        ),
        "claim_ids": selected,
        "n_errors": sum(1 for r in records if r.get("error")),
        "n_scored": sum(1 for r in records if "result" in r),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    summary_path = args.out / f"{run_id}_{args.split}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    if records:
        write_jsonl(args.out / f"{run_id}_{args.split}_records.jsonl", records)

    print(json.dumps(summary, indent=2))
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
