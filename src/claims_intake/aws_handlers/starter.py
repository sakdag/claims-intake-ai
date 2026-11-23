from __future__ import annotations

import json
import os
import time
import urllib.parse
import uuid
from typing import Any

import boto3


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """S3 ObjectCreated → StartExecution with {bucket, key}."""
    sm = boto3.client("stepfunctions")
    state_machine = os.environ["STATE_MACHINE_ARN"]
    started = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        safe = key.replace("/", "-")[-40:]
        name = f"c-{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe}"[:80]
        resp = sm.start_execution(
            stateMachineArn=state_machine,
            name=name,
            input=json.dumps({"bucket": bucket, "key": key}),
        )
        started.append({"key": key, "executionArn": resp["executionArn"]})

    return {"started": started}
