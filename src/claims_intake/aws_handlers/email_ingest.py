"""SES → S3 raw email → claim package JSON in the inbox prefix."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

import boto3

from claims_intake.pipeline.email_ingest import email_to_polycontext, wrap_poly_for_inbox


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """
    Triggered when SES stores a raw email under the email-raw/ prefix.
    Writes inbox/{claimId}-email.json so the existing Starter Lambda starts SFN.
    """
    s3 = boto3.client("s3")
    inbox_prefix = os.environ.get("INBOX_PREFIX", "inbox/")
    written: list[dict[str, str]] = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        if key.endswith("/"):
            continue
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
        poly = email_to_polycontext(raw)
        package = wrap_poly_for_inbox(poly)
        claim_id = str(package["data"]["claim"]["claimId"])
        out_key = f"{inbox_prefix.rstrip('/')}/{claim_id}-email.json"
        s3.put_object(
            Bucket=bucket,
            Key=out_key,
            Body=json.dumps(package).encode("utf-8"),
            ContentType="application/json",
        )
        written.append({"source": key, "inbox_key": out_key, "claim_id": claim_id})

    return {"written": written}
