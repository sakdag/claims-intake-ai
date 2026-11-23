from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dynamo(value: Any) -> Any:
    """Convert floats to Decimal for DynamoDB."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


class CaseStore:
    def __init__(
        self,
        *,
        cases_table: str | None = None,
        audit_table: str | None = None,
        region: str | None = None,
    ) -> None:
        region = region or os.getenv("CLAIMS_AWS_REGION") or "eu-north-1"
        self.cases_table_name = cases_table or os.environ["CASES_TABLE"]
        self.audit_table_name = audit_table or os.environ["AUDIT_TABLE"]
        dynamodb = boto3.resource("dynamodb", region_name=region)
        self.cases = dynamodb.Table(self.cases_table_name)
        self.audit = dynamodb.Table(self.audit_table_name)

    def get_case(self, claim_id: str) -> dict[str, Any] | None:
        resp = self.cases.get_item(Key={"pk": f"CLAIM#{claim_id}", "sk": "CASE"})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def put_case_if_absent(self, case: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """
        Idempotent create. Returns (case, created).
        If a case already exists with the same content_hash, returns existing and created=False.
        If hash differs, overwrites for reprocessing.
        """
        claim_id = case["claim_id"]
        existing = self.get_case(claim_id)
        if existing and existing.get("content_hash") == case.get("content_hash"):
            return existing, False

        item = {
            "pk": f"CLAIM#{claim_id}",
            "sk": "CASE",
            "entity_type": "case",
            "updated_at": _now(),
            **case,
        }
        if not existing:
            item["created_at"] = _now()
        else:
            item["created_at"] = existing.get("created_at") or _now()

        self.cases.put_item(Item=_to_dynamo(item))
        return _from_dynamo(item), True

    def update_case(self, claim_id: str, **fields: Any) -> dict[str, Any]:
        existing = self.get_case(claim_id) or {
            "pk": f"CLAIM#{claim_id}",
            "sk": "CASE",
            "claim_id": claim_id,
            "created_at": _now(),
        }
        existing.update(fields)
        existing["updated_at"] = _now()
        existing["pk"] = f"CLAIM#{claim_id}"
        existing["sk"] = "CASE"
        existing["entity_type"] = "case"
        self.cases.put_item(Item=_to_dynamo(existing))
        return _from_dynamo(existing)

    def append_audit(
        self,
        *,
        claim_id: str,
        component: str,
        action: str,
        output: dict[str, Any] | None = None,
        model_version: str | None = None,
        input_hash: str | None = None,
    ) -> dict[str, Any]:
        ts = _now()
        event_id = str(uuid.uuid4())
        item = {
            "pk": f"CLAIM#{claim_id}",
            "sk": f"AUDIT#{ts}#{event_id}",
            "entity_type": "audit",
            "claim_id": claim_id,
            "event_id": event_id,
            "component": component,
            "action": action,
            "model_version": model_version,
            "input_hash": input_hash,
            "output": output or {},
            "at": ts,
        }
        self.audit.put_item(Item=_to_dynamo(item))
        return _from_dynamo(item)

    def list_audit(self, claim_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        resp = self.audit.query(
            KeyConditionExpression=Key("pk").eq(f"CLAIM#{claim_id}")
            & Key("sk").begins_with("AUDIT#"),
            ScanIndexForward=True,
            Limit=limit,
        )
        return [_from_dynamo(i) for i in resp.get("Items", [])]

    def list_cases(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        # MVP: scan with optional filter (demo scale only)
        kwargs: dict[str, Any] = {"Limit": limit}
        if status:
            kwargs["FilterExpression"] = "entity_type = :e AND #s = :status"
            kwargs["ExpressionAttributeNames"] = {"#s": "status"}
            kwargs["ExpressionAttributeValues"] = {":e": "case", ":status": status}
        else:
            kwargs["FilterExpression"] = "entity_type = :e"
            kwargs["ExpressionAttributeValues"] = {":e": "case"}
        resp = self.cases.scan(**kwargs)
        return [_from_dynamo(i) for i in resp.get("Items", [])]
