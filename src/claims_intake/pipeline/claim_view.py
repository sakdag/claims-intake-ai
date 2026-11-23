"""Build a claim dict for policy gates from AI extraction (not gold claim fields)."""

from __future__ import annotations

from typing import Any


def claim_view_from_extraction(
    extraction: dict[str, Any] | None,
    *,
    fallback_claim_id: str = "unknown",
) -> dict[str, Any]:
    """
    Map extracted fields into the shape expected by deterministic policy checks.
    Policy records still come from the policy database / package `policy` object.
    """
    fields = {
        str(f.get("name")): f.get("value")
        for f in ((extraction or {}).get("fields") or [])
        if f.get("name")
    }
    damaged = fields.get("damagedItems")
    if damaged is None:
        damaged_items: list[Any] = []
    elif isinstance(damaged, list):
        damaged_items = damaged
    else:
        damaged_items = []

    return {
        "claimId": fields.get("claimId") or fallback_claim_id,
        "policyId": fields.get("policyId"),
        "dateOfLoss": fields.get("dateOfLoss"),
        "dateOfReported": fields.get("dateOfReported"),
        "lossEvent": fields.get("lossEvent"),
        "claimant": fields.get("claimant"),
        "product": fields.get("product"),
        "damagedItems": damaged_items,
    }
