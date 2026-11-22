from __future__ import annotations

from collections import Counter
from typing import Any


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    correct = sum(a == b for a, b in zip(y_true, y_pred, strict=True))
    return correct / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0
    scores = []
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred, strict=True))
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        scores.append(f1)
    return sum(scores) / len(scores)


def field_exact_match(gold: dict[str, Any], pred_fields: list[dict[str, Any]]) -> dict[str, Any]:
    pred_map = {str(f.get("name")): _norm(f.get("value")) for f in pred_fields}
    keys = [
        "claimId",
        "policyId",
        "dateOfLoss",
        "dateOfReported",
        "lossEvent",
        "product",
    ]
    per_field = {}
    hits = 0
    for key in keys:
        g = _norm(gold.get(key))
        p = pred_map.get(key)
        ok = g is not None and p is not None and g == p
        per_field[key] = ok
        hits += int(ok)
    citation_rate = 0.0
    if pred_fields:
        with_cite = sum(1 for f in pred_fields if (f.get("citations") or [{}])[0].get("quote"))
        citation_rate = with_cite / len(pred_fields)
    return {
        "field_accuracy": hits / len(keys),
        "per_field": per_field,
        "citation_rate": citation_rate,
    }


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    return s.lower()


def confusion_pairs(y_true: list[str], y_pred: list[str], limit: int = 10) -> list[tuple[str, str, int]]:
    c: Counter[tuple[str, str]] = Counter()
    for t, p in zip(y_true, y_pred, strict=True):
        if t != p:
            c[(t, p)] += 1
    return [(a, b, n) for (a, b), n in c.most_common(limit)]
