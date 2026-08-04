from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.instruments.ports import (
    AmbiguousPointInTimeResultError,
    SemanticCollisionError,
    UnitOfWorkStateError,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.migrations import downgrade_to_base, upgrade_to_head
from app.persistence.postgres.models import CatalogueVersionRow, MarketInstrumentRow
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.instruments.identity import ProviderContractMapping


@pytest.fixture
def migrated_postgres_url(postgres_url: str) -> str:
    downgrade_to_base(postgres_url)
    upgrade_to_head(postgres_url)
    return postgres_url


@pytest.mark.anyio
async def test_fixture_persists_and_exact_reinsert_is_idempotent(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            assert await unit_of_work.catalogues.get(fixture.catalogue.catalogue_version_id) == fixture.catalogue
            assert await unit_of_work.instruments.get_identity(fixture.underlying.instrument_id) == fixture.underlying
            assert await unit_of_work.instruments.get_identity(fixture.future.contract_id) == fixture.future
            assert await unit_of_work.instruments.get_identity(fixture.option.contract_id) == fixture.option
            assert await unit_of_work.instruments.get_version(fixture.option_version.version_id) == fixture.option_version
            resolved = await unit_of_work.instruments.resolve_provider_key(
                fixture.provider_mapping.provider,
                fixture.provider_mapping.provider_contract_key,
                fixture.provider_mapping.effective_from,
                fixture.provider_mapping.recorded_at,
            )
            session = await unit_of_work.trading_sessions.resolve(
                fixture.session.exchange,
                fixture.session.session_date,
                fixture.session.session_kind.value,
                fixture.session_version.recorded_at,
            )
            assert resolved == fixture.provider_mapping
            assert session == fixture.session_version
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_semantic_collision_fails_and_rolls_back_all_writes(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    collision = replace(
        fixture.catalogue,
        recorded_at=fixture.catalogue.recorded_at + timedelta(seconds=1),
    )
    try:
        with pytest.raises(SemanticCollisionError):
            async with PostgresUnitOfWork(factory) as unit_of_work:
                await unit_of_work.catalogues.add(fixture.catalogue)
                await unit_of_work.catalogues.add(collision)
                await unit_of_work.commit()
        async with factory() as session:
            assert await session.scalar(select(CatalogueVersionRow.catalogue_version_id)) is None
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_exception_and_explicit_rollback_remove_uncommitted_writes(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        with pytest.raises(RuntimeError, match="abort"):
            async with PostgresUnitOfWork(factory) as unit_of_work:
                await unit_of_work.catalogues.add(fixture.catalogue)
                raise RuntimeError("abort")
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.rollback()
        async with factory() as session:
            assert await session.scalar(select(CatalogueVersionRow.catalogue_version_id)) is None
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_repositories_share_one_transaction_and_uow_cannot_be_reused(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    unit_of_work = PostgresUnitOfWork(factory)
    try:
        async with unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.instruments.add_underlying(fixture.underlying)
            await unit_of_work.commit()
        async with factory() as session:
            assert await session.get(CatalogueVersionRow, fixture.catalogue.catalogue_version_id)
            assert await session.get(MarketInstrumentRow, fixture.underlying.instrument_id)
        with pytest.raises(UnitOfWorkStateError):
            async with unit_of_work:
                pass
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_point_in_time_mapping_cutoffs_and_ambiguity_fail_closed(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    recorded = fixture.provider_mapping.recorded_at
    effective = fixture.provider_mapping.effective_from
    first = replace(fixture.provider_mapping, superseded_at=recorded + timedelta(hours=2))
    competing = ProviderContractMapping(
        provider=first.provider,
        provider_contract_key=first.provider_contract_key,
        contract_version_id=first.contract_version_id,
        provider_payload_hash="sha256:" + "c" * 64,
        source_row_identity="source-row-competing",
        effective_from=first.effective_from,
        effective_until=first.effective_until,
        recorded_at=recorded + timedelta(hours=1),
        superseded_at=recorded + timedelta(hours=2),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.instruments.add_underlying(fixture.underlying)
            await unit_of_work.instruments.add_option(fixture.option)
            await unit_of_work.instruments.add_version(fixture.option_version)
            await unit_of_work.instruments.add_provider_mapping(first)
            await unit_of_work.instruments.add_provider_mapping(competing)
            await unit_of_work.commit()
        async with PostgresUnitOfWork(factory) as unit_of_work:
            assert await unit_of_work.instruments.resolve_provider_key(
                first.provider,
                first.provider_contract_key,
                effective - timedelta(microseconds=1),
                recorded + timedelta(minutes=30),
            ) is None
            assert await unit_of_work.instruments.resolve_provider_key(
                first.provider,
                first.provider_contract_key,
                effective,
                recorded - timedelta(microseconds=1),
            ) is None
            assert await unit_of_work.instruments.resolve_provider_key(
                first.provider,
                first.provider_contract_key,
                effective,
                recorded + timedelta(minutes=30),
            ) == first
            with pytest.raises(AmbiguousPointInTimeResultError):
                await unit_of_work.instruments.resolve_provider_key(
                    first.provider,
                    first.provider_contract_key,
                    effective,
                    recorded + timedelta(hours=1, minutes=30),
                )
            assert await unit_of_work.instruments.resolve_provider_key(
                first.provider,
                first.provider_contract_key,
                effective,
                recorded + timedelta(hours=2),
            ) is None
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_referenced_identity_delete_is_rejected(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        async with factory() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    delete(MarketInstrumentRow).where(
                        MarketInstrumentRow.instrument_id == fixture.underlying.instrument_id
                    )
                )
                await session.commit()
            await session.rollback()
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_repository_ordering_is_independent_of_insertion_order(
    migrated_postgres_url: str,
) -> None:
    engine = create_database_engine_from_url(migrated_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    later = replace(
        fixture.catalogue,
        source_content_hash="sha256:" + "d" * 64,
        effective_from=fixture.catalogue.effective_from + timedelta(days=1),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(later)
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.commit()
        async with PostgresUnitOfWork(factory) as unit_of_work:
            assert await unit_of_work.catalogues.list_for_provider(fixture.catalogue.provider) == (
                fixture.catalogue,
                later,
            )
    finally:
        await dispose_database_engine(engine)


def create_database_engine_from_url(database_url: str):
    from app.core.database_config import DatabaseSettings

    return create_database_engine(DatabaseSettings(database_url=database_url, _env_file=None))
