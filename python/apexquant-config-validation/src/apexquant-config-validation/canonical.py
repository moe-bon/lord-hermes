from __future__ import annotations

import hashlib
import json
from typing import Any


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value.keys())}

    if isinstance(value, list):
        return [canonicalize(item) for item in value]

    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        sort_keys=False,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def hash_config(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()