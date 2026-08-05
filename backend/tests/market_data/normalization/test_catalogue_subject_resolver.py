from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.instruments.ports import InstrumentVersionState, ProviderMappingState
from app.instruments.temporal_records import AmbiguousPointInTimeResultError
from app.services.catalogue_market_subject_resolver import CatalogueMarketSubjectResolver
from tests.market_data.normalization.helpers import AT, subjects


class FakeInstrumentRepository:
    def __init__(self, resolved_subjects):
        self.subjects = {subject.provider_contract_key: subject for subject in resolved_subjects}
        self.stale: set[str] = set()
        self.ambiguous: set[str] = set()
        self.calls: list[tuple] = []

    async def resolve_provider_key_state(self, provider, key, market_as_of, known_as_of):
        self.calls.append(("mapping", provider, key, market_as_of, known_as_of))
        if key in self.ambiguous:
            raise AmbiguousPointInTimeResultError("ambiguous")
        subject = self.subjects.get(key)
        if subject is None or key in self.stale:
            return None
        return ProviderMappingState(subject.provider_mapping, "mapping-record", subject.economic_subject_id)

    async def resolve_provider_key_instrument_id(self, provider, key):
        self.calls.append(("binding", provider, key))
        subject = self.subjects.get(key)
        return subject.economic_subject_id if subject is not None else None

    async def resolve_version_state(self, instrument_id, market_as_of, known_as_of):
        self.calls.append(("version", instrument_id, market_as_of, known_as_of))
        subject = next(item for item in self.subjects.values() if item.economic_subject_id == instrument_id)
        return InstrumentVersionState(subject.contract_version, "version-record")

    async def get_identity(self, instrument_id):
        self.calls.append(("identity", instrument_id))
        return next(item.economic_identity for item in self.subjects.values() if item.economic_subject_id == instrument_id)


@dataclass
class FakeUnitOfWork:
    instruments: FakeInstrumentRepository
    entered: int = 0
    exited: int = 0
    committed: int = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exited += 1

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


def test_catalogue_resolver_resolves_all_kinds_sorted_with_exact_provenance() -> None:
    expected = subjects()
    repository = FakeInstrumentRepository(expected)
    unit_of_work = FakeUnitOfWork(repository)
    resolver = CatalogueMarketSubjectResolver(lambda: unit_of_work)
    keys = tuple(reversed(tuple(item.provider_contract_key for item in expected)))
    result = asyncio.run(resolver.resolve_many("upstox", keys, AT, AT))
    assert tuple(item.provider_contract_key for item in result.resolved) == tuple(sorted(keys))
    assert {item.instrument_kind.value for item in result.resolved} == {"underlying", "future", "option"}
    assert all(item.provider_mapping is next(x for x in expected if x.provider_contract_key == item.provider_contract_key).provider_mapping for item in result.resolved)
    assert all(item.resolution_market_as_of == AT and item.resolution_known_as_of == AT for item in result.resolved)
    assert unit_of_work.entered == unit_of_work.exited == 1
    assert unit_of_work.committed == 0


def test_catalogue_resolver_distinguishes_unknown_stale_and_ambiguous() -> None:
    expected = subjects()
    repository = FakeInstrumentRepository(expected)
    repository.stale.add(expected[0].provider_contract_key)
    repository.ambiguous.add(expected[1].provider_contract_key)
    unit_of_work = FakeUnitOfWork(repository)
    resolver = CatalogueMarketSubjectResolver(lambda: unit_of_work)
    keys = ("unknown", expected[0].provider_contract_key, expected[1].provider_contract_key)
    result = asyncio.run(resolver.resolve_many("upstox", keys, AT, AT))
    assert [(item.provider_contract_key, item.reason_code) for item in result.failures] == [
        (expected[1].provider_contract_key, "ambiguous_provider_mapping"),
        (expected[0].provider_contract_key, "stale_provider_mapping"),
        ("unknown", "unknown_provider_key"),
    ]
    assert result.resolved == ()


def test_catalogue_resolver_uses_sorted_unique_keys_in_one_batch() -> None:
    expected = subjects()
    repository = FakeInstrumentRepository(expected)
    unit_of_work = FakeUnitOfWork(repository)
    resolver = CatalogueMarketSubjectResolver(lambda: unit_of_work)
    key = expected[0].provider_contract_key
    result = asyncio.run(resolver.resolve_many("upstox", (key, key), AT, AT))
    assert result.provider_contract_keys == (key,)
    assert [call[2] for call in repository.calls if call[0] == "mapping"] == [key]
    assert unit_of_work.entered == unit_of_work.exited == 1


def test_catalogue_resolver_propagates_unexpected_repository_error() -> None:
    repository = FakeInstrumentRepository(subjects())

    async def broken(*args):
        raise RuntimeError("database unavailable")

    repository.resolve_provider_key_state = broken
    unit_of_work = FakeUnitOfWork(repository)
    resolver = CatalogueMarketSubjectResolver(lambda: unit_of_work)
    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(resolver.resolve_many("upstox", ("key",), AT, AT))
    assert unit_of_work.exited == 1
