from claims_intake.models import RuleStatus
from claims_intake.pipeline.policy_checks import (
    check_coverage_period,
    check_perils_covered,
    check_policy_status,
)


def test_policy_status_issued_is_unresolvable() -> None:
    out = check_policy_status({"policyStatusToDateOfLoss": "Issued"})
    assert out.status == RuleStatus.UNRESOLVABLE


def test_policy_status_active_passes() -> None:
    out = check_policy_status({"policyStatusToDateOfLoss": "Active"})
    assert out.status == RuleStatus.PASSED


def test_coverage_period() -> None:
    claim = {"dateOfLoss": "2026-01-15"}
    policy = {"coveragePeriodFrom": "2025-01-01", "coveragePeriodTo": "2026-12-31"}
    assert check_coverage_period(claim, policy).status == RuleStatus.PASSED


def test_peril_covered() -> None:
    claim = {
        # Subject string need not match the policy subject name — risk must be covered.
        "damagedItems": [{"insuredSubject": "Absorbent cotton dish towels", "risk": "Flood"}],
    }
    policy = {
        "coverage": {
            "insuredSubjects": [
                {"name": "Household contents", "risks": ["Flood", "Fire"]},
            ]
        }
    }
    assert check_perils_covered(claim, policy).status == RuleStatus.PASSED


def test_peril_not_covered() -> None:
    claim = {"damagedItems": [{"insuredSubject": "Window", "risk": "Earthquake"}]}
    policy = {
        "coverage": {
            "insuredSubjects": [
                {"name": "House", "risks": ["Storm", "Fire"]},
            ]
        }
    }
    assert check_perils_covered(claim, policy).status == RuleStatus.FAILED
