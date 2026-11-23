from __future__ import annotations

from typing import Any

from claims_intake.aws_handlers.common import get_store
from claims_intake.models import CaseStatus


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Callback worker for Step Functions waitForTaskToken.
    Stores the task token on the case and leaves the execution RUNNING
    until the review API calls SendTaskSuccess / SendTaskFailure.
    """
    claim_id = str(event.get("claim_id") or "")
    task_token = event.get("taskToken")
    if not claim_id or not task_token:
        raise ValueError("claim_id and taskToken are required")

    store = get_store()
    store.update_case(
        claim_id,
        status=CaseStatus.NEEDS_REVIEW.value,
        sfn_task_token=task_token,
        sfn_execution_arn=event.get("executionArn"),
        review_summary=event.get("summary"),
    )
    store.append_audit(
        claim_id=claim_id,
        component="wait_for_review",
        action="awaiting_human",
        output={
            "executionArn": event.get("executionArn"),
            "has_task_token": True,
        },
    )
    # Do NOT return success to SFN — callback pattern waits for SendTaskSuccess.
    return {"registered": True, "claim_id": claim_id}
