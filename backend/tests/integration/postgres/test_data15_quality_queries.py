from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.core.hashing import stable_hash
from app.market_data.quality.ports import (
    ConnectionScope,
    InstrumentScope,
    SegmentScope,
    SubscriptionScope,
)
from app.persistence.postgres.base import Base
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


@pytest.mark.anyio
async def test_temporal_candidate_query_uses_record_and_receipt_cutoffs(
    reset_postgres_url: str,
    postgres_settings,
) -> None:
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    fixture = deterministic_fixture()
    try:
        await seed_fixture(PostgresUnitOfWork(factory), fixture)
        receipt_table = Base.metadata.tables[
            "market_data_quality_instrument_version_receipts"
        ]
        record_table = Base.metadata.tables["instrument_version_records"]
        async with factory() as session:
            first_receipt = await session.scalar(
                select(receipt_table.c.receipt_at)
                .join(
                    record_table,
                    record_table.c.record_id == receipt_table.c.record_id,
                )
                .where(
                    record_table.c.version_id
                    == fixture.option_version.version_id
                )
            )
        assert first_receipt is not None

        later = replace(
            fixture.option_version,
            recorded_at=fixture.option_version.recorded_at
            + timedelta(minutes=1),
        )
        async with PostgresUnitOfWork(factory) as unit_of_work:
            predecessor = await unit_of_work.instruments.resolve_version_state(
                fixture.option.contract_id,
                fixture.option_version.valid_from,
                None,
            )
            assert predecessor is not None
            second_record_id = await unit_of_work.instruments.add_version(
                later,
                predecessor.record_id,
            )
            await unit_of_work.commit()

        async with factory() as session:
            second_receipt = await session.scalar(
                select(receipt_table.c.receipt_at).where(
                    receipt_table.c.record_id == second_record_id
                )
            )
        assert second_receipt is not None
        assert second_receipt >= first_receipt

        market = fixture.option_version.valid_from
        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            before = await unit_of_work.market_data_quality.list_instrument_version_candidates(
                InstrumentScope(fixture.option.contract_id),
                market,
                first_receipt,
            )
        assert len(before.candidates) == 1
        assert before.candidates[0].candidate.record_id != second_record_id

        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            after = await unit_of_work.market_data_quality.list_instrument_version_candidates(
                InstrumentScope(fixture.option.contract_id),
                market,
                second_receipt,
            )
        assert {item.candidate.record_id for item in after.candidates} == {
            before.candidates[0].candidate.record_id,
            second_record_id,
        }
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_visible_target_and_status_candidates_hide_future_result_persistence(
    reset_postgres_url: str,
    postgres_settings,
) -> None:
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    at = datetime(2026, 8, 8, 4, 0, tzinfo=UTC)
    persistence_at = at + timedelta(seconds=1)
    event_id = stable_hash({"fixture": "data15-visible-status-event"})
    raw_event_id = stable_hash({"fixture": "data15-visible-status-raw"})
    result_id = stable_hash({"fixture": "data15-visible-status-result"})
    segment = "NSE_FO"
    tables = Base.metadata.tables
    try:
        async with engine.begin() as connection:
            await connection.execute(
                tables["raw_market_frames"].insert().values(
                    raw_event_id=raw_event_id,
                    provider="upstox",
                    provider_schema_id="data15-fixture-schema",
                    provider_schema_sha256="a" * 64,
                    connection_session_id="data15-status-connection",
                    source_order_scope_id="data15-status-source",
                    source_order=0,
                    frame_bytes=b"x",
                    frame_content_hash=stable_hash(
                        {"fixture": "data15-status-frame"}
                    ),
                    received_at=None,
                    available_at=at,
                    recorded_at=at,
                    capture_basis="historical_import",
                    source_file_id=None,
                    source_record_id=None,
                    persistence_recorded_at=persistence_at,
                )
            )
            await connection.execute(
                tables["market_normalization_results"].insert().values(
                    result_id=result_id,
                    raw_event_id=raw_event_id,
                    normalization_schema_version=1,
                    normalizer_implementation_version="upstox-v3-normalizer-1",
                    response_type="market_info",
                    status="complete",
                    decoded_entry_count=1,
                    accepted_entry_count=1,
                    failed_entry_count=0,
                    frame_failure_present=False,
                    unadopted_schema_paths=[],
                    present_unadopted_message_paths=[],
                    secondary_payload_paths_present=[],
                    full_result_hash=stable_hash(
                        {"fixture": "data15-status-full-result"}
                    ),
                    adopted_semantics_hash=stable_hash(
                        {"fixture": "data15-status-adopted"}
                    ),
                    metadata_payload={},
                    persistence_recorded_at=persistence_at,
                )
            )
            await connection.execute(
                tables["market_observations"].insert().values(
                    event_id=event_id,
                    raw_event_id=raw_event_id,
                    event_type="market_segment_status_observation",
                    subject_id=stable_hash(
                        {
                            "entity": "provider_market_segment",
                            "provider": "upstox",
                            "segment": segment,
                        }
                    ),
                    provider="upstox",
                    provider_contract_key=None,
                    economic_subject_id=None,
                    provider_mapping_id=None,
                    contract_version_id=None,
                    catalogue_version_id=None,
                    provider_mapping_record_id=None,
                    contract_version_record_id=None,
                    catalogue_version_record_id=None,
                    resolution_market_as_of=None,
                    resolution_known_as_of=None,
                    provider_timestamp=at,
                    exchange_timestamp=None,
                    received_at=None,
                    available_at=at,
                    recorded_at=at,
                    availability_basis="historical_import",
                    source_order_scope_id="data15-status-source",
                    source_order=0,
                    normalization_schema_version=1,
                    normalizer_implementation_version="upstox-v3-normalizer-1",
                    provider_sequence=None,
                    supersedes_event_id=None,
                    payload={},
                )
            )
            await connection.execute(
                tables["market_segment_status_observations"].insert().values(
                    event_id=event_id,
                    event_type="market_segment_status_observation",
                    subject_id=stable_hash(
                        {
                            "entity": "provider_market_segment",
                            "provider": "upstox",
                            "segment": segment,
                        }
                    ),
                    segment=segment,
                    provider_status_name="NORMAL_OPEN",
                    provider_status_numeric=2,
                    status_is_known=True,
                )
            )
            await connection.execute(
                tables["market_normalization_result_events"].insert().values(
                    result_id=result_id,
                    raw_event_id=raw_event_id,
                    event_ordinal=0,
                    event_id=event_id,
                )
            )
            await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            hidden = await unit_of_work.market_data_quality.load_visible_targets(
                (event_id,),
                persistence_at - timedelta(microseconds=1),
            )
            hidden_status = await unit_of_work.market_data_quality.list_segment_status_candidates(
                SegmentScope("upstox", segment),
                at,
                persistence_at - timedelta(microseconds=1),
            )
        assert hidden.hidden_event_ids == (event_id,)
        assert not hidden.targets
        assert not hidden_status.candidates

        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            visible = await unit_of_work.market_data_quality.load_visible_targets(
                (event_id,), persistence_at
            )
            status = await unit_of_work.market_data_quality.list_segment_status_candidates(
                SegmentScope("upstox", segment), at, persistence_at
            )
        assert visible.is_complete
        assert visible.targets[0].event_id == event_id
        assert len(status.candidates) == 1
        assert status.candidates[0].candidate_id == event_id
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_lifecycle_candidates_require_visible_owning_batch(
    reset_postgres_url: str,
    postgres_settings,
) -> None:
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    at = datetime(2026, 8, 8, 5, 0, tzinfo=UTC)
    persistence_at = at + timedelta(seconds=1)
    provider_key = "NSE_FO|DATA15"
    connection_id = "data15-lifecycle-connection"
    source_scope = "data15-lifecycle-source"
    tables = Base.metadata.tables

    instrument_keys_digest = stable_hash(
        {
            "entity": "provider_subscription_instrument_keys_v1",
            "provider_contract_keys": (provider_key,),
        }
    )

    async def insert_lifecycle(
        connection,
        *,
        kind: str,
        marker: str,
        source_order: int,
    ) -> str:
        batch_id = stable_hash({"fixture": f"data15-{kind}-batch-{marker}"})
        raw_event_id = stable_hash({"fixture": f"data15-{kind}-raw-{marker}"})
        event_id = stable_hash({"fixture": f"data15-{kind}-event-{marker}"})
        subscription_scope_id = (
            "data15-subscription-scope" if kind == "subscription" else None
        )
        subject_id = (
            stable_hash(
                {
                    "entity": "provider_subscription",
                    "provider": "upstox",
                    "connection_session_id": connection_id,
                    "subscription_scope_id": subscription_scope_id,
                }
            )
            if kind == "subscription"
            else connection_id
        )
        previous_state = (
            "subscribe_requested" if kind == "subscription" else "connected"
        )
        state = "subscribed" if kind == "subscription" else "authorized"
        event_type = (
            "provider_subscription_lifecycle_observation"
            if kind == "subscription"
            else "provider_connection_lifecycle_observation"
        )

        await connection.execute(
            tables["provider_lifecycle_batches"].insert().values(
                lifecycle_batch_id=batch_id,
                lifecycle_kind=kind,
                provider="upstox",
                normalization_schema_version=1,
                normalizer_implementation_version="upstox-v3-normalizer-1",
                input_count=1,
                unique_count=1,
                normalized_count=1,
                duplicate_count=0,
                batch_hash=stable_hash({"fixture": f"batch-hash-{marker}"}),
                normalized_sequence_hash=stable_hash(
                    {"fixture": f"sequence-hash-{marker}"}
                ),
                metadata_payload={},
                persistence_recorded_at=persistence_at,
            )
        )
        await connection.execute(
            tables["raw_provider_lifecycle_events"].insert().values(
                raw_event_id=raw_event_id,
                lifecycle_kind=kind,
                provider="upstox",
                connection_session_id=connection_id,
                subscription_scope_id=subscription_scope_id,
                previous_state=previous_state,
                state=state,
                source_order_scope_id=source_scope,
                source_order=source_order,
                occurred_at=at,
                available_at=at,
                recorded_at=at,
                request_mode="ltpc" if kind == "subscription" else None,
                instrument_keys_digest=(
                    instrument_keys_digest if kind == "subscription" else None
                ),
                instrument_key_count=1 if kind == "subscription" else None,
                redacted_reason_code=None,
                provider_sequence=None,
                payload={},
            )
        )
        await connection.execute(
            tables["provider_lifecycle_batch_events"].insert().values(
                lifecycle_batch_id=batch_id,
                lifecycle_kind=kind,
                input_ordinal=0,
                raw_event_id=raw_event_id,
                is_exact_duplicate=False,
                first_occurrence_ordinal=0,
            )
        )
        await connection.execute(
            tables["provider_lifecycle_observations"].insert().values(
                event_id=event_id,
                raw_event_id=raw_event_id,
                event_type=event_type,
                subject_id=subject_id,
                lifecycle_kind=kind,
                provider="upstox",
                connection_session_id=connection_id,
                source_order_scope_id=source_scope,
                source_order=source_order,
                occurred_at=at,
                available_at=at,
                recorded_at=at,
                normalization_schema_version=1,
                normalizer_implementation_version="upstox-v3-normalizer-1",
                provider_sequence=None,
                payload={},
            )
        )
        subtype_values = {
            "event_id": event_id,
            "event_type": event_type,
            "subject_id": subject_id,
            "lifecycle_kind": kind,
            "connection_session_id": connection_id,
            "previous_state": previous_state,
            "state": state,
            "redacted_reason_code": None,
        }
        if kind == "subscription":
            subtype_values.update(
                {
                    "subscription_scope_id": subscription_scope_id,
                    "request_mode": "ltpc",
                    "instrument_keys_digest": instrument_keys_digest,
                    "instrument_key_count": 1,
                }
            )
        await connection.execute(
            tables[
                "provider_subscription_lifecycle_observations"
                if kind == "subscription"
                else "provider_connection_lifecycle_observations"
            ].insert().values(**subtype_values)
        )
        await connection.execute(
            tables["provider_lifecycle_batch_observations"].insert().values(
                lifecycle_batch_id=batch_id,
                lifecycle_kind=kind,
                event_ordinal=0,
                event_id=event_id,
            )
        )
        return event_id

    try:
        async with engine.begin() as connection:
            await connection.execute(
                tables["provider_subscription_instrument_sets"].insert().values(
                    instrument_keys_digest=instrument_keys_digest,
                    instrument_key_count=1,
                    provider_contract_keys=[provider_key],
                    canonical_payload_hash=instrument_keys_digest,
                )
            )
            await connection.execute(
                tables["provider_subscription_instrument_set_keys"].insert().values(
                    instrument_keys_digest=instrument_keys_digest,
                    key_ordinal=0,
                    provider_contract_key=provider_key,
                )
            )
            connection_event_id = await insert_lifecycle(
                connection, kind="connection", marker="one", source_order=0
            )
            subscription_event_id = await insert_lifecycle(
                connection, kind="subscription", marker="two", source_order=1
            )
            await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            hidden_connection = await unit_of_work.market_data_quality.list_connection_candidates(
                ConnectionScope("upstox", connection_id),
                at,
                persistence_at - timedelta(microseconds=1),
            )
            hidden_subscription = await unit_of_work.market_data_quality.list_subscription_scope_candidates(
                SubscriptionScope(
                    "upstox", connection_id, provider_key, "ltpc"
                ),
                at,
                persistence_at - timedelta(microseconds=1),
            )
        assert not hidden_connection.candidates
        assert not hidden_subscription.candidates

        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            connection = await unit_of_work.market_data_quality.list_connection_candidates(
                ConnectionScope("upstox", connection_id), at, persistence_at
            )
            subscription = await unit_of_work.market_data_quality.list_subscription_scope_candidates(
                SubscriptionScope(
                    "upstox", connection_id, provider_key, "ltpc"
                ),
                at,
                persistence_at,
            )
        assert connection.candidates[0].candidate_id == connection_event_id
        assert subscription.candidates[0].candidate_id == subscription_event_id
        assert subscription.candidates[0].candidate.payload["contains_target_key"] is True
    finally:
        await dispose_database_engine(engine)
