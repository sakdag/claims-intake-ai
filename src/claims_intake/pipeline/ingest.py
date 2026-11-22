from __future__ import annotations

from typing import Any

from claims_intake.llm.client import LlmClient
from claims_intake.pipeline.classify import classify_document
from claims_intake.pipeline.conflicts import detect_amount_conflicts
from claims_intake.pipeline.extract import extract_fields
from claims_intake.pipeline.policy_checks import (
    check_coverage_period,
    check_perils_covered,
    check_policy_status,
)


def documents_from_polycontext(poly: dict[str, Any], *, hide_types: bool = True) -> list[dict[str, Any]]:
    docs = []
    for d in poly.get("contextDocuments") or []:
        item = {
            "document_id": str(d.get("extractedDocumentId")),
            "content": d.get("extractedDocumentContent") or "",
            "channel": d.get("channel"),
            "extractedDocumentContent": d.get("extractedDocumentContent") or "",
            "extractedDocumentId": d.get("extractedDocumentId"),
        }
        if not hide_types:
            item["document_type"] = d.get("documentType")
            item["documentType"] = d.get("documentType")
        docs.append(item)
    return docs


def process_claim_package(
    client: LlmClient,
    poly: dict[str, Any],
    *,
    classify: bool = True,
    extract: bool = True,
) -> dict[str, Any]:
    """Offline / Lambda-shared intake path for one polycontext."""
    claim = poly.get("claim") or {}
    policy = poly.get("policy") or {}
    claim_id = str(claim.get("claimId") or "unknown")

    raw_docs = documents_from_polycontext(poly, hide_types=True)
    classifications: list[dict[str, Any]] = []
    if classify:
        for d in raw_docs:
            result = classify_document(
                client,
                document_id=d["document_id"],
                content=d["content"],
                channel=d.get("channel"),
            )
            classifications.append(result)
            d["document_type"] = result["document_type"]
            d["documentType"] = result["document_type"]
    else:
        # Use gold types when skipping LLM classify (deterministic stages / cheaper eval)
        for d, gold in zip(raw_docs, poly.get("contextDocuments") or [], strict=False):
            d["document_type"] = gold.get("documentType")
            d["documentType"] = gold.get("documentType")

    extraction = extract_fields(client, claim_id=claim_id, documents=raw_docs) if extract else None

    # Conflict detection uses gold or predicted types already stamped on docs
    conflicts = detect_amount_conflicts(raw_docs)

    policy_outcomes = [
        check_coverage_period(claim, policy),
        check_policy_status(policy),
        check_perils_covered(claim, policy),
    ]

    return {
        "claim_id": claim_id,
        "classifications": classifications,
        "extraction": extraction,
        "conflicts": [c.model_dump() for c in conflicts],
        "policy_checks": [o.model_dump() for o in policy_outcomes],
        "model_id": client.model_id,
    }
