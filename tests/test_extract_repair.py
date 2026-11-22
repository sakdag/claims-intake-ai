from claims_intake.pipeline.extract import _normalize_fields


def test_repair_pipe_collapsed_fields() -> None:
    raw = [
        {
            "name": "claimId|policyId|dateOfLoss|product",
            "value": "260000101|PZ-PHI-000000002|2026-08-05|Household",
            "quote": "policy PZ-PHI-000000002",
            "document_id": "1",
        }
    ]
    fields = _normalize_fields(raw, documents=[])
    by = {f["name"]: f["value"] for f in fields}
    assert by["claimId"] == "260000101"
    assert by["policyId"] == "PZ-PHI-000000002"
    assert by["dateOfLoss"] == "2026-08-05"
    assert by["product"] == "PHI"
