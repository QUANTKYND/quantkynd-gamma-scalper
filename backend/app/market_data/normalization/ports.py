from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.market_data.normalization.models import ResolvedMarketSubjectV1


@dataclass(frozen=True)
class SubjectResolutionFailureV1:
    provider_contract_key: str
    reason_code: str


@dataclass(frozen=True)
class SubjectResolutionBatch:
    resolved: tuple[ResolvedMarketSubjectV1, ...]
    failures: tuple[SubjectResolutionFailureV1, ...]

    def __post_init__(self) -> None:
        resolved_keys = tuple(subject.provider_contract_key for subject in self.resolved)
        failure_keys = tuple(failure.provider_contract_key for failure in self.failures)
        if resolved_keys != tuple(sorted(set(resolved_keys))):
            raise ValueError("resolved subjects must be unique and sorted")
        if failure_keys != tuple(sorted(set(failure_keys))):
            raise ValueError("subject failures must be unique and sorted")
        if set(resolved_keys) & set(failure_keys):
            raise ValueError("a subject cannot be both resolved and failed")

    def subject_for(self, provider_contract_key: str) -> ResolvedMarketSubjectV1 | None:
        return next(
            (subject for subject in self.resolved if subject.provider_contract_key == provider_contract_key),
            None,
        )

    def failure_for(self, provider_contract_key: str) -> SubjectResolutionFailureV1 | None:
        return next(
            (failure for failure in self.failures if failure.provider_contract_key == provider_contract_key),
            None,
        )


class MarketSubjectResolver(Protocol):
    async def resolve_many(
        self,
        provider: str,
        provider_contract_keys: tuple[str, ...],
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> SubjectResolutionBatch: ...


class StaticSubjectManifestResolver:
    def __init__(self, subjects: tuple[ResolvedMarketSubjectV1, ...]) -> None:
        self._subjects = {subject.provider_contract_key: subject for subject in subjects}
        if len(self._subjects) != len(subjects):
            raise ValueError("static subject keys must be unique")

    async def resolve_many(
        self,
        provider: str,
        provider_contract_keys: tuple[str, ...],
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> SubjectResolutionBatch:
        market_cutoff = _utc(market_as_of, "market_as_of")
        knowledge_cutoff = _utc(known_as_of, "known_as_of")
        keys = tuple(sorted(set(provider_contract_keys)))
        resolved: list[ResolvedMarketSubjectV1] = []
        failures: list[SubjectResolutionFailureV1] = []
        for key in keys:
            subject = self._subjects.get(key)
            if subject is None or subject.provider != provider:
                failures.append(SubjectResolutionFailureV1(key, "unknown_provider_key"))
                continue
            if subject.resolution_market_as_of != market_cutoff or subject.resolution_known_as_of != knowledge_cutoff:
                failures.append(SubjectResolutionFailureV1(key, "stale_provider_mapping"))
                continue
            resolved.append(subject)
        return SubjectResolutionBatch(tuple(resolved), tuple(failures))


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
