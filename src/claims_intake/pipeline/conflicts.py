from __future__ import annotations

import re
from typing import Any

from claims_intake.models import ConflictFlag

# Matches €1,234.56 / 1234.56 EUR / EUR 1234.56
_AMOUNT_RE = re.compile(
    r"(?:€\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?|[0-9]+(?:[.,][0-9]{2})?))"
    r"|(?:([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?|[0-9]+(?:[.,][0-9]{2})?)\s*EUR)"
    r"|(?:EUR\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?|[0-9]+(?:[.,][0-9]{2})?))",
    re.IGNORECASE,
)

_MONEY_DOC_TYPES = {
    "invoice",
    "deposit_invoice",
    "damage_calculation",
    "online_form_submission",
    "first_notice_of_loss",
    "site_inspection",
}


def parse_eur_amount(raw: str) -> float | None:
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    # European thousands: 19.931,95 or US: 19,931.95
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # 19931,95 or 16,400
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def extract_amounts(text: str) -> list[float]:
    values: list[float] = []
    for match in _AMOUNT_RE.finditer(text or ""):
        raw = next(g for g in match.groups() if g)
        val = parse_eur_amount(raw)
        if val is not None and val > 0:
            values.append(val)
    return values


def detect_amount_conflicts(
    documents: list[dict[str, Any]],
    *,
    relative_threshold: float = 0.05,
    absolute_threshold: float = 50.0,
) -> list[ConflictFlag]:
    """
    Pseudo-label friendly detector: compare max amount per money-like document.
    Flag pairwise disagreements above relative OR absolute threshold.
    """
    per_doc: dict[str, float] = {}
    meta: dict[str, str] = {}
    for d in documents:
        doc_id = str(d.get("document_id") or d.get("extractedDocumentId"))
        doc_type = str(d.get("document_type") or d.get("documentType") or "")
        if doc_type and doc_type not in _MONEY_DOC_TYPES:
            continue
        content = d.get("content") or d.get("extractedDocumentContent") or ""
        amounts = extract_amounts(content)
        if not amounts:
            continue
        # Prefer the largest amount as a proxy for document total
        per_doc[doc_id] = max(amounts)
        meta[doc_id] = doc_type

    ids = sorted(per_doc.keys())
    conflicts: list[ConflictFlag] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            va, vb = per_doc[a], per_doc[b]
            diff = abs(va - vb)
            denom = max(va, vb, 1e-9)
            rel = diff / denom
            if diff >= absolute_threshold and rel >= relative_threshold:
                conflicts.append(
                    ConflictFlag(
                        kind="amount_mismatch",
                        summary=(
                            f"Amount conflict between {meta.get(a, a)} ({va:.2f}) "
                            f"and {meta.get(b, b)} ({vb:.2f})"
                        ),
                        document_ids=[a, b],
                        values={a: va, b: vb, "abs_diff": diff, "rel_diff": rel},
                    )
                )
    return conflicts


def amount_conflict_gold(
    documents: list[dict[str, Any]],
    *,
    relative_threshold: float = 0.05,
    absolute_threshold: float = 50.0,
) -> dict[str, Any]:
    """Same definition used as pseudo-labels for precision/recall."""
    flags = detect_amount_conflicts(
        documents,
        relative_threshold=relative_threshold,
        absolute_threshold=absolute_threshold,
    )
    pairs = {tuple(sorted(f.document_ids)) for f in flags}
    return {
        "has_conflict": bool(pairs),
        "pairs": [list(p) for p in sorted(pairs)],
        "flags": [f.model_dump() for f in flags],
    }
