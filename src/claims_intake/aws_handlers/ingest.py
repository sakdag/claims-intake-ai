from __future__ import annotations

from typing import Any

from claims_intake.aws_handlers.common import content_hash, get_store, poly_from_event
from claims_intake.models import CaseStatus


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Idempotent ingest.
    Input: {bucket, key} or {poly: {...}}.
    Keeps Step Functions state small by not echoing document bodies.
    """
    poly = poly_from_event(event)
    claim = poly.get("claim") or {}
    claim_id = str(claim.get("claimId") or "")
    if not claim_id:
        raise ValueError("poly.claim.claimId is required")

    digest = content_hash(poly)
    store = get_store()
    case, created = store.put_case_if_absent(
        {
            "claim_id": claim_id,
            "status": CaseStatus.PROCESSING.value,
            "content_hash": digest,
            "pipeline_version": "0.1.0",
            "source_bucket": event.get("bucket"),
            "source_key": event.get("key"),
        }
    )

    store.append_audit(
        claim_id=claim_id,
        component="ingest",
        action="accepted" if created else "idempotent_replay",
        input_hash=digest,
        output={"created": created, "status": case.get("status")},
    )

    # Only skip when a prior run fully completed (human + email path done).
    skip_pipeline = (not created) and (
        case.get("workflow_complete") is True
        or case.get("status") in {CaseStatus.READY.value, CaseStatus.CLOSED.value}
    )

    out: dict[str, Any] = {
        "claim_id": claim_id,
        "content_hash": digest,
        "created": created,
        "skip_pipeline": skip_pipeline,
        "bucket": event.get("bucket"),
        "key": event.get("key"),
    }
    # Inline poly only when no S3 pointer (local/dev invocations)
    if not event.get("bucket"):
        out["poly"] = poly
    return out
