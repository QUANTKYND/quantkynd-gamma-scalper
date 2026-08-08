from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.instruments.provider_catalogue import (
    CatalogueIngestionDisposition,
    CatalogueIngestionRun,
    CatalogueMembership,
    CatalogueRowOutcome,
    CatalogueSourceArtifact,
)
from app.instruments.temporal_records import catalogue_temporal_record
from app.market_data.quality.contracts import ReceiptBasis
from app.market_data.quality.ports import (
    CatalogueMembershipReceipt,
    ReceiptTargetKind,
    TemporalRecordReceipt,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.models import (
    MARKET_DATA_QUALITY_CATALOGUE_MEMBERSHIP_RECEIPTS_TABLE,
    MARKET_DATA_QUALITY_CATALOGUE_VERSION_RECEIPTS_TABLE,
    MARKET_DATA_QUALITY_INSTRUMENT_VERSION_RECEIPTS_TABLE,
    MARKET_DATA_QUALITY_PROVIDER_MAPPING_RECEIPTS_TABLE,
    MARKET_DATA_QUALITY_TRADING_SESSION_RECEIPTS_TABLE,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


TEMPORAL_RECEIPTS = (
    (
        MARKET_DATA_QUALITY_PROVIDER_MAPPING_RECEIPTS_TABLE,
        ReceiptTargetKind.PROVIDER_MAPPING_RECORD,
        1,
    ),
    (
        MARKET_DATA_QUALITY_INSTRUMENT_VERSION_RECEIPTS_TABLE,
        ReceiptTargetKind.INSTRUMENT_VERSION_RECORD,
        3,
    ),
    (
        MARKET_DATA_QUALITY_CATALOGUE_VERSION_RECEIPTS_TABLE,
        ReceiptTargetKind.CATALOGUE_VERSION_RECORD,
        1,
    ),
    (
        MARKET_DATA_QUALITY_TRADING_SESSION_RECEIPTS_TABLE,
        ReceiptTargetKind.TRADING_SESSION_RECORD,
        1,
    ),
)


async def _temporal_receipt_snapshot(factory) -> dict[str, tuple[dict[str, object], ...]]:
    snapshot: dict[str, tuple[dict[str, object], ...]] = {}
    async with factory() as session:
        for table, _, _ in TEMPORAL_RECEIPTS:
            rows = (
                await session.execute(
                    select(table).order_by(table.c.record_id)
                )
            ).mappings().all()
            snapshot[table.name] = tuple(dict(row) for row in rows)
    return snapshot


@pytest.mark.anyio
async def test_temporal_repositories_insert_database_owned_receipts(
    reset_postgres_url: str,
    postgres_settings,
) -> None:
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        first = await _temporal_receipt_snapshot(factory)

        for table, target_kind, expected_count in TEMPORAL_RECEIPTS:
            rows = first[table.name]
            assert len(rows) == expected_count
            for row in rows:
                assert row["receipt_basis"] == ReceiptBasis.REPOSITORY_INSERT.value
                assert row["bootstrap_revision"] is None
                receipt = TemporalRecordReceipt(
                    target_kind,
                    row["record_id"],
                    row["receipt_at"],
                    ReceiptBasis.REPOSITORY_INSERT,
                )
                assert row["canonical_payload_hash"] == receipt.canonical_payload_hash
                assert row["receipt_at"] > fixture.catalogue.recorded_at

        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        assert await _temporal_receipt_snapshot(factory) == first

        async with PostgresUnitOfWork(factory) as unit_of_work:
            state = await unit_of_work.trading_sessions.resolve_state(
                fixture.session.exchange,
                fixture.session.session_date,
                fixture.session.session_kind.value,
                None,
            )
            assert state is not None
            assert state.value == fixture.session_version
            assert state.record_id in {
                row["record_id"]
                for row in first[
                    MARKET_DATA_QUALITY_TRADING_SESSION_RECEIPTS_TABLE.name
                ]
            }
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_catalogue_membership_repository_inserts_exact_ingestion_receipt(
    reset_postgres_url: str,
    postgres_settings,
) -> None:
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    catalogue_record_id = catalogue_temporal_record(fixture.catalogue).record_id
    profile = "upstox-nse-nifty-index-derivatives-v1"
    artifact = CatalogueSourceArtifact(
        provider=fixture.catalogue.provider,
        profile_version=profile,
        media_type="application/json",
        compression="gzip",
        compressed_sha256="sha256:" + "1" * 64,
        decompressed_sha256="sha256:" + "2" * 64,
        compressed_byte_count=1,
        decompressed_byte_count=2,
        source_schema_version="fixture-v1",
        artifact_object_key="fixture/instruments.json.gz",
    )
    at = fixture.catalogue.recorded_at + timedelta(minutes=1)
    run = CatalogueIngestionRun(
        idempotency_key="data15-membership-receipt-fixture",
        command_digest="sha256:" + "3" * 64,
        source_artifact_id=artifact.source_artifact_id,
        catalogue_version_id=fixture.catalogue.catalogue_version_id,
        catalogue_record_id=catalogue_record_id,
        profile_version=profile,
        original_file_name="instruments.json.gz",
        effective_from=fixture.catalogue.effective_from,
        effective_until=fixture.catalogue.effective_until,
        started_at=at,
        recorded_at=at,
        completed_at=at,
        normalized_catalogue_hash="sha256:" + "4" * 64,
        physical_row_count=1,
        accepted_unique_count=1,
        exact_duplicate_count=0,
        excluded_count=0,
        database_revision="20260804_05",
    )
    outcome = CatalogueRowOutcome(
        ingestion_run_id=run.ingestion_run_id,
        source_row_occurrence_id="sha256:" + "5" * 64,
        source_row_semantic_id="sha256:" + "6" * 64,
        physical_row_number=1,
        raw_row_hash="sha256:" + "7" * 64,
        normalized_row_hash="sha256:" + "8" * 64,
        provider_contract_key=fixture.provider_mapping.provider_contract_key,
        disposition=CatalogueIngestionDisposition.ACCEPTED,
        reason_codes=(),
        instrument_id=fixture.option.contract_id,
        version_id=fixture.option_version.version_id,
        mapping_id=fixture.provider_mapping.mapping_id,
    )
    membership = CatalogueMembership(
        catalogue_version_id=fixture.catalogue.catalogue_version_id,
        row_outcome_id=outcome.row_outcome_id,
        source_row_occurrence_id=outcome.source_row_occurrence_id,
        source_row_semantic_id=outcome.source_row_semantic_id,
        instrument_id=fixture.option.contract_id,
        version_id=fixture.option_version.version_id,
        mapping_id=fixture.provider_mapping.mapping_id,
        provider_contract_key=fixture.provider_mapping.provider_contract_key,
        raw_row_hash=outcome.raw_row_hash,
        normalized_row_hash=outcome.normalized_row_hash,
    )
    table = MARKET_DATA_QUALITY_CATALOGUE_MEMBERSHIP_RECEIPTS_TABLE
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogue_ingestions.add_source_artifact(artifact)
            await unit_of_work.catalogue_ingestions.add_ingestion_run(run)
            await unit_of_work.catalogue_ingestions.add_row_outcomes((outcome,))
            await unit_of_work.catalogue_ingestions.add_memberships((membership,))
            await unit_of_work.commit()

        async with factory() as session:
            first = (
                await session.execute(
                    select(table).where(
                        table.c.membership_id == membership.membership_id
                    )
                )
            ).mappings().one()
            first = dict(first)

        receipt = CatalogueMembershipReceipt(
            membership.membership_id,
            run.ingestion_run_id,
            first["receipt_at"],
            ReceiptBasis.REPOSITORY_INSERT,
        )
        assert first["ingestion_run_id"] == run.ingestion_run_id
        assert first["receipt_basis"] == ReceiptBasis.REPOSITORY_INSERT.value
        assert first["bootstrap_revision"] is None
        assert first["canonical_payload_hash"] == receipt.canonical_payload_hash

        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogue_ingestions.add_memberships((membership,))
            await unit_of_work.commit()
        async with factory() as session:
            second = (
                await session.execute(
                    select(table).where(
                        table.c.membership_id == membership.membership_id
                    )
                )
            ).mappings().one()
        assert dict(second) == first
    finally:
        await dispose_database_engine(engine)
