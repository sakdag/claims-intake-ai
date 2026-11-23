from __future__ import annotations

import json
import os
from typing import Any

import boto3
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from claims_intake.approvals import issue_approval_token, verify_approval_token
from claims_intake.models import CaseStatus
from claims_intake.store.dynamo import CaseStore

def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="Elm & Stone Claims Intake", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EDITABLE_FIELDS = (
    "claimId",
    "policyId",
    "dateOfLoss",
    "dateOfReported",
    "lossEvent",
    "claimant",
    "product",
)


def _store() -> CaseStore:
    return CaseStore()


def _hmac_secret() -> str:
    return os.getenv("CLAIMS_APPROVAL_HMAC_SECRET", "demo-change-me")


def _sfn():
    return boto3.client("stepfunctions", region_name=os.getenv("CLAIMS_AWS_REGION", "eu-north-1"))


def _used_tokens(case: dict[str, Any]) -> set[str]:
    return set(case.get("used_approval_tokens") or [])


def _field_workspace(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge AI extraction + adjuster corrections into a review grid."""
    extracted = (case.get("extraction") or {}).get("fields") or []
    by_name: dict[str, dict[str, Any]] = {}
    for f in extracted:
        name = str(f.get("name") or "")
        if not name:
            continue
        cites = f.get("citations") or []
        by_name[name] = {
            "name": name,
            "ai_value": f.get("value"),
            "citation": (cites[0].get("quote") if cites else None),
            "document_id": (cites[0].get("document_id") if cites else None),
        }
    corrections = case.get("corrected_fields") or {}
    rows = []
    for name in EDITABLE_FIELDS:
        base = by_name.get(name) or {"name": name, "ai_value": None, "citation": None}
        corrected = corrections.get(name)
        rows.append(
            {
                **base,
                "corrected_value": corrected,
                "effective_value": corrected if corrected is not None else base.get("ai_value"),
            }
        )
    return rows


def _enrich(case: dict[str, Any], audit: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    waiting = bool(case.get("sfn_task_token"))
    status = case.get("status")
    if waiting:
        phase = "awaiting_adjuster"
        phase_label = "Paused — waiting for adjuster"
    elif status == CaseStatus.READY.value:
        phase = "complete"
        phase_label = "Complete"
    elif status == CaseStatus.CLOSED.value:
        phase = "rejected"
        phase_label = "Rejected / closed"
    elif status == CaseStatus.WAITING_APPROVAL.value:
        phase = "sending"
        phase_label = "Approved — sending / finalizing"
    elif case.get("ai_complete"):
        phase = "ai_done"
        phase_label = "AI finished — registering review hold"
    else:
        phase = "processing"
        phase_label = "AI processing"

    summary = case.get("summary") or case.get("review_summary")
    if waiting:
        instruction = (
            "Compare each working value to its citation. Correct only mistakes, "
            "then Approve & send (or reject). Saving corrections does not resume the workflow."
        )
    else:
        instruction = "Case is not waiting on adjuster action right now."

    return {
        "case": case,
        "audit": audit or [],
        "review": {
            "phase": phase,
            "phase_label": phase_label,
            "instruction": instruction,
            "waiting_on_adjuster": waiting,
            "can_approve_send": waiting and bool(case.get("missing_doc_draft")),
            "can_reject": waiting,
            "fields": _field_workspace(case),
            "documents": case.get("classifications") or [],
            "conflicts": case.get("conflicts") or [],
            "policy_checks": case.get("policy_checks") or [],
            "draft": case.get("missing_doc_draft"),
            "summary": summary,
            "execution_arn": case.get("sfn_execution_arn"),
            "outbound_message_id": case.get("outbound_message_id"),
        },
    }


class CorrectionBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class RejectReviewBody(BaseModel):
    reason: str = "adjuster_rejected"


class ApproveSendBody(BaseModel):
    skip_email: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me() -> dict[str, Any]:
    """Identity echo for authenticated callers (API Gateway JWT already verified)."""
    return {
        "service": "elm-stone-claims-intake",
        "auth": "cognito_jwt",
    }


@app.get("/queue")
def review_queue() -> dict[str, Any]:
    """Open work: cases waiting on an adjuster (task token) or mid-approval."""
    store = _store()
    open_statuses = {
        CaseStatus.NEEDS_REVIEW.value,
        CaseStatus.WAITING_APPROVAL.value,
        CaseStatus.PROCESSING.value,
    }
    items = []
    for status in open_statuses:
        items.extend(store.list_cases(status=status, limit=50))
    # Prefer waiting_on_adjuster first
    dedup: dict[str, dict[str, Any]] = {}
    for c in items:
        dedup[str(c.get("claim_id"))] = c
    cases = list(dedup.values())
    cases.sort(key=lambda c: (0 if c.get("sfn_task_token") else 1, c.get("updated_at") or ""))
    return {
        "cases": [
            {
                "claim_id": c.get("claim_id"),
                "status": c.get("status"),
                "summary": c.get("summary") or c.get("review_summary"),
                "waiting_on_adjuster": bool(c.get("sfn_task_token")),
                "n_conflicts": len(c.get("conflicts") or []),
                "model_id": c.get("model_id"),
                "updated_at": c.get("updated_at"),
            }
            for c in cases
        ]
    }


@app.get("/cases")
def list_cases(status: str | None = Query(default="needs_review")) -> dict[str, Any]:
    cases = _store().list_cases(status=status, limit=50)
    return {"cases": cases}


@app.get("/cases/{claim_id}")
def get_case(claim_id: str) -> dict[str, Any]:
    case = _store().get_case(claim_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    audit = _store().list_audit(claim_id)
    return _enrich(case, audit)


@app.post("/cases/{claim_id}/corrections")
def correct_case(claim_id: str, body: CorrectionBody) -> dict[str, Any]:
    """
    Adjuster overrides of AI-extracted fields.
    Saved for audit / eval feedback — does not by itself resume Step Functions.
    """
    store = _store()
    case = store.get_case(claim_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    cleaned = {k: v for k, v in body.fields.items() if k in EDITABLE_FIELDS and v is not None}
    corrections = list(case.get("corrections") or [])
    corrections.append({"fields": cleaned, "note": body.note})
    updated = store.update_case(
        claim_id,
        corrections=corrections,
        corrected_fields={**(case.get("corrected_fields") or {}), **cleaned},
    )
    store.append_audit(
        claim_id=claim_id,
        component="review_ui",
        action="correction",
        output={"fields": cleaned, "note": body.note},
    )
    return _enrich(updated, store.list_audit(claim_id))


def _issue_payload(case: dict[str, Any], claim_id: str) -> dict[str, Any]:
    draft = case.get("missing_doc_draft")
    if not draft:
        raise HTTPException(status_code=400, detail="no missing_doc_draft on case")
    return {
        "claim_id": claim_id,
        "action": "send_missing_docs",
        "body": draft,
        "to": os.getenv("SES_TO_EMAIL", ""),
        "from": os.getenv("SES_FROM_EMAIL", ""),
        "subject": f"Additional documents needed for claim {claim_id}",
    }


@app.post("/cases/{claim_id}/approve-and-send")
def approve_and_send(claim_id: str, body: ApproveSendBody) -> dict[str, Any]:
    """
    One-click adjuster action: signed approval + SendTaskSuccess so SFN continues to SES.
    """
    store = _store()
    case = store.get_case(claim_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    task_token = case.get("sfn_task_token")
    if not task_token:
        raise HTTPException(
            status_code=409,
            detail="Workflow is not waiting for adjuster review (no task token)",
        )

    payload = _issue_payload(case, claim_id)
    tok = issue_approval_token(
        secret=_hmac_secret(),
        claim_id=claim_id,
        action="send_missing_docs",
        payload=payload,
        ttl_seconds=3600,
    )
    used = _used_tokens(case)
    ok, reason = verify_approval_token(
        secret=_hmac_secret(),
        token=tok.token,
        claim_id=claim_id,
        action="send_missing_docs",
        payload=payload,
        used_token_ids=used,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    used.add(tok.token)
    callback = {
        "claim_id": claim_id,
        "approved": True,
        "body": payload.get("body"),
        "to": payload.get("to"),
        "from": payload.get("from"),
        "subject": payload.get("subject"),
        "skip_email": body.skip_email,
    }
    try:
        _sfn().send_task_success(taskToken=task_token, output=json.dumps(callback))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"SendTaskSuccess failed: {exc}") from exc

    updated = store.update_case(
        claim_id,
        used_approval_tokens=sorted(used),
        pending_approval=None,
        sfn_task_token=None,
        status=CaseStatus.WAITING_APPROVAL.value,
    )
    store.append_audit(
        claim_id=claim_id,
        component="approvals",
        action="approve_and_send",
        output={"reason": reason, "skip_email": body.skip_email, "to": payload.get("to")},
    )
    return {
        **_enrich(updated, store.list_audit(claim_id)),
        "workflow_continued": True,
        "email_will_send": not body.skip_email,
    }


@app.post("/cases/{claim_id}/review/reject")
def reject_review(claim_id: str, body: RejectReviewBody) -> dict[str, Any]:
    store = _store()
    case = store.get_case(claim_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    task_token = case.get("sfn_task_token")
    if not task_token:
        raise HTTPException(status_code=409, detail="workflow is not waiting on a task token")
    try:
        _sfn().send_task_failure(
            taskToken=task_token,
            error="AdjusterRejected",
            cause=body.reason[:700],
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"SendTaskFailure failed: {exc}") from exc

    updated = store.update_case(
        claim_id,
        status=CaseStatus.CLOSED.value,
        sfn_task_token=None,
        reject_reason=body.reason,
    )
    store.append_audit(
        claim_id=claim_id,
        component="review_ui",
        action="rejected",
        output={"reason": body.reason},
    )
    return _enrich(updated, store.list_audit(claim_id))
