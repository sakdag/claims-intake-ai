from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    FIRST_NOTICE_OF_LOSS = "first_notice_of_loss"
    ONLINE_FORM_SUBMISSION = "online_form_submission"
    PHOTO_EVIDENCE = "photo_evidence"
    SITE_INSPECTION = "site_inspection"
    DAMAGE_CALCULATION = "damage_calculation"
    INVOICE = "invoice"
    DEPOSIT_INVOICE = "deposit_invoice"
    POLICE_CONFIRMATION = "police_confirmation"
    FIRE_BRIGADE_REPORT = "fire_brigade_report"
    CERTIFICATE_OF_OWNERSHIP = "certificate_of_ownership"
    NHMI_REPORT = "nhmi_report"


class GateName(StrEnum):
    FIRST_NOTIFICATION_OF_LOSS = "FIRST_NOTIFICATION_OF_LOSS"
    CLAIM_REGISTRATION = "CLAIM_REGISTRATION"
    CLAIM_ASSESSMENT = "CLAIM_ASSESSMENT"


class RuleStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNRESOLVABLE = "UNRESOLVABLE"


class CaseStatus(StrEnum):
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    WAITING_APPROVAL = "waiting_approval"
    CLOSED = "closed"


class Citation(BaseModel):
    document_id: str
    document_type: str | None = None
    quote: str
    start_char: int | None = None
    end_char: int | None = None


class ExtractedField(BaseModel):
    name: str
    value: Any
    citations: list[Citation] = Field(default_factory=list)
    confidence: float | None = None


class ConflictFlag(BaseModel):
    kind: str
    summary: str
    document_ids: list[str] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)


class RuleOutcome(BaseModel):
    rule_id: str
    gate: GateName
    status: RuleStatus
    reason: str
    evaluator: str  # "deterministic" | "llm" | ...
    model_version: str | None = None


class AuditEvent(BaseModel):
    claim_id: str
    component: str
    action: str
    model_version: str | None = None
    input_hash: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CaseRecord(BaseModel):
    claim_id: str
    status: CaseStatus = CaseStatus.PROCESSING
    pipeline_version: str = "0.1.0"
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    conflicts: list[ConflictFlag] = Field(default_factory=list)
    rule_outcomes: list[RuleOutcome] = Field(default_factory=list)
    summary: str | None = None
    missing_doc_draft: str | None = None
