from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.instruments.identity import (
    FuturesContractIdentity,
    FuturesContractVersion,
    OptionContractIdentity,
    OptionContractVersion,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.instruments.ports import PersistenceIntegrityError, UnitOfWork
from app.instruments.temporal_records import AmbiguousPointInTimeResultError
from app.market_data.normalization.enums import MarketSubjectKind
from app.market_data.normalization.models import ResolvedMarketSubjectV1
from app.market_data.normalization.ports import SubjectResolutionBatch, SubjectResolutionFailureV1


class CatalogueMarketSubjectResolver:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def resolve_many(
        self,
        provider: str,
        provider_contract_keys: tuple[str, ...],
        market_as_of: datetime,
        known_as_of: datetime,
    ) -> SubjectResolutionBatch:
        market_cutoff = _utc(market_as_of, "market_as_of")
        knowledge_cutoff = _utc(known_as_of, "known_as_of")
        resolved: list[ResolvedMarketSubjectV1] = []
        failures: list[SubjectResolutionFailureV1] = []
        async with self._unit_of_work_factory() as unit_of_work:
            for key in sorted(set(provider_contract_keys)):
                try:
                    mapping_state = await unit_of_work.instruments.resolve_provider_key_mapping_state(
                        provider,
                        key,
                        market_cutoff,
                        knowledge_cutoff,
                    )
                except AmbiguousPointInTimeResultError:
                    failures.append(SubjectResolutionFailureV1(key, "ambiguous_provider_mapping"))
                    continue
                if mapping_state is None:
                    instrument_id = await unit_of_work.instruments.resolve_provider_key_instrument_id(
                        provider,
                        key,
                    )
                    reason = "unknown_provider_key" if instrument_id is None else "stale_provider_mapping"
                    failures.append(SubjectResolutionFailureV1(key, reason))
                    continue
                try:
                    version_state = await unit_of_work.instruments.resolve_version_state(
                        mapping_state.instrument_id,
                        market_cutoff,
                        knowledge_cutoff,
                    )
                except AmbiguousPointInTimeResultError:
                    failures.append(SubjectResolutionFailureV1(key, "ambiguous_contract_version"))
                    continue
                if version_state is None:
                    failures.append(SubjectResolutionFailureV1(key, "stale_provider_mapping"))
                    continue
                if version_state.value.version_id != mapping_state.value.contract_version_id:
                    raise PersistenceIntegrityError("provider mapping resolved to a different instrument version")
                identity = await unit_of_work.instruments.get_identity(mapping_state.instrument_id)
                if identity is None:
                    raise PersistenceIntegrityError("provider mapping references a missing economic identity")
                kind = _subject_kind(identity, version_state.value)
                resolved.append(
                    ResolvedMarketSubjectV1(
                        provider=provider,
                        provider_contract_key=key,
                        provider_mapping_id=mapping_state.value.mapping_id,
                        provider_mapping=mapping_state.value,
                        contract_version_id=version_state.value.version_id,
                        economic_subject_id=mapping_state.instrument_id,
                        instrument_kind=kind,
                        economic_identity=identity,
                        contract_version=version_state.value,
                        resolution_market_as_of=market_cutoff,
                        resolution_known_as_of=knowledge_cutoff,
                    )
                )
        return SubjectResolutionBatch(tuple(resolved), tuple(failures))


def _subject_kind(identity, version) -> MarketSubjectKind:
    pairs = (
        (UnderlyingInstrumentIdentity, UnderlyingInstrumentVersion, MarketSubjectKind.UNDERLYING),
        (FuturesContractIdentity, FuturesContractVersion, MarketSubjectKind.FUTURE),
        (OptionContractIdentity, OptionContractVersion, MarketSubjectKind.OPTION),
    )
    for identity_type, version_type, kind in pairs:
        if isinstance(identity, identity_type) and isinstance(version, version_type):
            return kind
    raise PersistenceIntegrityError("economic identity and version kinds do not match")


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
