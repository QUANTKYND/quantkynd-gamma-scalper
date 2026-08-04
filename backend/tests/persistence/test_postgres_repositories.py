import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.database_config import DatabaseSettings
from app.instruments.catalogue import CatalogueVersion
from app.instruments.ports import SemanticCollisionError, UnitOfWorkStateError
from app.instruments.temporal_records import TemporalSupersessionConflictError
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.models import (
    CatalogueVersionRecordRow,
    CatalogueVersionRow,
    MarketInstrumentRow,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


def engine_for(database_url: str):
    return create_database_engine(DatabaseSettings(database_url=database_url, _env_file=None))


@pytest.mark.anyio
async def test_fixture_and_exact_record_reinsert_are_idempotent(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(CatalogueVersionRow)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(CatalogueVersionRecordRow))
                == 1
            )
        async with PostgresUnitOfWork(factory) as unit_of_work:
            assert await unit_of_work.catalogues.get(fixture.catalogue.catalogue_version_id) == fixture.catalogue
            assert await unit_of_work.instruments.get_identity(fixture.option.contract_id) == fixture.option
            assert await unit_of_work.instruments.get_version(fixture.option_version.version_id) == fixture.option_version
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_separate_knowledge_records_share_semantic_identity(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    later = replace(
        fixture.catalogue,
        recorded_at=fixture.catalogue.recorded_at + timedelta(minutes=1),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            first_id = await unit_of_work.catalogues.add(fixture.catalogue)
            second_id = await unit_of_work.catalogues.add(later)
            await unit_of_work.commit()
        assert fixture.catalogue.catalogue_version_id == later.catalogue_version_id
        assert first_id != second_id
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_conflicting_content_under_record_identity_fails_closed(
    reset_postgres_url: str,
) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            record_id = await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.commit()
        async with factory.begin() as session:
            await session.execute(
                update(CatalogueVersionRecordRow)
                .where(CatalogueVersionRecordRow.record_id == record_id)
                .values(source_provenance_id="sha256:" + "f" * 64)
            )
        with pytest.raises(SemanticCollisionError):
            async with PostgresUnitOfWork(factory) as unit_of_work:
                await unit_of_work.catalogues.add(fixture.catalogue)
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_catalogue_open_interval_replacement_is_bitemporal(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    first = fixture.catalogue
    second = CatalogueVersion(
        provider=first.provider,
        source_content_hash="sha256:" + "d" * 64,
        catalogue_schema_version=first.catalogue_schema_version,
        effective_from=first.effective_from + timedelta(days=1),
        effective_until=None,
        published_at=first.published_at + timedelta(hours=1),
        recorded_at=first.recorded_at + timedelta(hours=1),
        row_count=first.row_count,
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            first_record_id = await unit_of_work.catalogues.add(first)
            await unit_of_work.catalogues.add(second, first_record_id)
            await unit_of_work.commit()
        async with PostgresUnitOfWork(factory) as unit_of_work:
            before_known = await unit_of_work.catalogues.resolve(
                first.provider,
                second.effective_from + timedelta(minutes=1),
                second.recorded_at - timedelta(microseconds=1),
            )
            known_not_effective = await unit_of_work.catalogues.resolve(
                first.provider,
                second.effective_from - timedelta(microseconds=1),
                second.recorded_at,
            )
            known_and_effective = await unit_of_work.catalogues.resolve(
                first.provider,
                second.effective_from,
                second.recorded_at,
            )
            historical = await unit_of_work.catalogues.resolve(
                first.provider,
                first.effective_from,
                first.recorded_at,
            )
            current = await unit_of_work.catalogues.resolve(
                first.provider,
                second.effective_from,
                None,
            )
        assert before_known == first
        assert known_not_effective == first
        assert known_and_effective == second
        assert historical == first
        assert current == second
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_competing_successors_serialize_to_one_conflict(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    first = fixture.catalogue
    successors = (
        replace(
            first,
            source_content_hash="sha256:" + "d" * 64,
            recorded_at=first.recorded_at + timedelta(minutes=1),
        ),
        replace(
            first,
            source_content_hash="sha256:" + "e" * 64,
            recorded_at=first.recorded_at + timedelta(minutes=2),
        ),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            predecessor_id = await unit_of_work.catalogues.add(first)
            await unit_of_work.commit()

        async def insert_successor(value):
            try:
                async with PostgresUnitOfWork(factory) as unit_of_work:
                    await unit_of_work.catalogues.add(value, predecessor_id)
                    await unit_of_work.commit()
                return "committed"
            except TemporalSupersessionConflictError:
                return "conflict"

        results = await asyncio.gather(*(insert_successor(value) for value in successors))
        assert sorted(results) == ["committed", "conflict"]
        async with factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(CatalogueVersionRecordRow)
                .where(CatalogueVersionRecordRow.supersedes_record_id == predecessor_id)
            )
            assert count == 1
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_successor_scope_and_time_are_validated(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    first = fixture.catalogue
    wrong_scope = replace(
        first,
        provider="another-provider",
        source_content_hash="sha256:" + "d" * 64,
        recorded_at=first.recorded_at + timedelta(minutes=1),
    )
    not_later = replace(first, source_content_hash="sha256:" + "e" * 64)
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            predecessor_id = await unit_of_work.catalogues.add(first)
            await unit_of_work.commit()
        for invalid in (wrong_scope, not_later):
            with pytest.raises(TemporalSupersessionConflictError):
                async with PostgresUnitOfWork(factory) as unit_of_work:
                    await unit_of_work.catalogues.add(invalid, predecessor_id)
                    await unit_of_work.commit()
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_current_reads_keep_one_transaction_snapshot(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    first = fixture.catalogue
    second = replace(
        first,
        source_content_hash="sha256:" + "d" * 64,
        recorded_at=first.recorded_at + timedelta(minutes=1),
    )
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            first_id = await unit_of_work.catalogues.add(first)
            await unit_of_work.commit()
        async with PostgresUnitOfWork(factory) as reader:
            assert await reader.catalogues.resolve(first.provider, first.effective_from, None) == first
            async with PostgresUnitOfWork(factory) as writer:
                await writer.catalogues.add(second, first_id)
                await writer.commit()
            assert await reader.catalogues.resolve(first.provider, first.effective_from, None) == first
        async with PostgresUnitOfWork(factory) as fresh_reader:
            assert await fresh_reader.catalogues.resolve(first.provider, first.effective_from, None) == second
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_rollback_and_referenced_delete_safety(reset_postgres_url: str) -> None:
    engine = engine_for(reset_postgres_url)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogues.add(fixture.catalogue)
            await unit_of_work.rollback()
            with pytest.raises(UnitOfWorkStateError):
                await unit_of_work.catalogues.add(fixture.catalogue)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            repository = unit_of_work.catalogues
            await repository.add(fixture.catalogue)
            await unit_of_work.commit()
            with pytest.raises(UnitOfWorkStateError):
                await repository.get(fixture.catalogue.catalogue_version_id)
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
