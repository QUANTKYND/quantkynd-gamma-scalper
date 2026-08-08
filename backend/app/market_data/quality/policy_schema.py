from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import (
    QualityPolicyIdentity,
    QualityPolicyVersionIdentity,
    SourceArtifactIdentity,
)
from app.market_data.quality.reason_registry import ReasonDefinition


@dataclass(frozen=True)
class ParsedQualityPolicy:
    """Strictly parsed immutable policy semantics plus exact source evidence."""

    policy_identity: QualityPolicyIdentity
    policy_version_identity: QualityPolicyVersionIdentity
    semantic_projection: Mapping[str, object]
    reason_definitions: tuple[ReasonDefinition, ...]
    source_bytes: bytes
    source_sha256: str
    source_artifact_identity: SourceArtifactIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.policy_identity, QualityPolicyIdentity):
            raise TypeError("policy_identity must be QualityPolicyIdentity")
        if not isinstance(self.policy_version_identity, QualityPolicyVersionIdentity):
            raise TypeError(
                "policy_version_identity must be QualityPolicyVersionIdentity"
            )
        if self.policy_version_identity.policy_id != self.policy_identity.policy_id:
            raise ValueError("policy version must belong to policy identity")
        if not isinstance(self.semantic_projection, Mapping):
            raise TypeError("semantic_projection must be a mapping")
        object.__setattr__(
            self,
            "semantic_projection",
            _freeze_mapping(self.semantic_projection),
        )
        if not isinstance(self.source_bytes, bytes) or not self.source_bytes:
            raise ValueError("source_bytes must be non-empty bytes")
        if (
            self.source_artifact_identity.policy_version_id
            != self.policy_version_identity.policy_version_id
        ):
            raise ValueError("source artifact must belong to policy version")
        if self.source_artifact_identity.source_sha256 != self.source_sha256:
            raise ValueError("source artifact hash mismatch")
        if self.source_artifact_identity.source_byte_count != len(self.source_bytes):
            raise ValueError("source artifact byte count mismatch")
        if len(self.reason_definitions) != 69:
            raise ValueError("policy must contain exactly 69 reason definitions")

    @property
    def policy_id(self) -> str:
        return self.policy_identity.policy_id

    @property
    def policy_version_id(self) -> str:
        return self.policy_version_identity.policy_version_id

    @property
    def source_artifact_id(self) -> str:
        return self.source_artifact_identity.source_artifact_id

    @property
    def policy_definition_hash(self) -> str:
        return stable_hash(self.semantic_projection)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: _freeze(item)
            for key, item in value.items()
        }
    )


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    if isinstance(value, (str, int, bool, Decimal)) or value is None:
        return value
    raise TypeError(f"unsupported policy semantic value: {type(value).__name__}")


def thaw_policy_projection(value: object) -> Any:
    """Return plain deterministic containers for persistence/tests."""

    if isinstance(value, Mapping):
        return {
            key: thaw_policy_projection(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [thaw_policy_projection(item) for item in value]
    return value
