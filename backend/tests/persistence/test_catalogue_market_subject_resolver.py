from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.database_config import DatabaseSettings
from app.instruments.identity import ProviderContractMapping
from app.persistence.postgres.engine import create_database_engine, create_session_factory, dispose_database_engine
from app.persistence.postgres.fixtures import deterministic_fixture
from app.persistence.postgres.models import ProviderContractMappingRow
from app.persistence.postgres.market_subject_resolver import postgres_catalogue_market_subject_resolver
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


def _mapping(key, version, effective_from, recorded_at, marker, *, effective_until=None):
    return ProviderContractMapping(
        provider="upstox",
        provider_contract_key=key,
        contract_version_id=version.version_id,
        provider_payload_hash="sha256:" + marker * 64,
        source_row_identity=f"row-{marker}",
        effective_from=effective_from,
        effective_until=effective_until,
        recorded_at=recorded_at,
    )


@pytest.mark.anyio
async def test_catalogue_market_subject_resolver_on_postgres_17(reset_postgres_url: str) -> None:
    engine = create_database_engine(DatabaseSettings(database_url=reset_postgres_url, _env_file=None))
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    effective = fixture.catalogue.effective_from
    recorded = fixture.catalogue.recorded_at
    keys = {
        "underlying": "NSE_INDEX|resolver-underlying",
        "future": "NSE_FO|resolver-future",
        "option": "NSE_FO|resolver-option",
        "expired": "NSE_FO|resolver-expired",
        "version_stale": "NSE_FO|resolver-version-stale",
        "superseded": "NSE_FO|resolver-superseded",
        "ambiguous": "NSE_FO|resolver-ambiguous",
    }
    base_mappings = (
        _mapping(keys["underlying"], fixture.underlying_version, effective, recorded, "1"),
        _mapping(keys["future"], fixture.future_version, effective, recorded, "2"),
        _mapping(keys["option"], fixture.option_version, effective, recorded, "3"),
        _mapping(keys["expired"], fixture.option_version, effective, recorded, "4", effective_until=effective + timedelta(minutes=30)),
        _mapping(keys["version_stale"], fixture.option_version, recorded, recorded, "5"),
        _mapping(keys["superseded"], fixture.option_version, effective, recorded, "6"),
        _mapping(keys["ambiguous"], fixture.option_version, effective, recorded, "7"),
        _mapping(keys["ambiguous"], fixture.option_version, effective, recorded + timedelta(minutes=1), "8"),
    )
    successor = replace(
        base_mappings[5],
        provider_payload_hash="sha256:" + "9" * 64,
        source_row_identity="row-9",
        recorded_at=recorded + timedelta(hours=2),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.instruments.add_underlying(fixture.underlying)
            await unit_of_work.instruments.add_future(fixture.future)
            await unit_of_work.instruments.add_option(fixture.option)
            await unit_of_work.instruments.add_version(fixture.underlying_version)
            await unit_of_work.instruments.add_version(fixture.future_version)
            await unit_of_work.instruments.add_version(fixture.option_version)
            predecessor = None
            for mapping in base_mappings:
                record_id = await unit_of_work.instruments.add_provider_mapping(mapping)
                if mapping.provider_contract_key == keys["superseded"]:
                    predecessor = record_id
            assert predecessor is not None
            await unit_of_work.instruments.add_provider_mapping(successor, predecessor)
            await unit_of_work.commit()

        async with factory() as session:
            before = await session.scalar(select(func.count()).select_from(ProviderContractMappingRow))

        resolver = postgres_catalogue_market_subject_resolver(factory)
        market_cutoff = effective + timedelta(hours=1)
        knowledge_cutoff = recorded + timedelta(hours=1)
        resolved = await resolver.resolve_many(
            "upstox",
            (keys["option"], keys["underlying"], keys["future"], keys["option"]),
            market_cutoff,
            knowledge_cutoff,
        )
        assert tuple(item.provider_contract_key for item in resolved.resolved) == tuple(
            sorted((keys["underlying"], keys["future"], keys["option"]))
        )
        assert {item.instrument_kind.value for item in resolved.resolved} == {"underlying", "future", "option"}
        assert all(item.resolution_market_as_of == market_cutoff for item in resolved.resolved)
        assert all(item.resolution_known_as_of == knowledge_cutoff for item in resolved.resolved)
        assert all(item.provider_mapping.mapping_id == item.provider_mapping_id for item in resolved.resolved)
        cases = (
            (keys["future"], effective - timedelta(seconds=1), knowledge_cutoff, "stale_provider_mapping"),
            (keys["expired"], market_cutoff, knowledge_cutoff, "stale_provider_mapping"),
            (keys["option"], market_cutoff, recorded - timedelta(seconds=1), "stale_provider_mapping"),
            (keys["version_stale"], recorded + timedelta(minutes=1), knowledge_cutoff, "stale_provider_mapping"),
            (keys["ambiguous"], market_cutoff, knowledge_cutoff, "ambiguous_provider_mapping"),
            ("NSE_FO|resolver-unknown", market_cutoff, knowledge_cutoff, "unknown_provider_key"),
        )
        for key, market_as_of, known_as_of, reason in cases:
            result = await resolver.resolve_many("upstox", (key,), market_as_of, known_as_of)
            assert result.failures[0].reason_code == reason

        mixed = await resolver.resolve_many(
            "upstox",
            (keys["option"], "NSE_FO|resolver-unknown"),
            market_cutoff,
            knowledge_cutoff,
        )
        assert tuple(item.provider_contract_key for item in mixed.resolved) == (keys["option"],)
        assert mixed.failures[0].reason_code == "unknown_provider_key"

        historical = await resolver.resolve_many(
            "upstox",
            (keys["superseded"],),
            market_cutoff,
            recorded + timedelta(hours=1),
        )
        current = await resolver.resolve_many(
            "upstox",
            (keys["superseded"],),
            market_cutoff,
            recorded + timedelta(hours=3),
        )
        replay = await resolver.resolve_many(
            "upstox",
            (keys["superseded"],),
            market_cutoff,
            recorded + timedelta(hours=1),
        )
        assert historical.resolved[0].provider_mapping_id == base_mappings[5].mapping_id
        assert current.resolved[0].provider_mapping_id == successor.mapping_id
        assert replay == historical

        async with factory() as session:
            after = await session.scalar(select(func.count()).select_from(ProviderContractMappingRow))
        assert after == before
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_catalogue_resolver_returns_valid_and_ambiguous_version_outcomes(reset_postgres_url: str) -> None:
    engine = create_database_engine(DatabaseSettings(database_url=reset_postgres_url, _env_file=None))
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    alternate = replace(
        fixture.future_version,
        display_symbol="NIFTY26AUGFUT-ALT",
        recorded_at=fixture.future_version.recorded_at + timedelta(minutes=1),
    )
    underlying_mapping = _mapping(
        "NSE_INDEX|mixed-valid",
        fixture.underlying_version,
        fixture.catalogue.effective_from,
        fixture.catalogue.recorded_at,
        "a",
    )
    future_mapping = _mapping(
        "NSE_FO|mixed-ambiguous-version",
        fixture.future_version,
        fixture.catalogue.effective_from,
        fixture.catalogue.recorded_at,
        "b",
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.instruments.add_underlying(fixture.underlying)
            await unit_of_work.instruments.add_future(fixture.future)
            await unit_of_work.instruments.add_version(fixture.underlying_version)
            await unit_of_work.instruments.add_version(fixture.future_version)
            await unit_of_work.instruments.add_version(alternate)
            await unit_of_work.instruments.add_provider_mapping(underlying_mapping)
            await unit_of_work.instruments.add_provider_mapping(future_mapping)
            await unit_of_work.commit()
        resolver = postgres_catalogue_market_subject_resolver(factory)
        result = await resolver.resolve_many(
            "upstox",
            (future_mapping.provider_contract_key, underlying_mapping.provider_contract_key),
            fixture.catalogue.effective_from + timedelta(hours=1),
            fixture.catalogue.recorded_at + timedelta(hours=1),
        )
        assert tuple(item.provider_contract_key for item in result.resolved) == (
            underlying_mapping.provider_contract_key,
        )
        assert result.failures[0].provider_contract_key == future_mapping.provider_contract_key
        assert result.failures[0].reason_code == "ambiguous_contract_version"
    finally:
        await dispose_database_engine(engine)
