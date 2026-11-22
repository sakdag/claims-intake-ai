from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def to_python(obj: Any) -> Any:
    """Convert parquet/numpy/pandas values into JSON-friendly Python types."""
    if isinstance(obj, dict):
        return {str(k): to_python(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_python(x) for x in obj]
    if isinstance(obj, np.ndarray):
        return [to_python(x) for x in obj.tolist()]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    if obj is None:
        return None
    try:
        if pd.isna(obj):
            return None
    except (ValueError, TypeError):
        pass
    return obj


def load_polycontexts(raw_dir: Path) -> list[dict[str, Any]]:
    df = pd.read_parquet(raw_dir / "data.parquet")
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "id": int(row["id"]),
                "note": str(row["note"]),
                "data": to_python(row["data"]),
            }
        )
    return rows


def load_rules(raw_dir: Path) -> list[dict[str, Any]]:
    df = pd.read_parquet(raw_dir / "rules-dataset.parquet")
    return [to_python(r) for r in df.to_dict(orient="records")]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
