from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import gzip
import hashlib
import json
import stat

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database_config import DatabaseSettings
from app.instruments.provider_catalogue import (
    CatalogueArtifactError,
    CatalogueConflictError,
    CatalogueIdempotencyConflictError,
    CatalogueNormalizationError,
)
from app.instruments.ports import PersistenceIntegrityError, SemanticCollisionError
from app.instruments.providers.upstox_catalogue import PROFILE_VERSION
from app.instruments.temporal_records import TemporalSupersessionConflictError
from app.instruments.temporal_records import (
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.models import (
    CatalogueIngestionRunRow,
    CatalogueMembershipRow,
    CatalogueRowOutcomeRow,
    CatalogueSourceArtifactRow,
    CatalogueVersionRecordRow,
    CatalogueVersionRow,
    InstrumentVersionRow,
    MarketInstrumentRow,
    ProviderContractMappingRow,
    ProviderMappingRecordRow,
    InstrumentVersionRecordRow,
)
from app.persistence.postgres.repositories import (
    PostgresCatalogueIngestionRepository,
    PostgresInstrumentRepository,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)


EFFECTIVE_FROM = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
SECOND_EFFECTIVE_FROM = datetime(2026, 8, 5, 3, 45, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "upstox"
NSE_JSON_GZ = FIXTURE_ROOT / "NSE.json.gz"
CANONICAL_JSON = FIXTURE_ROOT / "NSE.canonical.json"
DATA12_MODELS = (
    CatalogueSourceArtifactRow,
    CatalogueIngestionRunRow,
    CatalogueRowOutcomeRow,
    CatalogueMembershipRow,
)
INGESTION_MODELS = (
    CatalogueVersionRow,
    CatalogueVersionRecordRow,
    MarketInstrumentRow,
    InstrumentVersionRow,
    ProviderContractMappingRow,
    *DATA12_MODELS,
)


@pytest.mark.anyio
async def test_validate_only_and_dry_run_retain_no_artifacts_or_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    validate_settings = DatabaseSettings(_env_file=None)

    validate_result = await ingest_provider_catalogue(
        _command(mode="validate-only", idempotency_key=None),
        validate_settings,
    )
    dry_run_result = await ingest_provider_catalogue(
        _command(mode="dry-run", idempotency_key=None),
        settings,
    )

    assert validate_result.status == "accepted"
    assert dry_run_result.status == "accepted"
    assert dry_run_result.semantic_diff is not None
    assert dry_run_result.semantic_diff.as_dict() == {
        "added": 4,
        "unchanged": 0,
        "metadata_changed": 0,
        "provider_mapping_changed": 0,
        "disappeared": 0,
        "excluded": 1,
        "exact_duplicates": 0,
    }
    assert not (tmp_path / "artifacts").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


@pytest.mark.anyio
async def test_accepted_write_timestamp_is_the_single_durable_knowledge_boundary(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    started_at = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    recorded_at = started_at + timedelta(minutes=5)
    completed_at = recorded_at + timedelta(seconds=2)
    result = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-knowledge-boundary"),
        settings,
        clock=_clock(started_at, recorded_at, completed_at),
    )
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            run = await session.get(CatalogueIngestionRunRow, result.ingestion_run_id)
            catalogue_records = tuple(await session.scalars(select(CatalogueVersionRecordRow)))
            version_records = tuple(await session.scalars(select(InstrumentVersionRecordRow)))
            mapping_records = tuple(await session.scalars(select(ProviderMappingRecordRow)))
        assert run is not None
        assert run.started_at == started_at
        assert run.recorded_at == recorded_at
        assert run.completed_at == completed_at
        assert started_at < recorded_at <= completed_at
        assert {row.recorded_at for row in catalogue_records} == {recorded_at}
        assert {row.recorded_at for row in version_records} == {recorded_at}
        assert {row.recorded_at for row in mapping_records} == {recorded_at}
        async with PostgresUnitOfWork(factory) as unit_of_work:
            before = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                EFFECTIVE_FROM,
                started_at + timedelta(minutes=1),
            )
            accepted = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                EFFECTIVE_FROM,
                recorded_at,
            )
            catalogue_leaf = await unit_of_work.catalogues.resolve_knowledge_leaf(
                "upstox:upstox-nse-nifty-index-derivatives-v1"
            )
            membership = (
                await unit_of_work.catalogue_ingestions.list_memberships_for_catalogue(
                    result.catalogue_version_id
                )
            )[0]
            version_leaf = await unit_of_work.instruments.resolve_version_knowledge_leaf(
                membership.instrument_id
            )
            mapping_leaf = await unit_of_work.instruments.resolve_provider_key_knowledge_leaf(
                "upstox",
                membership.provider_contract_key,
            )
        assert before is None
        assert accepted is not None and accepted.catalogue_version_id == result.catalogue_version_id
        assert catalogue_leaf is not None
        assert catalogue_leaf.record_id == catalogue_temporal_record(catalogue_leaf.value).record_id
        assert version_leaf is not None
        assert version_leaf.record_id == instrument_version_temporal_record(version_leaf.value).record_id
        assert mapping_leaf is not None
        assert mapping_leaf.record_id == provider_mapping_temporal_record(mapping_leaf.value).record_id
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_non_commit_modes_never_request_a_durable_knowledge_timestamp(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    invocation = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)

    await ingest_provider_catalogue(
        _command(mode="validate-only", idempotency_key=None),
        DatabaseSettings(_env_file=None),
        clock=_clock(invocation),
    )
    await ingest_provider_catalogue(
        _command(mode="dry-run", idempotency_key=None),
        settings,
        clock=_clock(invocation),
    )


@pytest.mark.anyio
async def test_sequential_catalogues_preserve_temporal_history_and_binding(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-sequential-a"),
        settings,
    )
    second_file = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace(
            '"trading_symbol": "NIFTY26AUGFUT"',
            '"trading_symbol": "NIFTY26AUGFUT-UPDATED"',
        ),
        "sequential-b.json.gz",
    )
    second_command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-sequential-b",
        file=second_file,
        effective_from=SECOND_EFFECTIVE_FROM,
        supersedes_catalogue_record_id=first.catalogue_record_id,
    )
    dry_run = await ingest_provider_catalogue(
        replace(second_command, mode="dry-run", idempotency_key=None),
        settings,
    )
    second = await ingest_provider_catalogue(second_command, settings)
    state = await _sequential_state(settings, first, second)

    assert dry_run.semantic_diff is not None
    assert dry_run.semantic_diff.as_dict() == {
        "added": 0,
        "unchanged": 3,
        "metadata_changed": 1,
        "provider_mapping_changed": 0,
        "disappeared": 0,
        "excluded": 1,
        "exact_duplicates": 0,
    }
    assert state["catalogue_before_second_known"] == first.catalogue_version_id
    assert state["catalogue_known_before_effective"] == first.catalogue_version_id
    assert state["catalogue_current"] == second.catalogue_version_id
    assert state["mapping_before_second_known"] == state["first_mapping_id"]
    assert state["mapping_known_before_effective"] == state["first_mapping_id"]
    assert state["mapping_current"] == state["second_mapping_id"]
    assert state["first_instrument_id"] == state["second_instrument_id"]
    assert state["catalogue_successor_target"] == first.catalogue_record_id
    assert state["version_successor_target"] == state["first_version_record_id"]
    assert state["mapping_successor_target"] == state["first_mapping_record_id"]
    assert state["version_root_count"] == 4
    assert state["mapping_root_count"] == 4
    assert state["version_successor_count"] == 4
    assert state["mapping_successor_count"] == 4


@pytest.mark.anyio
async def test_open_ended_historical_correction_supersedes_the_current_knowledge_leaf(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-historical-open-a"),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 5, 10, 1, tzinfo=UTC),
            datetime(2026, 8, 5, 10, 2, tzinfo=UTC),
        ),
    )
    historical_from = EFFECTIVE_FROM - timedelta(days=2)
    with pytest.raises(CatalogueConflictError, match="explicit catalogue predecessor"):
        await ingest_provider_catalogue(
            _command(
                mode="commit",
                idempotency_key="DATA-1.2-historical-open-missing",
                effective_from=historical_from,
            ),
            settings,
            clock=_clock(
                datetime(2026, 8, 5, 10, 3, tzinfo=UTC),
                datetime(2026, 8, 5, 10, 4, tzinfo=UTC),
            ),
        )
    historical = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-historical-open-h",
            effective_from=historical_from,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 10, 5, tzinfo=UTC),
            datetime(2026, 8, 5, 10, 6, tzinfo=UTC),
            datetime(2026, 8, 5, 10, 7, tzinfo=UTC),
        ),
    )

    state = await _historical_state(settings, first, historical, EFFECTIVE_FROM)

    assert state["selected_catalogue_id"] == historical.catalogue_version_id
    assert state["selected_mapping_id"] == state["successor_mapping_id"]
    assert state["catalogue_root_count"] == 1
    assert state["catalogue_successor_count"] == 1
    assert state["version_root_count"] == 4
    assert state["version_successor_count"] == 4
    assert state["mapping_root_count"] == 4
    assert state["mapping_successor_count"] == 4
    assert state["catalogue_edge_preserved"]
    assert state["version_edge_preserved"]
    assert state["mapping_edge_preserved"]


@pytest.mark.anyio
async def test_bounded_historical_backfill_preserves_historical_and_current_market_reads(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-backfill-a"),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 11, 0, tzinfo=UTC),
            datetime(2026, 8, 5, 11, 1, tzinfo=UTC),
            datetime(2026, 8, 5, 11, 2, tzinfo=UTC),
        ),
    )
    historical_from = EFFECTIVE_FROM - timedelta(days=3)
    historical_until = EFFECTIVE_FROM - timedelta(days=1)
    backfill = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-backfill-h",
            effective_from=historical_from,
            effective_until=historical_until,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 11, 3, tzinfo=UTC),
            datetime(2026, 8, 5, 11, 4, tzinfo=UTC),
            datetime(2026, 8, 5, 11, 5, tzinfo=UTC),
        ),
    )
    historical_market_time = historical_from + timedelta(hours=1)
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            first_run = await session.get(CatalogueIngestionRunRow, first.ingestion_run_id)
            backfill_run = await session.get(CatalogueIngestionRunRow, backfill.ingestion_run_id)
            first_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id == first.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key
                        == "NSE_FO|SANITIZED_NIFTY_FUT",
                    )
                )
            ).one()
            backfill_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == backfill.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key
                        == "NSE_FO|SANITIZED_NIFTY_FUT",
                    )
                )
            ).one()
        assert first_run is not None and backfill_run is not None
        async with PostgresUnitOfWork(factory) as unit_of_work:
            before_known = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                historical_market_time,
                first_run.recorded_at,
            )
            historical = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                historical_market_time,
                backfill_run.recorded_at,
            )
            current = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                EFFECTIVE_FROM,
                backfill_run.recorded_at,
            )
            mapping_before_known = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                first_membership.provider_contract_key,
                historical_market_time,
                first_run.recorded_at,
            )
            historical_mapping = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                first_membership.provider_contract_key,
                historical_market_time,
                backfill_run.recorded_at,
            )
            current_mapping = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                first_membership.provider_contract_key,
                EFFECTIVE_FROM,
                backfill_run.recorded_at,
            )
        assert before_known is None
        assert historical is not None
        assert historical.catalogue_version_id == backfill.catalogue_version_id
        assert current is not None
        assert current.catalogue_version_id == first.catalogue_version_id
        assert mapping_before_known is None
        assert historical_mapping is not None
        assert historical_mapping.mapping_id == backfill_membership.mapping_id
        assert current_mapping is not None
        assert current_mapping.mapping_id == first_membership.mapping_id
    finally:
        await dispose_database_engine(engine)
    state = await _historical_state(settings, first, backfill, historical_market_time)
    assert state["catalogue_root_count"] == 1
    assert state["catalogue_successor_count"] == 1
    assert state["version_root_count"] == 4
    assert state["version_successor_count"] == 4
    assert state["mapping_root_count"] == 4
    assert state["mapping_successor_count"] == 4
    assert state["catalogue_edge_preserved"]
    assert state["version_edge_preserved"]
    assert state["mapping_edge_preserved"]


@pytest.mark.anyio
async def test_overlapping_historical_correction_applies_transitive_market_supersession(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-overlap-a"),
        settings,
        clock=_clock(
            datetime(2026, 8, 6, 9, 0, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 1, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 2, tzinfo=UTC),
        ),
    )
    second = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-overlap-b",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 6, 9, 3, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 4, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 5, tzinfo=UTC),
        ),
    )
    historical_from = EFFECTIVE_FROM + timedelta(hours=8)
    historical_until = EFFECTIVE_FROM + timedelta(hours=14)
    historical = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-overlap-h",
            effective_from=historical_from,
            effective_until=historical_until,
            supersedes_catalogue_record_id=second.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 6, 9, 6, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 7, tzinfo=UTC),
            datetime(2026, 8, 6, 9, 8, tzinfo=UTC),
        ),
    )
    provider_key = "NSE_FO|SANITIZED_NIFTY_FUT"
    inside_h = historical_from + timedelta(hours=1)
    before_h = historical_from - timedelta(hours=1)
    after_h = historical_until + timedelta(hours=1)
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            second_run = await session.get(CatalogueIngestionRunRow, second.ingestion_run_id)
            historical_run = await session.get(
                CatalogueIngestionRunRow,
                historical.ingestion_run_id,
            )
            memberships = {}
            for label, result in (("A", first), ("B", second), ("H", historical)):
                memberships[label] = (
                    await session.scalars(
                        select(CatalogueMembershipRow).where(
                            CatalogueMembershipRow.catalogue_version_id
                            == result.catalogue_version_id,
                            CatalogueMembershipRow.provider_contract_key == provider_key,
                        )
                    )
                ).one()
            counts = {
                "catalogue": await _temporal_counts(session, CatalogueVersionRecordRow),
                "version": await _temporal_counts(session, InstrumentVersionRecordRow),
                "mapping": await _temporal_counts(session, ProviderMappingRecordRow),
            }
        assert second_run is not None and historical_run is not None
        async with PostgresUnitOfWork(factory) as unit_of_work:
            async def resolve(market_as_of: datetime, known_as_of: datetime):
                catalogue = await unit_of_work.catalogues.resolve(
                    "upstox:upstox-nse-nifty-index-derivatives-v1",
                    market_as_of,
                    known_as_of,
                )
                version = await unit_of_work.instruments.resolve_version_state(
                    memberships["A"].instrument_id,
                    market_as_of,
                    known_as_of,
                )
                mapping = await unit_of_work.instruments.resolve_provider_key(
                    "upstox",
                    provider_key,
                    market_as_of,
                    known_as_of,
                )
                assert catalogue is not None and version is not None and mapping is not None
                return catalogue.catalogue_version_id, version.value.version_id, mapping.mapping_id

            before_h_known = await resolve(inside_h, second_run.recorded_at)
            after_h_known = await resolve(inside_h, historical_run.recorded_at)
            at_b = await resolve(SECOND_EFFECTIVE_FROM, historical_run.recorded_at)
            before_h_interval = await resolve(before_h, historical_run.recorded_at)
            after_h_interval = await resolve(after_h, historical_run.recorded_at)
    finally:
        await dispose_database_engine(engine)

    assert before_h_known == (
        first.catalogue_version_id,
        memberships["A"].version_id,
        memberships["A"].mapping_id,
    )
    assert after_h_known == (
        historical.catalogue_version_id,
        memberships["H"].version_id,
        memberships["H"].mapping_id,
    )
    assert at_b == (
        second.catalogue_version_id,
        memberships["B"].version_id,
        memberships["B"].mapping_id,
    )
    expected_a = (
        first.catalogue_version_id,
        memberships["A"].version_id,
        memberships["A"].mapping_id,
    )
    assert before_h_interval == expected_a
    assert after_h_interval == expected_a
    assert counts == {
        "catalogue": (1, 2),
        "version": (4, 8),
        "mapping": (4, 8),
    }


@pytest.mark.anyio
async def test_stale_predecessor_rejects_and_same_effective_time_correction_succeeds(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-stale-a"),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 1, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 2, tzinfo=UTC),
        ),
    )
    second = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-stale-b",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 12, 3, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 4, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 5, tzinfo=UTC),
        ),
    )
    with pytest.raises(CatalogueConflictError, match="current knowledge leaf"):
        await ingest_provider_catalogue(
            _command(
                mode="commit",
                idempotency_key="DATA-1.2-stale-rejected",
                effective_from=EFFECTIVE_FROM - timedelta(days=1),
                supersedes_catalogue_record_id=first.catalogue_record_id,
            ),
            settings,
            clock=_clock(
                datetime(2026, 8, 5, 12, 6, tzinfo=UTC),
                datetime(2026, 8, 5, 12, 7, tzinfo=UTC),
            ),
        )
    correction_file = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace(
            '"trading_symbol": "NIFTY26AUGFUT"',
            '"trading_symbol": "NIFTY26AUGFUT-CORRECTED"',
        ),
        "same-effective-c.json.gz",
    )
    correction = await ingest_provider_catalogue(
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-same-effective-c",
            file=correction_file,
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=second.catalogue_record_id,
        ),
        settings,
        clock=_clock(
            datetime(2026, 8, 5, 12, 8, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 9, tzinfo=UTC),
            datetime(2026, 8, 5, 12, 10, tzinfo=UTC),
        ),
    )

    assert correction.catalogue_record_id not in {
        first.catalogue_record_id,
        second.catalogue_record_id,
    }
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            selected = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM,
                None,
            )
    finally:
        await dispose_database_engine(engine)
    assert selected is not None
    assert selected.catalogue_version_id == correction.catalogue_version_id


@pytest.mark.anyio
async def test_disappearance_is_informational_and_does_not_close_temporal_state(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-disappearance-a"),
        settings,
    )
    rows = json.loads(CANONICAL_JSON.read_text())
    disappeared_key = rows[3]["instrument_key"]
    second_file = _fixture_variant(
        tmp_path,
        json.dumps(rows[:3] + rows[4:]),
        "disappearance-b.json.gz",
    )
    second_command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-disappearance-b",
        file=second_file,
        effective_from=SECOND_EFFECTIVE_FROM,
        supersedes_catalogue_record_id=first.catalogue_record_id,
    )
    dry_run = await ingest_provider_catalogue(
        replace(second_command, mode="dry-run", idempotency_key=None),
        settings,
    )
    await ingest_provider_catalogue(second_command, settings)
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            mapping = await unit_of_work.instruments.resolve_provider_key_state(
                "upstox",
                disappeared_key,
                SECOND_EFFECTIVE_FROM,
                None,
            )
    finally:
        await dispose_database_engine(engine)

    assert dry_run.disappeared_provider_contract_keys == (disappeared_key,)
    assert dry_run.semantic_diff is not None
    assert dry_run.semantic_diff.disappeared == 1
    assert mapping is not None
    assert mapping.value.effective_until is None


@pytest.mark.anyio
async def test_provider_key_economic_reassignment_is_rejected_in_dry_run_and_commit(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-reassignment-a"),
        settings,
    )
    reassigned = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace('"strike_price": 24500.0', '"strike_price": 24600.0', 1),
        "reassignment-b.json.gz",
    )
    for mode, idempotency_key in (("dry-run", None), ("commit", "DATA-1.2-reassignment-b")):
        with pytest.raises(CatalogueConflictError, match="economic instrument"):
            await ingest_provider_catalogue(
                _command(
                    mode=mode,
                    idempotency_key=idempotency_key,
                    file=reassigned,
                    effective_from=SECOND_EFFECTIVE_FROM,
                    supersedes_catalogue_record_id=first.catalogue_record_id,
                ),
                settings,
            )


@pytest.mark.anyio
async def test_concurrent_catalogue_transitions_serialize_and_exact_replay_is_idempotent(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first_commands = (
        _command(mode="commit", idempotency_key="DATA-1.2-concurrent-root-a"),
        _command(mode="commit", idempotency_key="DATA-1.2-concurrent-root-b"),
    )
    first_results = await asyncio.gather(
        *(ingest_provider_catalogue(command, settings) for command in first_commands),
        return_exceptions=True,
    )
    roots = [result for result in first_results if not isinstance(result, Exception)]
    root_errors = [result for result in first_results if isinstance(result, Exception)]

    assert len(roots) == 1
    assert len(root_errors) == 1
    first = roots[0]
    successors = (
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-concurrent-successor-a",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-concurrent-successor-b",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
    )
    successor_results = await asyncio.gather(
        *(ingest_provider_catalogue(command, settings) for command in successors),
        return_exceptions=True,
    )
    committed = [result for result in successor_results if not isinstance(result, Exception)]
    rejected = [result for result in successor_results if isinstance(result, Exception)]

    assert len(committed) == 1
    assert len(rejected) == 1
    committed_command = next(
        command
        for command, result in zip(successors, successor_results, strict=True)
        if not isinstance(result, Exception)
    )
    replay_results = await asyncio.gather(
        ingest_provider_catalogue(committed_command, settings),
        ingest_provider_catalogue(committed_command, settings),
    )
    assert replay_results[0].ingestion_run_id == replay_results[1].ingestion_run_id
    assert replay_results[0].catalogue_record_id == replay_results[1].catalogue_record_id


@pytest.mark.anyio
async def test_concurrent_exact_command_returns_commit_and_verified_idempotent_success(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-concurrent-exact-command",
    )

    results = await asyncio.gather(
        ingest_provider_catalogue(command, settings),
        ingest_provider_catalogue(command, settings),
    )

    assert results[0].ingestion_run_id == results[1].ingestion_run_id
    assert results[0].catalogue_record_id == results[1].catalogue_record_id
    counts = await _counts(settings, INGESTION_MODELS)
    assert counts["catalogue_ingestion_runs"] == 1
    assert counts["catalogue_version_records"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "error"),
    [
        ("add_source_artifact", SemanticCollisionError("semantic collision")),
        ("add_source_artifact", PersistenceIntegrityError("integrity failure")),
        (
            "add_source_artifact",
            IntegrityError("insert", {}, Exception("unrelated constraint")),
        ),
        ("add_version", TemporalSupersessionConflictError("temporal conflict")),
    ],
)
async def test_non_idempotency_persistence_errors_preserve_their_category(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
    monkeypatch,
    method_name: str,
    error: Exception,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )

    async def fail(*args, **kwargs):
        raise error

    owner = (
        PostgresInstrumentRepository
        if method_name == "add_version"
        else PostgresCatalogueIngestionRepository
    )
    monkeypatch.setattr(owner, method_name, fail)

    with pytest.raises(type(error)):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key=f"DATA-1.2-{method_name}"),
            settings,
        )


@pytest.mark.anyio
async def test_commit_retains_artifact_atomically_and_replay_is_idempotent(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    command = _command(mode="commit", idempotency_key="DATA-1.2-persistence-commit")

    first = await ingest_provider_catalogue(command, settings)
    counts_after_first = await _counts(settings, INGESTION_MODELS)
    second = await ingest_provider_catalogue(command, settings)
    counts_after_second = await _counts(settings, INGESTION_MODELS)
    retained_path = tmp_path / "artifacts" / str(first.artifact_object_key)

    assert first.ingestion_run_id == second.ingestion_run_id
    assert first.catalogue_record_id == second.catalogue_record_id
    assert counts_after_first == counts_after_second
    assert counts_after_first["catalogue_ingestion_runs"] == 1
    assert counts_after_first["catalogue_source_artifacts"] == 1
    assert counts_after_first["catalogue_row_outcomes"] == 5
    assert counts_after_first["catalogue_memberships"] == 4
    assert retained_path.read_bytes() == NSE_JSON_GZ.read_bytes()
    assert stat.S_IMODE(retained_path.stat().st_mode) == 0o600
    assert not list(retained_path.parent.glob(".tmp-*"))
    assert first.artifact_object_key == _expected_object_key(retained_path)


@pytest.mark.anyio
async def test_commit_requires_postgres_artifact_root_and_idempotency_key(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    no_database = DatabaseSettings(
        _env_file=None,
        database_url=None,
        catalogue_artifact_root=str(tmp_path / "artifacts"),
    )
    no_artifact_root = postgres_settings.model_copy(update={"catalogue_artifact_root": None})
    with pytest.raises(CatalogueConflictError, match="idempotency key"):
        await ingest_provider_catalogue(_command(mode="commit", idempotency_key=None), no_artifact_root)
    with pytest.raises(Exception, match="DATABASE_URL"):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-no-database"),
            no_database,
        )
    with pytest.raises(Exception, match="CATALOGUE_ARTIFACT_ROOT"):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-no-root"),
            no_artifact_root,
        )
    assert await _counts(postgres_settings, INGESTION_MODELS) == {
        model.__tablename__: 0 for model in INGESTION_MODELS
    }


@pytest.mark.anyio
async def test_idempotency_conflict_fails_without_extra_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-conflict"),
        settings,
    )
    counts = await _counts(settings, INGESTION_MODELS)

    with pytest.raises(CatalogueIdempotencyConflictError):
        await ingest_provider_catalogue(
            _command(
                mode="commit",
                idempotency_key="DATA-1.2-conflict",
                effective_from=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
            ),
            settings,
        )

    assert await _counts(settings, INGESTION_MODELS) == counts


@pytest.mark.anyio
async def test_malformed_in_profile_row_rejects_without_any_catalogue_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    malformed = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace('"underlying_symbol": "NIFTY"', '"underlying_symbol": "BANKNIFTY"', 1),
    )

    with pytest.raises(CatalogueNormalizationError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-rejected", file=malformed),
            settings,
        )

    assert not (tmp_path / "artifacts").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


@pytest.mark.anyio
async def test_excluded_valid_nse_rows_are_persisted_without_rejection(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})

    result = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-exclusion"),
        settings,
    )
    dispositions = await _dispositions(settings)

    assert result.excluded_count == 1
    assert dispositions == {"accepted": 4, "excluded_by_profile": 1}


@pytest.mark.anyio
async def test_retained_artifact_mismatch_and_symlink_paths_fail_closed(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    command = _command(mode="commit", idempotency_key="DATA-1.2-artifact-mismatch")
    result = await ingest_provider_catalogue(command, settings)
    retained_path = tmp_path / "artifacts" / str(result.artifact_object_key)
    counts = await _counts(settings, INGESTION_MODELS)
    retained_path.write_bytes(b"corrupted")

    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(command, settings)

    symlink_source = tmp_path / "NSE-symlink.json.gz"
    symlink_source.symlink_to(NSE_JSON_GZ)
    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-source-symlink", file=symlink_source),
            settings,
        )

    assert await _counts(settings, INGESTION_MODELS) == counts


@pytest.mark.anyio
async def test_artifact_store_parent_symlink_is_rejected(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "sha256").symlink_to(tmp_path / "outside")
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(artifact_root)})

    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-store-symlink"),
            settings,
        )

    assert not (tmp_path / "outside").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


def _command(
    *,
    mode: str,
    idempotency_key: str | None,
    file: Path = NSE_JSON_GZ,
    effective_from: datetime = EFFECTIVE_FROM,
    effective_until: datetime | None = None,
    supersedes_catalogue_record_id: str | None = None,
) -> CatalogueIngestionCommand:
    return CatalogueIngestionCommand(
        profile=PROFILE_VERSION,
        file=file,
        effective_from=effective_from,
        effective_until=effective_until,
        idempotency_key=idempotency_key,
        expected_compressed_sha256=None,
        supersedes_catalogue_record_id=supersedes_catalogue_record_id,
        mode=mode,
    )


async def _counts(settings: DatabaseSettings, models: tuple[type, ...]) -> dict[str, int]:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            return {
                model.__tablename__: int(await session.scalar(select(func.count()).select_from(model)))
                for model in models
            }
    finally:
        await dispose_database_engine(engine)


async def _temporal_counts(session, model: type) -> tuple[int, int]:
    roots = int(
        await session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.supersedes_record_id.is_(None))
        )
    )
    successors = int(
        await session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.supersedes_record_id.is_not(None))
        )
    )
    return roots, successors


async def _dispositions(settings: DatabaseSettings) -> dict[str, int]:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(CatalogueRowOutcomeRow.disposition, func.count())
                    .group_by(CatalogueRowOutcomeRow.disposition)
                    .order_by(CatalogueRowOutcomeRow.disposition)
                )
            ).all()
            return {str(disposition): int(count) for disposition, count in rows}
    finally:
        await dispose_database_engine(engine)


async def _sequential_state(settings: DatabaseSettings, first, second) -> dict[str, object]:
    provider_key = "NSE_FO|SANITIZED_NIFTY_FUT"
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            first_run = await session.get(CatalogueIngestionRunRow, first.ingestion_run_id)
            second_run = await session.get(CatalogueIngestionRunRow, second.ingestion_run_id)
            first_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == first.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key == provider_key,
                    )
                )
            ).one()
            second_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == second.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key == provider_key,
                    )
                )
            ).one()
            first_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == first_membership.version_id
                    )
                )
            ).one()
            second_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == second_membership.version_id
                    )
                )
            ).one()
            first_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == first_membership.mapping_id
                    )
                )
            ).one()
            second_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == second_membership.mapping_id
                    )
                )
            ).one()
            second_catalogue_record = await session.get(
                CatalogueVersionRecordRow,
                second.catalogue_record_id,
            )
            version_root_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InstrumentVersionRecordRow)
                    .where(InstrumentVersionRecordRow.supersedes_record_id.is_(None))
                )
            )
            mapping_root_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderMappingRecordRow)
                    .where(ProviderMappingRecordRow.supersedes_record_id.is_(None))
                )
            )
            version_successor_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InstrumentVersionRecordRow)
                    .where(InstrumentVersionRecordRow.supersedes_record_id.is_not(None))
                )
            )
            mapping_successor_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderMappingRecordRow)
                    .where(ProviderMappingRecordRow.supersedes_record_id.is_not(None))
                )
            )
        assert first_run is not None
        assert second_run is not None
        assert second_catalogue_record is not None
        async with PostgresUnitOfWork(factory) as unit_of_work:
            catalogue_before_second_known = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM,
                first_run.recorded_at,
            )
            catalogue_known_before_effective = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
                second_run.recorded_at,
            )
            catalogue_current = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM,
                None,
            )
            mapping_before_second_known = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM,
                first_run.recorded_at,
            )
            mapping_known_before_effective = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
                second_run.recorded_at,
            )
            mapping_current = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM,
                None,
            )
        return {
            "catalogue_before_second_known": catalogue_before_second_known.catalogue_version_id,
            "catalogue_known_before_effective": catalogue_known_before_effective.catalogue_version_id,
            "catalogue_current": catalogue_current.catalogue_version_id,
            "mapping_before_second_known": mapping_before_second_known.mapping_id,
            "mapping_known_before_effective": mapping_known_before_effective.mapping_id,
            "mapping_current": mapping_current.mapping_id,
            "first_mapping_id": first_membership.mapping_id,
            "second_mapping_id": second_membership.mapping_id,
            "first_instrument_id": first_membership.instrument_id,
            "second_instrument_id": second_membership.instrument_id,
            "catalogue_successor_target": second_catalogue_record.supersedes_record_id,
            "version_successor_target": second_version_record.supersedes_record_id,
            "mapping_successor_target": second_mapping_record.supersedes_record_id,
            "first_version_record_id": first_version_record.record_id,
            "first_mapping_record_id": first_mapping_record.record_id,
            "version_root_count": version_root_count,
            "mapping_root_count": mapping_root_count,
            "version_successor_count": version_successor_count,
            "mapping_successor_count": mapping_successor_count,
        }
    finally:
        await dispose_database_engine(engine)


async def _historical_state(
    settings: DatabaseSettings,
    first,
    successor,
    market_as_of: datetime,
) -> dict[str, object]:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            successor_run = await session.get(
                CatalogueIngestionRunRow,
                successor.ingestion_run_id,
            )
            counts = {
                "catalogue_root_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CatalogueVersionRecordRow)
                        .where(CatalogueVersionRecordRow.supersedes_record_id.is_(None))
                    )
                ),
                "catalogue_successor_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CatalogueVersionRecordRow)
                        .where(CatalogueVersionRecordRow.supersedes_record_id.is_not(None))
                    )
                ),
                "version_root_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(InstrumentVersionRecordRow)
                        .where(InstrumentVersionRecordRow.supersedes_record_id.is_(None))
                    )
                ),
                "version_successor_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(InstrumentVersionRecordRow)
                        .where(InstrumentVersionRecordRow.supersedes_record_id.is_not(None))
                    )
                ),
                "mapping_root_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ProviderMappingRecordRow)
                        .where(ProviderMappingRecordRow.supersedes_record_id.is_(None))
                    )
                ),
                "mapping_successor_count": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ProviderMappingRecordRow)
                        .where(ProviderMappingRecordRow.supersedes_record_id.is_not(None))
                    )
                ),
            }
            successor_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == successor.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key
                        == "NSE_FO|SANITIZED_NIFTY_FUT",
                    )
                )
            ).one()
            first_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id == first.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key
                        == successor_membership.provider_contract_key,
                    )
                )
            ).one()
            first_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == first_membership.version_id
                    )
                )
            ).one()
            successor_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == successor_membership.version_id
                    )
                )
            ).one()
            first_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == first_membership.mapping_id
                    )
                )
            ).one()
            successor_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == successor_membership.mapping_id
                    )
                )
            ).one()
            successor_catalogue_record = await session.get(
                CatalogueVersionRecordRow,
                successor.catalogue_record_id,
            )
        assert successor_run is not None
        async with PostgresUnitOfWork(factory) as unit_of_work:
            selected = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                market_as_of,
                successor_run.recorded_at,
            )
            selected_mapping = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                successor_membership.provider_contract_key,
                market_as_of,
                successor_run.recorded_at,
            )
        assert selected is not None
        assert selected_mapping is not None
        assert successor_catalogue_record is not None
        return {
            "selected_catalogue_id": selected.catalogue_version_id,
            "selected_mapping_id": selected_mapping.mapping_id,
            "successor_mapping_id": successor_membership.mapping_id,
            "catalogue_edge_preserved": (
                successor_catalogue_record.supersedes_record_id == first.catalogue_record_id
            ),
            "version_edge_preserved": (
                successor_version_record.supersedes_record_id == first_version_record.record_id
            ),
            "mapping_edge_preserved": (
                successor_mapping_record.supersedes_record_id == first_mapping_record.record_id
            ),
            **counts,
        }
    finally:
        await dispose_database_engine(engine)


def _fixture_variant(tmp_path: Path, payload: str, name: str = "variant.json.gz") -> Path:
    path = tmp_path / name
    path.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    return path


def _expected_object_key(retained_path: Path) -> str:
    compressed_sha256 = hashlib.sha256(retained_path.read_bytes()).hexdigest()
    return f"sha256/{compressed_sha256[:2]}/{compressed_sha256}.json.gz"


def _clock(*values: datetime):
    iterator = iter(values)
    return lambda: next(iterator)
