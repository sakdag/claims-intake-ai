from __future__ import annotations

from typing import Any

from claims_intake.aws_handlers.common import get_llm, get_store, poly_from_event
from claims_intake.models import CaseStatus
from claims_intake.pipeline.claim_view import claim_view_from_extraction
from claims_intake.pipeline.draft import draft_missing_document_request, short_case_summary
from claims_intake.pipeline.ingest import process_claim_package


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Run classify → extract → conflicts → policy checks and persist for review.
    Input: ingest output ({claim_id, bucket, key} and/or poly).
    """
    if event.get("skip_pipeline"):
        return {
            "claim_id": event["claim_id"],
            "skipped": True,
            "status": CaseStatus.NEEDS_REVIEW.value,
        }

    poly = poly_from_event(event)
    store = get_store()
    client = get_llm()

    result = process_claim_package(client, poly, classify=True, extract=True)
    extracted_claim = claim_view_from_extraction(
        result.get("extraction"),
        fallback_claim_id=result["claim_id"],
    )
    required = result.get("required_doc_rules") or []
    draft = draft_missing_document_request(
        claim_id=result["claim_id"],
        claimant=extracted_claim.get("claimant"),
        required_doc_outcomes=required,
        conflicts=result.get("conflicts") or [],
    )
    summary = short_case_summary(result)

    store.update_case(
        result["claim_id"],
        status=CaseStatus.PROCESSING.value,
        content_hash=event.get("content_hash"),
        classifications=result.get("classifications"),
        extraction=result.get("extraction"),
        conflicts=result.get("conflicts"),
        policy_checks=result.get("policy_checks"),
        required_doc_rules=required,
        summary=summary,
        missing_doc_draft=draft,
        model_id=result.get("model_id"),
        pipeline_version="0.1.0",
        source_bucket=event.get("bucket"),
        source_key=event.get("key"),
        ai_complete=True,
    )

    store.append_audit(
        claim_id=result["claim_id"],
        component="process_claim",
        action="ai_complete",
        model_version=result.get("model_id"),
        input_hash=event.get("content_hash"),
        output={
            "n_docs": len(result.get("classifications") or []),
            "n_conflicts": len(result.get("conflicts") or []),
            "next": "WaitForHumanReview",
        },
    )

    return {
        "claim_id": result["claim_id"],
        "skipped": False,
        "status": CaseStatus.PROCESSING.value,
        "summary": summary,
        "n_conflicts": len(result.get("conflicts") or []),
        "model_id": result.get("model_id"),
    }
