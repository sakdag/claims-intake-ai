from __future__ import annotations

from typing import Any

from claims_intake.aws_handlers.common import get_store
from claims_intake.models import CaseStatus


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """Mark case ready/closed after human review + optional SES send."""
    review = event.get("review") or {}
    email = event.get("email") or {}
    claim_id = str(
        review.get("claim_id") or email.get("claim_id") or event.get("claim_id") or ""
    )
    if not claim_id:
        raise ValueError("claim_id required")

    store = get_store()
    store.update_case(
        claim_id,
        status=CaseStatus.READY.value,
        sfn_task_token=None,
        workflow_complete=True,
        outbound_sent=bool(email.get("sent")),
        outbound_message_id=email.get("message_id"),
    )
    store.append_audit(
        claim_id=claim_id,
        component="finalize",
        action="completed",
        output={
            "email_sent": bool(email.get("sent")),
            "email_skipped": bool(email.get("skipped")),
            "message_id": email.get("message_id"),
        },
    )
    return {
        "claim_id": claim_id,
        "status": CaseStatus.READY.value,
        "email_sent": bool(email.get("sent")),
    }
