"""AWS Lambda entrypoint for the adjuster API (API Gateway HTTP API → Mangum)."""

from __future__ import annotations

from mangum import Mangum

from claims_intake.api.app import app

handler = Mangum(app, lifespan="off")
