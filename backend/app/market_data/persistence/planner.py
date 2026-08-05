from __future__ import annotations
import hashlib
from dataclasses import dataclass
from app.market_data.persistence.contracts import DATA14_ADVISORY_LOCK_NAMESPACE, DATA14_LOCK_STRIPE_COUNT

def lock_stripe(entity_namespace: str, canonical_id: str) -> int:
    payload = f"data14-lock-stripe-v1\0{entity_namespace}\0{canonical_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest(), "big", signed=False) % DATA14_LOCK_STRIPE_COUNT

def derive_lock_stripes(roots):
    return tuple(sorted({lock_stripe(namespace, ident) for namespace, ident in roots}))

@dataclass(frozen=True)
class ParameterChunk:
    offset: int
    size: int

def plan_parameter_chunks(item_count: int, parameters_per_item: int, budget: int = 60000) -> tuple[ParameterChunk, ...]:
    if not isinstance(item_count,int) or item_count < 0 or not isinstance(parameters_per_item,int) or parameters_per_item <= 0 or budget <= 0: raise ValueError("invalid chunk planner arguments")
    size = max(1, budget // parameters_per_item)
    return tuple(ParameterChunk(offset, min(size, item_count-offset)) for offset in range(0, item_count, size))

def parameter_chunks(item_count: int, parameters_per_item: int, budget: int = 60000):
    return plan_parameter_chunks(item_count, parameters_per_item, budget)

