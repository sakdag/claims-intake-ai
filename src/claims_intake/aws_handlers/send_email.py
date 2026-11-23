from __future__ import annotations

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import boto3
from botocore.exceptions import ClientError

from claims_intake.approvals import verify_approval_token
from claims_intake.aws_handlers.common import get_store
from claims_intake.aws_handlers.secrets import approval_hmac_secret
from claims_intake.models import CaseStatus


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Verify the adjuster-signed approval token, consume it once, then SES-send.
    Input is the full state including $.review from SendTaskSuccess payload.
    """
    review = event.get("review") or {}
    claim_id = str(review.get("claim_id") or event.get("claim_id") or "")
    if not claim_id:
        raise ValueError("claim_id missing from review callback")

    store = get_store()

    if review.get("skip_email"):
        store.append_audit(
            claim_id=claim_id,
            component="send_email",
            action="skipped",
            output={
                "reason": review.get("reason") or "skip_email",
                "approved_by": review.get("approved_by"),
            },
        )
        return {"sent": False, "skipped": True, "claim_id": claim_id}

    body = review.get("body") or ""
    to_addr = review.get("to") or os.environ.get("SES_TO_EMAIL") or ""
    from_addr = review.get("from") or os.environ.get("SES_FROM_EMAIL") or ""
    subject = review.get("subject") or f"Additional documents needed for claim {claim_id}"
    token = str(review.get("approval_token") or "")
    if not token:
        raise ValueError("approval_token missing — refusing outbound send")

    payload = {
        "claim_id": claim_id,
        "action": "send_missing_docs",
        "body": body,
        "to": to_addr,
        "from": from_addr,
        "subject": subject,
    }
    case = store.get_case(claim_id) or {}
    used = set(case.get("used_approval_tokens") or [])
    ok, reason = verify_approval_token(
        secret=approval_hmac_secret(),
        token=token,
        claim_id=claim_id,
        action="send_missing_docs",
        payload=payload,
        used_token_ids=used,
    )
    if not ok:
        raise ValueError(f"approval rejected: {reason}")

    try:
        store.consume_approval_token(claim_id, token)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise ValueError("approval token already consumed") from exc
        raise

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

    store.update_case(
        claim_id,
        status=CaseStatus.WAITING_APPROVAL.value,
        outbound_message_id=message_id,
        outbound_to=to_addr,
        outbound_from=from_addr,
        approved_by=review.get("approved_by"),
    )
    store.append_audit(
        claim_id=claim_id,
        component="send_email",
        action="ses_sent",
        output={
            "message_id": message_id,
            "to": to_addr,
            "from": from_addr,
            "approved_by": review.get("approved_by"),
            "approval": reason,
        },
    )
    return {
        "sent": True,
        "claim_id": claim_id,
        "message_id": message_id,
        "to": to_addr,
        "from": from_addr,
        "approved_by": review.get("approved_by"),
    }
