from claims_intake.approvals import issue_approval_token, verify_approval_token


def test_signed_single_use_approval() -> None:
    secret = "test-secret"
    payload = {
        "claim_id": "260001894",
        "action": "send_missing_docs",
        "to": "claimant@example.com",
        "body": "Please send ownership certificate.",
    }
    tok = issue_approval_token(
        secret=secret,
        claim_id="260001894",
        action="send_missing_docs",
        payload=payload,
        now=1_700_000_000,
        ttl_seconds=60,
    )
    ok, reason = verify_approval_token(
        secret=secret,
        token=tok.token,
        claim_id="260001894",
        action="send_missing_docs",
        payload=payload,
        used_token_ids=set(),
        now=1_700_000_010,
    )
    assert ok and reason == "ok"

    # Tweaked body must fail
    tweaked = {**payload, "body": "Please send everything."}
    ok2, reason2 = verify_approval_token(
        secret=secret,
        token=tok.token,
        claim_id="260001894",
        action="send_missing_docs",
        payload=tweaked,
        used_token_ids=set(),
        now=1_700_000_010,
    )
    assert not ok2 and reason2 == "payload mismatch"

    # Reuse must fail
    ok3, reason3 = verify_approval_token(
        secret=secret,
        token=tok.token,
        claim_id="260001894",
        action="send_missing_docs",
        payload=payload,
        used_token_ids={tok.token},
        now=1_700_000_010,
    )
    assert not ok3 and reason3 == "token already used"
