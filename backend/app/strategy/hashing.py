from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from app.strategy.models import StrategyContractV1


def canonical_payload(config: StrategyContractV1) -> dict[str, Any]:
    return config.model_dump(mode="json", exclude={"created_at"})


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        _normalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def strategy_config_hash(config: StrategyContractV1) -> str:
    encoded = canonical_json(canonical_payload(config)).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    return value
