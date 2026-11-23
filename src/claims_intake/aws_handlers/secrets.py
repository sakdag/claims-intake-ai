"""Resolve secrets from env (local) or Secrets Manager (deployed)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=4)
def _fetch_secret_string(secret_arn: str) -> str:
    import boto3

    client = boto3.client("secretsmanager", region_name=os.getenv("CLAIMS_AWS_REGION", "eu-north-1"))
    resp: dict[str, Any] = client.get_secret_value(SecretId=secret_arn)
    value = resp.get("SecretString") or ""
    if not value:
        raise RuntimeError(f"empty secret: {secret_arn}")
    return str(value)


def approval_hmac_secret() -> str:
    """Prefer CLAIMS_APPROVAL_HMAC_SECRET; else load CLAIMS_APPROVAL_HMAC_SECRET_ARN."""
    direct = os.getenv("CLAIMS_APPROVAL_HMAC_SECRET", "").strip()
    if direct:
        return direct
    arn = os.getenv("CLAIMS_APPROVAL_HMAC_SECRET_ARN", "").strip()
    if not arn:
        raise RuntimeError("CLAIMS_APPROVAL_HMAC_SECRET or _ARN is not set")
    return _fetch_secret_string(arn)
