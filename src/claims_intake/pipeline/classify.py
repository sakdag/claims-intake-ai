from __future__ import annotations

from typing import Any

from claims_intake.llm.client import LlmClient, complete_json
from claims_intake.models import DocumentType

DOCUMENT_TYPES = [t.value for t in DocumentType]

_SYSTEM = """You classify insurance claim documents for Elm & Stone Home Insurance.
Return ONLY valid JSON with keys:
- document_type: one of the allowed types
- confidence: number 0-1
- rationale: short reason

Allowed document_type values:
""" + "\n".join(f"- {t}" for t in DOCUMENT_TYPES)


def classify_document(
    client: LlmClient,
    *,
    document_id: str,
    content: str,
    channel: str | None = None,
) -> dict[str, Any]:
    user = (
        f"document_id: {document_id}\n"
        f"channel: {channel or 'unknown'}\n"
        f"---\n{content[:6000]}\n---"
    )
    data, resp = complete_json(client, system=_SYSTEM, user=user, max_tokens=256)
    doc_type = str(data.get("document_type") or "").strip()
    if doc_type not in DOCUMENT_TYPES:
        doc_type = _fallback_type(content)
    return {
        "document_id": document_id,
        "document_type": doc_type,
        "confidence": float(data.get("confidence") or 0.0),
        "rationale": str(data.get("rationale") or ""),
        "model_id": resp.model_id,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
    }


def _fallback_type(content: str) -> str:
    lower = content.lower()
    heuristics = [
        ("first notice of loss", DocumentType.FIRST_NOTICE_OF_LOSS.value),
        ("online form", DocumentType.ONLINE_FORM_SUBMISSION.value),
        ("invoice", DocumentType.INVOICE.value),
        ("deposit", DocumentType.DEPOSIT_INVOICE.value),
        ("police", DocumentType.POLICE_CONFIRMATION.value),
        ("fire brigade", DocumentType.FIRE_BRIGADE_REPORT.value),
        ("ownership", DocumentType.CERTIFICATE_OF_OWNERSHIP.value),
        ("nhmi", DocumentType.NHMI_REPORT.value),
        ("meteorolog", DocumentType.NHMI_REPORT.value),
        ("inspection", DocumentType.SITE_INSPECTION.value),
        ("damage calculation", DocumentType.DAMAGE_CALCULATION.value),
        ("photo", DocumentType.PHOTO_EVIDENCE.value),
    ]
    for needle, doc_type in heuristics:
        if needle in lower:
            return doc_type
    return DocumentType.FIRST_NOTICE_OF_LOSS.value
