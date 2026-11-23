from claims_intake.data.labels import required_doc_presence
from claims_intake.eval.metrics import field_exact_match, policy_check_status_accuracy
from claims_intake.pipeline.claim_view import claim_view_from_extraction


def test_claim_view_from_extraction() -> None:
    view = claim_view_from_extraction(
        {
            "fields": [
                {"name": "dateOfLoss", "value": "2025-12-02"},
                {"name": "claimant", "value": "Ada"},
                {
                    "name": "damagedItems",
                    "value": [{"insuredSubject": "Roof", "risk": "Weight of snow or ice"}],
                },
            ]
        },
        fallback_claim_id="fallback",
    )
    assert view["claimId"] == "fallback"
    assert view["dateOfLoss"] == "2025-12-02"
    assert view["damagedItems"][0]["risk"] == "Weight of snow or ice"


def test_required_doc_uses_predicted_types() -> None:
    poly = {
        "contextDocuments": [{"extractedDocumentId": "1", "documentType": "invoice"}],
        "rules": [
            {
                "id": "r1",
                "rule": "Claim must be supported by police confirmation",
                "gate_name": "CLAIM_REGISTRATION",
            }
        ],
    }
    # Gold type is invoice — predicted says police_confirmation present
    out = required_doc_presence(
        poly,
        document_types=[{"document_id": "1", "document_type": "police_confirmation"}],
    )
    assert out[0]["status"] == "PASSED"


def test_field_exact_match_includes_damaged_items() -> None:
    gold = {
        "claimId": "1",
        "policyId": "PZ-PHI-1",
        "dateOfLoss": "2025-01-01",
        "dateOfReported": "2025-01-02",
        "lossEvent": "Flood",
        "claimant": "Ada",
        "product": "PHI",
        "damagedItems": [{"insuredSubject": "Contents", "risk": "Flood"}],
    }
    pred = [
        {"name": "claimId", "value": "1", "citations": [{"quote": "x"}]},
        {"name": "policyId", "value": "PZ-PHI-1", "citations": [{"quote": "x"}]},
        {"name": "dateOfLoss", "value": "2025-01-01", "citations": [{"quote": "x"}]},
        {"name": "dateOfReported", "value": "2025-01-02", "citations": [{"quote": "x"}]},
        {"name": "lossEvent", "value": "Flood", "citations": [{"quote": "x"}]},
        {"name": "claimant", "value": "Ada", "citations": [{"quote": "x"}]},
        {"name": "product", "value": "PHI", "citations": [{"quote": "x"}]},
        {
            "name": "damagedItems",
            "value": [{"insuredSubject": "Contents", "risk": "Flood"}],
            "citations": [{"quote": "x"}],
        },
    ]
    fem = field_exact_match(gold, pred)
    assert fem["per_field"]["damagedItems"] is True
    assert fem["field_accuracy"] == 1.0


def test_policy_check_status_accuracy() -> None:
    gold = {
        "coverage_period": {"status": "PASSED"},
        "policy_status": {"status": "ACTIVE" if False else "PASSED"},
        "peril_covered": {"status": "FAILED"},
    }
    pred = [
        {"rule_id": "det.coverage_period", "status": "PASSED"},
        {"rule_id": "det.policy_status", "status": "PASSED"},
        {"rule_id": "det.peril_covered", "status": "FAILED"},
    ]
    assert policy_check_status_accuracy(gold, pred)["accuracy"] == 1.0
