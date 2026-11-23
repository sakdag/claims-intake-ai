from __future__ import annotations

from datetime import date
from typing import Any

from claims_intake.models import GateName, RuleOutcome, RuleStatus


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def check_coverage_period(claim: dict[str, Any], policy: dict[str, Any]) -> RuleOutcome:
    loss = _parse_date(claim.get("dateOfLoss"))
    start = _parse_date(policy.get("coveragePeriodFrom"))
    end = _parse_date(policy.get("coveragePeriodTo"))
    if not loss or not start or not end:
        return RuleOutcome(
            rule_id="det.coverage_period",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.UNRESOLVABLE,
            reason="Missing loss or coverage period dates",
            evaluator="deterministic",
        )

    ok = start <= loss <= end
    return RuleOutcome(
        rule_id="det.coverage_period",
        gate=GateName.CLAIM_REGISTRATION,
        status=RuleStatus.PASSED if ok else RuleStatus.FAILED,
        reason=(
            f"dateOfLoss {loss} within [{start}, {end}]"
            if ok
            else f"dateOfLoss {loss} outside [{start}, {end}]"
        ),
        evaluator="deterministic",
    )


def check_policy_status(policy: dict[str, Any]) -> RuleOutcome:
    """Active → PASS, Expired → FAIL, Issued → UNRESOLVABLE (human)."""
    status = (policy.get("policyStatusToDateOfLoss") or "").strip()
    if status == "Active":
        return RuleOutcome(
            rule_id="det.policy_status",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.PASSED,
            reason="Policy Active at date of loss",
            evaluator="deterministic",
        )
    if status == "Expired":
        return RuleOutcome(
            rule_id="det.policy_status",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.FAILED,
            reason="Policy Expired at date of loss",
            evaluator="deterministic",
        )
    if status == "Issued":
        return RuleOutcome(
            rule_id="det.policy_status",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.UNRESOLVABLE,
            reason="Policy status Issued is ambiguous — needs human review",
            evaluator="deterministic",
        )
    return RuleOutcome(
        rule_id="det.policy_status",
        gate=GateName.CLAIM_REGISTRATION,
        status=RuleStatus.UNRESOLVABLE,
        reason=f"Unknown policy status {status!r}",
        evaluator="deterministic",
    )


def check_perils_covered(claim: dict[str, Any], policy: dict[str, Any]) -> RuleOutcome:
    """
    Check each damaged item's risk against the union of covered risks on the policy.

    Extracted insuredSubject strings are often fine-grained inventory names, while
    the policy uses coarse subjects (e.g. House). Matching on risk keeps the gate
    aligned with what extract can reliably produce.
    """
    damaged = claim.get("damagedItems") or []
    coverage = policy.get("coverage") or {}
    subjects = coverage.get("insuredSubjects") or policy.get("insuredSubjects") or []
    all_risks: set[str] = set()
    for subj in subjects:
        all_risks |= {str(r) for r in (subj.get("risks") or [])}

    if not damaged:
        return RuleOutcome(
            rule_id="det.peril_covered",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.UNRESOLVABLE,
            reason="No damagedItems on claim",
            evaluator="deterministic",
        )

    failures: list[str] = []
    for item in damaged:
        risk = item.get("risk")
        if risk not in all_risks:
            failures.append(f"{risk!r} not in covered risks {sorted(all_risks)}")

    if failures:
        return RuleOutcome(
            rule_id="det.peril_covered",
            gate=GateName.CLAIM_REGISTRATION,
            status=RuleStatus.FAILED,
            reason="; ".join(failures),
            evaluator="deterministic",
        )
    return RuleOutcome(
        rule_id="det.peril_covered",
        gate=GateName.CLAIM_REGISTRATION,
        status=RuleStatus.PASSED,
        reason="All damaged-item risks are covered on the policy",
        evaluator="deterministic",
    )
