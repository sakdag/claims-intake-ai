from __future__ import annotations

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import boto3

from claims_intake.aws_handlers.common import get_store
from claims_intake.models import CaseStatus


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Send the adjuster-approved missing-document request via SES.
    Input is the full state including $.review from SendTaskSuccess payload.
    """
    review = event.get("review") or {}
    claim_id = str(review.get("claim_id") or event.get("claim_id") or "")
    if not claim_id:
        raise ValueError("claim_id missing from review callback")

    if review.get("skip_email"):
        store = get_store()
        store.append_audit(
            claim_id=claim_id,
            component="send_email",
            action="skipped",
            output={"reason": review.get("reason") or "skip_email"},
        )
        return {"sent": False, "skipped": True, "claim_id": claim_id}

    body = review.get("body") or ""
    to_addr = review.get("to") or os.environ.get("SES_TO_EMAIL") or ""
    from_addr = review.get("from") or os.environ.get("SES_FROM_EMAIL") or ""
    subject = review.get("subject") or f"Additional documents needed for claim {claim_id}"

    if not body or not to_addr or not from_addr:
        raise ValueError("email body/to/from required to send")

    ses = boto3.client("ses", region_name=os.getenv("CLAIMS_AWS_REGION", "eu-north-1"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    resp = ses.send_raw_email(
        Source=from_addr,
        Destinations=[to_addr],
        RawMessage={"Data": msg.as_string()},
    )
    message_id = resp.get("MessageId")

    store = get_store()
    store.update_case(
        claim_id,
        status=CaseStatus.WAITING_APPROVAL.value,  # brief; finalize moves to ready
        outbound_message_id=message_id,
        outbound_to=to_addr,
        outbound_from=from_addr,
    )
    store.append_audit(
        claim_id=claim_id,
        component="send_email",
        action="ses_sent",
        output={"message_id": message_id, "to": to_addr, "from": from_addr},
    )
    return {
        "sent": True,
        "claim_id": claim_id,
        "message_id": message_id,
        "to": to_addr,
        "from": from_addr,
    }
