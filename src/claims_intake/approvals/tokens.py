"""Signed, single-use approval tokens for outbound claimant messages."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApprovalToken:
    token: str
    expires_at: int
    action_hash: str


def action_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def issue_approval_token(
    *,
    secret: str,
    claim_id: str,
    action: str,
    payload: dict[str, Any],
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> ApprovalToken:
    """Bind a short-lived HMAC token to an exact outbound action payload."""
    ts = now if now is not None else int(time.time())
    expires_at = ts + ttl_seconds
    action_hash = action_payload_hash(payload)
    body = f"{claim_id}|{action}|{action_hash}|{expires_at}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    token = f"{expires_at}.{action_hash}.{sig}"
    return ApprovalToken(token=token, expires_at=expires_at, action_hash=action_hash)


def verify_approval_token(
    *,
    secret: str,
    token: str,
    claim_id: str,
    action: str,
    payload: dict[str, Any],
    used_token_ids: set[str],
    now: int | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason). Rejects expired, reused, or payload-mismatched tokens."""
    ts = now if now is not None else int(time.time())
    try:
        expires_s, action_hash, sig = token.split(".", 2)
        expires_at = int(expires_s)
    except ValueError:
        return False, "malformed token"

    if token in used_token_ids:
        return False, "token already used"
    if ts > expires_at:
        return False, "token expired"

    expected_hash = action_payload_hash(payload)
    if not hmac.compare_digest(action_hash, expected_hash):
        return False, "payload mismatch"

    body = f"{claim_id}|{action}|{action_hash}|{expires_at}"
    expected_sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False, "bad signature"
    return True, "ok"
