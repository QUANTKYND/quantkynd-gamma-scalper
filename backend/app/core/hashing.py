from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Mapping

from pydantic import BaseModel


def stable_hash(payload: object) -> str:
    encoded = canonical_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def canonical_json(payload: object) -> str:
    return json.dumps(_normalize(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical mappings require string keys")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=_canonical_sort_key)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical numeric values must be finite")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical numeric values must be finite")
        if value == 0:
            return "0"
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, int):
        return format(Decimal(value).normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
