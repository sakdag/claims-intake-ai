from __future__ import annotations

import re
from typing import Any

from claims_intake.llm.client import LlmClient, complete_json

_FIELD_NAMES = [
    "claimId",
    "policyId",
    "dateOfLoss",
    "dateOfReported",
    "lossEvent",
    "claimant",
    "product",
]

_SYSTEM = """You extract structured claim fields from insurance documents for Elm & Stone.
Return ONLY a JSON object. No markdown. No commentary.

Exact schema:
{
  "fields": [
    {
      "name": "claimId",
      "value": "260000101",
      "quote": "verbatim snippet",
      "document_id": "123"
    }
  ]
}

Allowed name values (one field object per name, omit if unknown):
- claimId
- policyId
- dateOfLoss
- dateOfReported
- lossEvent
- claimant
- product

Rules:
- Emit separate objects in "fields" — never join names with | characters.
- Dates as YYYY-MM-DD.
- product must be PHI or PBI when stated or clearly implied by policy id (PZ-PHI-... / PZ-PBI-...).
- quote must be a short verbatim snippet (≤20 words) copied from a provided document.
- document_id must be one of the provided document_id values.
"""


def extract_fields(
    client: LlmClient,
    *,
    claim_id: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    packed = []
    for d in documents:
        packed.append(
            {
                "document_id": str(d.get("document_id") or d.get("extractedDocumentId")),
                "document_type": d.get("document_type") or d.get("documentType"),
                "content": (d.get("content") or d.get("extractedDocumentContent") or "")[:3500],
            }
        )
    user = (
        "Extract the fields now.\n"
        f"claim_id_hint: {claim_id}\n"
        "Example of good output shape:\n"
        '{"fields":[{"name":"claimId","value":"260000101","quote":"...","document_id":"1"}]}\n'
        f"Documents:\n{packed}"
    )
    data, resp = complete_json(client, system=_SYSTEM, user=user, max_tokens=2048)
    fields = _normalize_fields(data.get("fields") or [], documents=packed)
    return {
        "claim_id": claim_id,
        "fields": fields,
        "model_id": resp.model_id,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
    }


def _normalize_fields(raw_fields: list[Any], *, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        # Repair Nova-Micro style collapse: name="a|b|c", value="1|2|3"
        if "|" in name and isinstance(value, str) and "|" in value:
            names = [n.strip() for n in name.split("|")]
            values = [v.strip() for v in str(value).split("|")]
            quote = item.get("quote") or ""
            doc_id = str(item.get("document_id") or "")
            for n, v in zip(names, values, strict=False):
                if n in _FIELD_NAMES and v:
                    normalized.append(
                        {
                            "name": n,
                            "value": _clean_value(n, v),
                            "citations": [{"document_id": doc_id, "quote": quote}],
                        }
                    )
            continue
        if name not in _FIELD_NAMES:
            continue
        normalized.append(
            {
                "name": name,
                "value": _clean_value(name, value),
                "citations": [
                    {
                        "document_id": str(item.get("document_id") or ""),
                        "quote": item.get("quote") or "",
                    }
                ],
            }
        )

    # Infer / repair product from policyId when missing or not PHI/PBI
    by_name = {f["name"]: f for f in normalized}
    product_val = str((by_name.get("product") or {}).get("value") or "").upper()
    needs_product = "product" not in by_name or product_val not in {"PHI", "PBI"}
    if needs_product and "policyId" in by_name:
        pid = str(by_name["policyId"].get("value") or "")
        inferred = None
        if "PHI" in pid.upper():
            inferred = "PHI"
        elif "PBI" in pid.upper():
            inferred = "PBI"
        if inferred:
            if "product" in by_name:
                by_name["product"]["value"] = inferred
            else:
                normalized.append(
                    {
                        "name": "product",
                        "value": inferred,
                        "citations": by_name["policyId"].get("citations") or [],
                    }
                )
    return normalized


def _clean_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    if name in {"dateOfLoss", "dateOfReported"}:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
    if name == "product":
        up = s.upper()
        if "PHI" in up:
            return "PHI"
        if "PBI" in up:
            return "PBI"
    return s
