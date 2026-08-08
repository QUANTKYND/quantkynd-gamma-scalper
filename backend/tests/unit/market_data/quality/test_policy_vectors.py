from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.hashing import canonical_json, stable_hash
from app.market_data.quality.contracts import (
    QualityPolicyIdentity,
    QualityPolicyVersionIdentity,
)


def test_policy_identity_vector() -> None:
    identity = QualityPolicyIdentity()
    assert canonical_json(
        {
            "entity": "market_data_quality_policy",
            "policy_name": identity.policy_name,
            "provider": identity.provider,
            "observation_domain": identity.observation_domain,
        }
    ) == (
        '{"entity":"market_data_quality_policy",'
        '"observation_domain":"normalized_market_observation",'
        '"policy_name":"upstox_nse_nifty_index_derivatives_quality",'
        '"provider":"upstox"}'
    )
    assert identity.policy_id == (
        "sha256:eb8daac12517a8e65f25e2a0aee14cda8eeb4a3b2308a80719f747bdcb333d01"
    )


def test_policy_version_zero_policy_vector() -> None:
    identity = QualityPolicyVersionIdentity("sha256:" + "0" * 64, 1)
    assert identity.policy_version_id == (
        "sha256:85eafa1a1b1517e373c0784d2842d11b065cd8c0ae3502d1aeb1398e4bea929d"
    )


def test_mixed_canonical_vector() -> None:
    payload = {
        "at": datetime(2026, 8, 7, 12, 34, 56, 123456, tzinfo=UTC),
        "entity": "canonical_hash_test",
        "price": Decimal("100.05"),
        "text": "ASCII",
        "values": [None, True, Decimal("0"), Decimal("-3")],
    }
    assert stable_hash(payload) == (
        "sha256:dcadb9cc36527b1507f5edb90916e72ea9cf774d65fa29b07d76829b52e2b0f8"
    )
