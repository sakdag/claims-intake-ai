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


_SCALAR_KEYS = [
    "claimId",
    "policyId",
    "dateOfLoss",
    "dateOfReported",
    "lossEvent",
    "claimant",
    "product",
]


def field_exact_match(gold: dict[str, Any], pred_fields: list[dict[str, Any]]) -> dict[str, Any]:
    pred_map = {str(f.get("name")): f.get("value") for f in pred_fields}
    per_field: dict[str, bool] = {}
    hits = 0
    for key in _SCALAR_KEYS:
        g = _norm(gold.get(key))
        p = _norm(pred_map.get(key))
        ok = g is not None and p is not None and g == p
        per_field[key] = ok
        hits += int(ok)

    # Subjects from extract are free-form inventory names; score the risk set only.
    gold_risks = {risk for _, risk in _norm_damaged(gold.get("damagedItems") or [])}
    pred_risks = {risk for _, risk in _norm_damaged(pred_map.get("damagedItems") or [])}
    damaged_ok = gold_risks == pred_risks
    per_field["damagedItems"] = damaged_ok
    hits += int(damaged_ok)
    n_keys = len(_SCALAR_KEYS) + 1

    citation_rate = 0.0
    if pred_fields:
        with_cite = sum(1 for f in pred_fields if (f.get("citations") or [{}])[0].get("quote"))
        citation_rate = with_cite / len(pred_fields)
    return {
        "field_accuracy": hits / n_keys,
        "per_field": per_field,
        "citation_rate": citation_rate,
    }


def policy_check_status_accuracy(
    gold_checks: dict[str, Any],
    pred_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare predicted gate statuses to gold labels (coverage / status / peril)."""
    pred_by_id = {str(c.get("rule_id")): str(c.get("status") or "") for c in pred_checks}
    mapping = {
        "coverage_period": "det.coverage_period",
        "policy_status": "det.policy_status",
        "peril_covered": "det.peril_covered",
    }
    per_check: dict[str, bool] = {}
    hits = 0
    for name, rule_id in mapping.items():
        gold_status = str((gold_checks.get(name) or {}).get("status") or "")
        pred_status = pred_by_id.get(rule_id, "")
        ok = bool(gold_status) and gold_status == pred_status
        per_check[name] = ok
        hits += int(ok)
    return {
        "accuracy": hits / len(mapping) if mapping else 0.0,
        "per_check": per_check,
        "n": len(mapping),
    }


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    return s.lower()


def _norm_damaged(items: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("insuredSubject") or item.get("subject") or "").strip().lower()
        risk = str(item.get("risk") or "").strip().lower()
        if subject and risk:
            out.add((subject, risk))
    return out


def confusion_pairs(y_true: list[str], y_pred: list[str], limit: int = 10) -> list[tuple[str, str, int]]:
    c: Counter[tuple[str, str]] = Counter()
    for t, p in zip(y_true, y_pred, strict=True):
        if t != p:
            c[(t, p)] += 1
    return [(a, b, n) for (a, b), n in c.most_common(limit)]
