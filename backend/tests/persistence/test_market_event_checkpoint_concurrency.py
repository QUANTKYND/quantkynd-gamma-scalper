import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database_config import DatabaseSettings
from app.market_data.persistence.contracts import (
    CANONICAL_IMPLEMENTATION,
    DATA14_ADVISORY_LOCK_NAMESPACE,
)
from app.market_data.persistence.errors import (
    NormalizedEventIdentityConflictError,
    RawCaptureIdentityConflictError,
    RawFrameContentMismatchError,
)
from app.market_data.persistence.planner import derive_lock_stripes
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.repositories import (
    PostgresMarketEventRepository,
)


class _EventIdentity(BaseModel):
    event_type: str
    subject_id: str


class _StatusEvent(BaseModel):
    event_id: str
    raw_event_id: str
    identity: _EventIdentity
    provider: str
    provider_timestamp: datetime
    received_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    source_order_scope_id: str
    source_order: int
    normalization_schema_version: int
    normalizer_implementation_version: str
    segment: str
    provider_status_name: str
    provider_status_numeric: int
    status_is_known: bool


def _sha(marker: str) -> str:
    return "sha256:" + marker * 64


def _command(
    *,
    raw_marker: str,
    event_marker: str,
    source_order: int,
    frame_bytes: bytes = b"x",
    provider_schema_id: str = "fixture-schema",
    status_name: str = "NORMAL_OPEN",
    status_numeric: int = 2,
):
    when = datetime(2026, 8, 6, 3, 45, tzinfo=UTC)
    raw_event_id = _sha(raw_marker)
    event = _StatusEvent(
        event_id=_sha(event_marker),
        raw_event_id=raw_event_id,
        identity=_EventIdentity(
            event_type="market_segment_status_observation",
            subject_id=_sha("9"),
        ),
        provider="upstox",
        provider_timestamp=when,
        received_at=None,
        available_at=when,
        recorded_at=when,
        source_order_scope_id="checkpoint-scope",
        source_order=source_order,
        normalization_schema_version=1,
        normalizer_implementation_version=(
            CANONICAL_IMPLEMENTATION
        ),
        segment="NSE_FO",
        provider_status_name=status_name,
        provider_status_numeric=status_numeric,
        status_is_known=True,
    )
    raw = SimpleNamespace(
        raw_event_id=raw_event_id,
        provider="upstox",
        provider_schema_id=provider_schema_id,
        provider_schema_sha256="a" * 64,
        connection_session_id="checkpoint-session",
        source_order_scope_id="checkpoint-scope",
        source_order=source_order,
        frame_bytes=frame_bytes,
        frame_content_hash=(
            "sha256:"
            + hashlib.sha256(frame_bytes).hexdigest()
        ),
        received_at=None,
        available_at=when,
        recorded_at=when,
        capture_basis=SimpleNamespace(
            value="historical_import"
        ),
        source_file_id=None,
        source_record_id=None,
    )
    result = SimpleNamespace(
        raw_frame_identity=SimpleNamespace(
            raw_event_id=raw_event_id
        ),
        accepted_events=(event,),
        frame_failure=None,
        entry_failures=(),
        response_type="live_feed",
        status="complete",
        decoded_entry_count=1,
        accepted_entry_count=1,
        failed_entry_count=0,
        unadopted_schema_paths=(),
        present_unadopted_message_paths=(),
        secondary_payload_paths_present=(),
        full_result_hash=_sha("7"),
        adopted_semantics_hash=_sha("8"),
    )
    return SimpleNamespace(
        raw_frame=raw,
        normalization_result=result,
        market_as_of=when,
        known_as_of=when,
    )


async def _wait_for_advisory_wait(
    engine,
    backend_pid: int,
    *,
    timeout: float = 5.0,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        async with engine.connect() as connection:
            wait_event = await connection.scalar(
                text(
                    "SELECT wait_event "
                    "FROM pg_stat_activity "
                    "WHERE pid = :pid"
                ),
                {"pid": backend_pid},
            )
        if wait_event == "advisory":
            return
        await asyncio.sleep(0.01)

    raise AssertionError(
        "second persistence transaction did not wait "
        "on a DATA-1.4 advisory lock"
    )


async def _table_count(engine, table_name: str) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                text(f"SELECT count(*) FROM {table_name}")
            )
        )


@pytest.mark.anyio
async def test_concurrent_exact_retry_serializes_and_is_idempotent(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    del reset_postgres_url
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    command = _command(
        raw_marker="1",
        event_marker="2",
        source_order=0,
    )

    first_session = factory()
    first_transaction = await first_session.begin()
    try:
        first_repository = PostgresMarketEventRepository(
            first_session,
            require_active=lambda: None,
        )
        first_summary = await first_repository.persist_frame_result(
            command
        )
        assert first_summary.inserted is True

        pid_ready = asyncio.get_running_loop().create_future()

        async def retry():
            async with factory() as session:
                async with session.begin():
                    pid = await session.scalar(
                        text("SELECT pg_backend_pid()")
                    )
                    pid_ready.set_result(int(pid))
                    repository = PostgresMarketEventRepository(
                        session,
                        require_active=lambda: None,
                    )
                    return await repository.persist_frame_result(
                        command
                    )

        retry_task = asyncio.create_task(retry())
        retry_pid = await asyncio.wait_for(pid_ready, timeout=2)
        await _wait_for_advisory_wait(engine, retry_pid)
        await first_transaction.commit()

        retry_summary = await asyncio.wait_for(
            retry_task,
            timeout=5,
        )
        assert retry_summary.inserted is False
        assert await _table_count(
            engine,
            "raw_market_frames",
        ) == 1
        assert await _table_count(
            engine,
            "market_normalization_results",
        ) == 1
        assert await _table_count(
            engine,
            "market_observations",
        ) == 1
    finally:
        if first_transaction.is_active:
            await first_transaction.rollback()
        await first_session.close()
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_concurrent_raw_content_collision_is_named_and_atomic(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    del reset_postgres_url
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    first = _command(
        raw_marker="3",
        event_marker="4",
        source_order=0,
        frame_bytes=b"first",
    )
    conflicting = _command(
        raw_marker="3",
        event_marker="4",
        source_order=0,
        frame_bytes=b"second",
    )

    try:
        async with factory() as session:
            async with session.begin():
                repository = PostgresMarketEventRepository(
                    session,
                    require_active=lambda: None,
                )
                await repository.persist_frame_result(first)

        async with factory() as session:
            with pytest.raises(RawFrameContentMismatchError):
                async with session.begin():
                    repository = PostgresMarketEventRepository(
                        session,
                        require_active=lambda: None,
                    )
                    await repository.persist_frame_result(
                        conflicting
                    )

        assert await _table_count(
            engine,
            "raw_market_frames",
        ) == 1
        assert await _table_count(
            engine,
            "market_normalization_results",
        ) == 1
        assert await _table_count(
            engine,
            "market_observations",
        ) == 1
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_capture_identity_collision_uses_named_error(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    del reset_postgres_url
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    first = _command(
        raw_marker="5",
        event_marker="6",
        source_order=0,
    )
    conflicting = _command(
        raw_marker="7",
        event_marker="8",
        source_order=0,
    )

    try:
        async with factory() as session:
            async with session.begin():
                repository = PostgresMarketEventRepository(
                    session,
                    require_active=lambda: None,
                )
                await repository.persist_frame_result(first)

        async with factory() as session:
            with pytest.raises(RawCaptureIdentityConflictError):
                async with session.begin():
                    repository = PostgresMarketEventRepository(
                        session,
                        require_active=lambda: None,
                    )
                    await repository.persist_frame_result(
                        conflicting
                    )

        assert await _table_count(
            engine,
            "raw_market_frames",
        ) == 1
        assert await _table_count(
            engine,
            "market_normalization_results",
        ) == 1
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_shared_event_changed_content_fails_without_deadlock(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    del reset_postgres_url
    engine = create_database_engine(postgres_settings)
    factory = create_session_factory(engine)
    first = _command(
        raw_marker="a",
        event_marker="c",
        source_order=0,
        status_name="NORMAL_OPEN",
        status_numeric=2,
    )
    conflicting = _command(
        raw_marker="b",
        event_marker="c",
        source_order=1,
        status_name="NORMAL_CLOSE",
        status_numeric=3,
    )

    try:
        async with factory() as session:
            async with session.begin():
                repository = PostgresMarketEventRepository(
                    session,
                    require_active=lambda: None,
                )
                await repository.persist_frame_result(first)

        async def persist_conflict() -> None:
            async with factory() as session:
                async with session.begin():
                    repository = PostgresMarketEventRepository(
                        session,
                        require_active=lambda: None,
                    )
                    await repository.persist_frame_result(
                        conflicting
                    )

        with pytest.raises(NormalizedEventIdentityConflictError):
            await asyncio.wait_for(
                persist_conflict(),
                timeout=5,
            )
    finally:
        await dispose_database_engine(engine)


@pytest.mark.anyio
async def test_boundary_lock_count_is_measured_and_bounded(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
) -> None:
    del reset_postgres_url
    engine = create_database_engine(postgres_settings)
    roots = tuple(
        ("market_observation", f"sha256:{index:064x}")
        for index in range(10_000)
    )
    stripes = derive_lock_stripes(roots)

    try:
        async with engine.begin() as connection:
            max_locks = int(
                await connection.scalar(
                    text("SHOW max_locks_per_transaction")
                )
            )
            backend_pid = int(
                await connection.scalar(
                    text("SELECT pg_backend_pid()")
                )
            )

            for stripe in stripes:
                await connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "CAST(:namespace AS integer), "
                        "CAST(:stripe AS integer)"
                        ")"
                    ),
                    {
                        "namespace": (
                            DATA14_ADVISORY_LOCK_NAMESPACE
                        ),
                        "stripe": stripe,
                    },
                )

            measured = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) "
                        "FROM pg_locks "
                        "WHERE pid = :pid "
                        "AND locktype = 'advisory' "
                        "AND granted"
                    ),
                    {"pid": backend_pid},
                )
            )

            assert max_locks > 0
            assert measured == len(stripes)
            assert measured <= 64
    finally:
        await dispose_database_engine(engine)
