from claims_intake.pipeline.draft import draft_missing_document_request, short_case_summary


def test_draft_lists_missing_docs() -> None:
    text = draft_missing_document_request(
        claim_id="260000101",
        claimant="SYN-Given-1",
        required_doc_outcomes=[
            {"required_document_type": "certificate_of_ownership", "status": "FAILED"},
        ],
        conflicts=[{"kind": "amount_mismatch"}],
    )
    assert "260000101" in text
    assert "certificate of ownership" in text
    assert "DRAFT" in text


def test_summary() -> None:
    s = short_case_summary(
        {
            "claim_id": "1",
            "conflicts": [{}],
            "policy_checks": [{"status": "UNRESOLVABLE"}],
        }
    )
    assert "1" in s
    assert "conflict" in s
