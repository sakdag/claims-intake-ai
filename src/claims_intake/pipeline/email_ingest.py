"""Turn a raw inbound email (MIME) into a claim package polycontext."""

from __future__ import annotations

import hashlib
import re
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from typing import Any


def parse_raw_email(raw: bytes) -> EmailMessage:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(msg, EmailMessage)
    return msg


def _claim_id_from_message(msg: Message) -> str:
    for header in ("X-Claim-Id", "X-Claim-ID"):
        value = msg.get(header)
        if value and re.fullmatch(r"[A-Za-z0-9_-]{4,64}", value.strip()):
            return value.strip()
    subject = msg.get("Subject") or ""
    m = re.search(r"\b(26\d{6,9}|CLM[-_]?\d{4,})\b", subject, re.I)
    if m:
        return re.sub(r"[^A-Za-z0-9]", "", m.group(1))
    digest = hashlib.sha1((msg.get("Message-ID") or subject or "email").encode()).hexdigest()[:10]
    return f"email-{digest}"


def _part_text(part: Message) -> str:
    get_content = getattr(part, "get_content", None)
    if callable(get_content):
        try:
            payload = get_content()
            return payload if isinstance(payload, str) else str(payload)
        except Exception:  # noqa: BLE001
            pass
    raw = part.get_payload(decode=True)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(part.get_payload())


def _walk_text_parts(msg: Message) -> list[tuple[str, str, str]]:
    """Return list of (filename, content_type, text)."""
    parts: list[tuple[str, str, str]] = []
    if msg.is_multipart():
        for i, part in enumerate(msg.walk()):
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            filename = part.get_filename() or f"part-{i}"
            if ctype.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv", ".json")):
                text = _part_text(part)
                if text.strip():
                    parts.append((filename, ctype, text))
    else:
        text = _part_text(msg)
        if text.strip():
            parts.append(("body.txt", msg.get_content_type(), text))
    return parts


def email_to_polycontext(raw: bytes, *, default_product: str = "PHI") -> dict[str, Any]:
    """
    Build a GNOTHEIA-like polycontext from a raw MIME email.

    Enough structure for classify/extract to run: claim header + contextDocuments
    from the body and text attachments.
    """
    msg = parse_raw_email(raw)
    claim_id = _claim_id_from_message(msg)
    subject = msg.get("Subject") or f"Email claim {claim_id}"
    sender = msg.get("From") or "unknown@example.com"
    parts = _walk_text_parts(msg)
    if not parts:
        parts = [("body.txt", "text/plain", subject)]

    documents = []
    for i, (filename, ctype, text) in enumerate(parts, start=1):
        doc_type = "first_notice_of_loss" if i == 1 else "online_form_submission"
        if "invoice" in filename.lower():
            doc_type = "invoice"
        documents.append(
            {
                "extractedDocumentId": f"EMAIL-{claim_id}-{i:03d}",
                "documentType": doc_type,
                "extractedDocumentContent": text[:20000],
                "sourceFilename": filename,
                "contentType": ctype,
            }
        )

    return {
        "claim": {
            "claimId": claim_id,
            "policyId": None,
            "dateOfLoss": None,
            "dateOfReported": None,
            "lossEvent": subject[:200],
            "claimant": sender,
            "product": default_product,
        },
        "contextDocuments": documents,
        "intakeChannel": "email",
        "emailMeta": {
            "subject": subject,
            "from": sender,
            "messageId": msg.get("Message-ID"),
        },
    }


def wrap_poly_for_inbox(poly: dict[str, Any]) -> dict[str, Any]:
    """Shape expected by S3 inbox → starter → ingest (`data.claim`)."""
    claim_id = str((poly.get("claim") or {}).get("claimId") or "unknown")
    return {
        "id": claim_id,
        "note": f"Inbound email intake for {claim_id}",
        "data": poly,
    }
