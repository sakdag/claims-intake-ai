from __future__ import annotations

import random
from collections import defaultdict
from datetime import date
from typing import Any

from claims_intake.pipeline.conflicts import amount_conflict_gold
from claims_intake.pipeline.policy_checks import (
    check_coverage_period,
    check_perils_covered,
    check_policy_status,
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def document_type_labels(poly: dict[str, Any]) -> list[dict[str, Any]]:
    docs = poly.get("contextDocuments") or []
    return [
        {
            "document_id": str(d.get("extractedDocumentId")),
            "document_type": d.get("documentType"),
            "channel": d.get("channel"),
        }
        for d in docs
    ]


def extraction_gold(poly: dict[str, Any]) -> dict[str, Any]:
    claim = poly.get("claim") or {}
    policy = poly.get("policy") or {}
    return {
        "claimId": claim.get("claimId"),
        "policyId": policy.get("policyId"),
        "dateOfLoss": claim.get("dateOfLoss"),
        "dateOfReported": claim.get("dateOfReported"),
        "lossEvent": claim.get("lossEvent"),
        "claimant": claim.get("claimant"),
        "policyStatusToDateOfLoss": policy.get("policyStatusToDateOfLoss"),
        "product": policy.get("product"),
        "coveragePeriodFrom": policy.get("coveragePeriodFrom"),
        "coveragePeriodTo": policy.get("coveragePeriodTo"),
        "damagedItems": claim.get("damagedItems") or [],
    }


def report_vs_loss_plausible(claim: dict[str, Any], max_lag_days: int = 365) -> dict[str, Any]:
    loss = _parse_date(claim.get("dateOfLoss"))
    reported = _parse_date(claim.get("dateOfReported"))
    if not loss or not reported:
        return {"status": "UNRESOLVABLE", "reason": "missing dates"}
    if reported < loss:
        return {"status": "FAILED", "reason": "reported before loss"}
    lag = (reported - loss).days
    if lag > max_lag_days:
        return {"status": "FAILED", "reason": f"report lag {lag}d > {max_lag_days}d"}
    return {"status": "PASSED", "reason": f"report lag {lag}d"}


def required_doc_presence(
    poly: dict[str, Any],
    *,
    document_types: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Deterministic labels for rules that clearly require a named document type.
    Heuristic: rule text mentions a known document phrase → expect that type present.

    Pass `document_types` (classifier output) for the live/eval path. When omitted,
    gold `contextDocuments[].documentType` is used (label derivation only).
    """
    if document_types is not None:
        present = {d.get("document_type") or d.get("documentType") for d in document_types}
    else:
        present = {d.get("documentType") for d in (poly.get("contextDocuments") or [])}
    phrase_to_type = {
        "certificate of unit ownership": "certificate_of_ownership",
        "land registry extract": "certificate_of_ownership",
        "certificate of ownership": "certificate_of_ownership",
        "police confirmation": "police_confirmation",
        "police report": "police_confirmation",
        "fire brigade": "fire_brigade_report",
        "nhmi": "nhmi_report",
        "hydrometeorological": "nhmi_report",
        "site inspection": "site_inspection",
        "photo evidence": "photo_evidence",
    }
    outcomes: list[dict[str, Any]] = []
    for rule in poly.get("rules") or []:
        text = (rule.get("rule") or "").lower()
        if "supported by" not in text and "accompanied by" not in text:
            continue
        matched_type = None
        for phrase, doc_type in phrase_to_type.items():
            if phrase in text:
                matched_type = doc_type
                break
        if not matched_type:
            continue
        ok = matched_type in present
        outcomes.append(
            {
                "rule_id": str(rule.get("id")),
                "required_document_type": matched_type,
                "status": "PASSED" if ok else "FAILED",
                "reason": (
                    f"{matched_type} present"
                    if ok
                    else f"{matched_type} missing from claim documents"
                ),
                "gate": rule.get("gate_name"),
            }
        )
    return outcomes


def derive_labels_for_polycontext(row: dict[str, Any]) -> dict[str, Any]:
    poly = row["data"]
    claim = poly.get("claim") or {}
    policy = poly.get("policy") or {}

    coverage = check_coverage_period(claim, policy)
    status = check_policy_status(policy)
    peril = check_perils_covered(claim, policy)
    plaus = report_vs_loss_plausible(claim)

    return {
        "id": row["id"],
        "claim_id": claim.get("claimId"),
        "product": policy.get("product"),
        "loss_event": claim.get("lossEvent"),
        "document_types": document_type_labels(poly),
        "extraction_gold": extraction_gold(poly),
        "policy_checks": {
            "coverage_period": {
                "status": coverage.status.value,
                "reason": coverage.reason,
            },
            "policy_status": {
                "status": status.status.value,
                "reason": status.reason,
            },
            "peril_covered": {
                "status": peril.status.value,
                "reason": peril.reason,
            },
            "report_vs_loss": plaus,
        },
        "required_doc_rules": required_doc_presence(poly),
        "amount_conflicts": amount_conflict_gold(
            [
                {
                    "document_id": str(d.get("extractedDocumentId")),
                    "document_type": d.get("documentType"),
                    "content": d.get("extractedDocumentContent") or "",
                }
                for d in (poly.get("contextDocuments") or [])
            ]
        ),
    }


def stratified_claim_split(
    labels: list[dict[str, Any]],
    *,
    n_dev: int = 50,
    n_test: int = 150,
    seed: int = 42,
) -> dict[str, Any]:
    """Build a 200-claim working set stratified by product × loss_event, then 50/150 split."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for lab in labels:
        key = (str(lab.get("product") or "?"), str(lab.get("loss_event") or "?"))
        buckets[key].append(lab)

    for key in buckets:
        rng.shuffle(buckets[key])

    need = n_dev + n_test
    pool: list[dict[str, Any]] = []
    keys = sorted(buckets.keys())
    while len(pool) < need and any(buckets[k] for k in keys):
        for key in keys:
            if buckets[key] and len(pool) < need:
                pool.append(buckets[key].pop())

    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lab in pool:
        by_product[str(lab.get("product") or "?")].append(lab)

    dev: list[str] = []
    test: list[str] = []
    for _, items in sorted(by_product.items()):
        rng.shuffle(items)
        n = len(items)
        n_d = int(round(n * (n_dev / need))) if need else 0
        for i, lab in enumerate(items):
            cid = str(lab["claim_id"])
            if i < n_d:
                dev.append(cid)
            else:
                test.append(cid)

    rng.shuffle(dev)
    rng.shuffle(test)
    if len(dev) > n_dev:
        test = dev[n_dev:] + test
        dev = dev[:n_dev]
    elif len(dev) < n_dev:
        take = n_dev - len(dev)
        dev = dev + test[:take]
        test = test[take:]
    test = test[:n_test]

    return {
        "seed": seed,
        "n_dev": len(dev),
        "n_test": len(test),
        "dev": sorted(dev),
        "test": sorted(test),
    }
