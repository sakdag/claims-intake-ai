from __future__ import annotations

import hashlib
import json
import os
from typing import Any, cast

import boto3

from claims_intake.llm.client import LlmClient, create_llm_client
from claims_intake.store.dynamo import CaseStore


def s3_client() -> Any:
    return boto3.client("s3", region_name=os.getenv("CLAIMS_AWS_REGION", "eu-north-1"))


def load_json_from_s3(bucket: str, key: str) -> dict[str, Any]:
    raw = s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("S3 object must be a JSON object")
    return cast(dict[str, Any], loaded)


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_store() -> CaseStore:
    return CaseStore()


def get_llm() -> LlmClient:
    return create_llm_client(
        provider=os.getenv("CLAIMS_MODEL_PROVIDER", "bedrock"),
        model_id=os.getenv("CLAIMS_MODEL_ID", "eu.amazon.nova-micro-v1:0"),
        region=os.getenv("CLAIMS_AWS_REGION", "eu-north-1"),
        profile=None,  # Lambda uses task role, not a local profile
    )


def poly_from_event(event: dict[str, Any]) -> dict[str, Any]:
    """Accept either inline polycontext or S3 pointer."""
    if "poly" in event:
        poly = event["poly"]
        if not isinstance(poly, dict):
            raise ValueError("'poly' must be an object")
        return cast(dict[str, Any], poly)
    if "bucket" in event and "key" in event:
        body = load_json_from_s3(event["bucket"], event["key"])
        # Support fixture shape {id, note, data} or raw polycontext
        if isinstance(body, dict) and "data" in body and isinstance(body["data"], dict):
            return cast(dict[str, Any], body["data"])
        return body
    raise ValueError("Event must include 'poly' or 'bucket'+'key'")
