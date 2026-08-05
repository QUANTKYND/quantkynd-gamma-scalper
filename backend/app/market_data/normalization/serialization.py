from __future__ import annotations

from app.core.hashing import canonical_json
from app.market_data.normalization.result_hashing import adopted_semantics_hash, full_result_hash, normalization_payload


def canonical_normalization_json(value: object) -> str:
    return canonical_json(normalization_payload(value))
