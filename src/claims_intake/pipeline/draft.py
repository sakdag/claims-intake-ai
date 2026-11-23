from __future__ import annotations

from typing import Any


def draft_missing_document_request(
    *,
    claim_id: str,
    claimant: str | None,
    required_doc_outcomes: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> str:
    """Template draft — never sent without signed adjuster approval."""
    missing = [
        r.get("required_document_type")
        for r in required_doc_outcomes
        if r.get("status") == "FAILED"
    ]
    lines = [
        f"Subject: Additional documents needed for claim {claim_id}",
        "",
        f"Dear {claimant or 'Policyholder'},",
        "",
        "Thank you for submitting your claim to Elm & Stone Home Insurance.",
        "Before we can complete our assessment, we need a few additional items:",
        "",
    ]
    if missing:
        for doc in missing:
            lines.append(f"- {str(doc).replace('_', ' ')}")
    else:
        lines.append("- Please confirm the claimed amounts across your invoices and estimates.")
    if conflicts:
        lines.append("")
        lines.append(
            "We also noticed differences between amounts stated in your documents "
            "and would appreciate clarification."
        )
    lines.extend(
        [
            "",
            "Please reply with the requested documents at your earliest convenience.",
            "",
            "Kind regards,",
            "Elm & Stone Claims Team",
            "",
            "[DRAFT — requires adjuster approval before send]",
        ]
    )
    return "\n".join(lines)


def short_case_summary(result: dict[str, Any]) -> str:
    claim_id = result.get("claim_id")
    n_conflicts = len(result.get("conflicts") or [])
    checks = result.get("policy_checks") or []
    failed = [c for c in checks if c.get("status") == "FAILED"]
    unresolved = [c for c in checks if c.get("status") == "UNRESOLVABLE"]
    parts = [f"Claim {claim_id} prepared for adjuster review."]
    if failed:
        parts.append(f"{len(failed)} policy check(s) failed.")
    if unresolved:
        parts.append(f"{len(unresolved)} check(s) need a human.")
    if n_conflicts:
        parts.append(f"{n_conflicts} amount conflict(s) flagged.")
    return " ".join(parts)
