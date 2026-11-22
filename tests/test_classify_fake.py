import json

from claims_intake.llm.client import FakeLlmClient
from claims_intake.pipeline.classify import classify_document


def test_classify_with_fake_llm() -> None:
    client = FakeLlmClient(
        responses={
            "document_id": json.dumps(
                {
                    "document_type": "invoice",
                    "confidence": 0.9,
                    "rationale": "contains line items and totals",
                }
            )
        }
    )
    out = classify_document(
        client,
        document_id="9",
        content="Invoice for repair works totaling EUR 1000",
        channel="email",
    )
    assert out["document_type"] == "invoice"
    assert out["confidence"] == 0.9
