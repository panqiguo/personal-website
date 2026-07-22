from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .normalize import normalize_title_key

Decision = Literal["same", "distinct"]


def review_key(title_a: str, title_b: str) -> tuple[str, str]:
    keys = sorted((normalize_title_key(title_a), normalize_title_key(title_b)))
    if not keys[0] or not keys[1] or keys[0] == keys[1]:
        raise ValueError("doctor review requires two different non-empty titles")
    return keys[0], keys[1]


def read_reviews(path: str | Path) -> dict[tuple[str, str], dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid doctor review file '{path}': {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("reviews", []), list):
        raise ValueError(f"invalid doctor review file '{path}': expected reviews array")

    reviews: dict[tuple[str, str], dict[str, str]] = {}
    for index, item in enumerate(data.get("reviews", []), start=1):
        if not isinstance(item, dict):
            raise ValueError(f"invalid doctor review #{index}: expected object")
        normalized_titles = item.get("normalized_titles")
        decision = item.get("decision")
        if (
            not isinstance(normalized_titles, list)
            or len(normalized_titles) != 2
            or decision not in ("same", "distinct")
        ):
            raise ValueError(f"invalid doctor review #{index}: malformed titles or decision")
        key = tuple(sorted(str(title) for title in normalized_titles))
        reviews[key] = {
            "decision": str(decision),
            "reason": str(item.get("reason") or ""),
            "reviewed_at": str(item.get("reviewed_at") or ""),
            "title_a": str(item.get("title_a") or ""),
            "title_b": str(item.get("title_b") or ""),
        }
    return reviews


def write_review(
    path: str | Path,
    *,
    title_a: str,
    title_b: str,
    decision: Decision,
    reason: str,
) -> dict[str, str]:
    if decision not in ("same", "distinct"):
        raise ValueError("doctor review decision must be 'same' or 'distinct'")
    path = Path(path)
    reviews = read_reviews(path)
    key = review_key(title_a, title_b)
    review = {
        "decision": decision,
        "reason": reason.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "title_a": title_a.strip(),
        "title_b": title_b.strip(),
    }
    reviews[key] = review

    payload = {
        "version": 1,
        "reviews": [
            {
                "normalized_titles": list(review_key_value),
                **review_value,
            }
            for review_key_value, review_value in sorted(reviews.items())
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    )
    try:
        with tmp as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(tmp.name, path)
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise
    return review
