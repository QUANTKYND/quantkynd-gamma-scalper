import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import BigInteger, LargeBinary, UniqueConstraint
from app.persistence.postgres.base import Base

from app.market_data.persistence.errors import (
    MarketEventDurableCorruptionError,
)

from app.persistence.postgres.repositories import (
    EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    PostgresMarketEventRepository,
    _rows_match_on_fields,
)


from app.market_data.persistence.contracts import (
    CANONICAL_IMPLEMENTATION,
    DATA14_ADVISORY_LOCK_NAMESPACE,
    DurableResultIdentity,
    QueryCursor,
)
from app.market_data.persistence.planner import derive_lock_stripes, lock_stripe, plan_parameter_chunks

REMOVED_PLACEHOLDER_METHODS = (
    "insert_or_compare_raw_frame",
    "insert_or_compare_normalization_result",
    "insert_or_compare_market_observations",
    "insert_or_compare_quote_observations",
    "insert_or_compare_failures",
    "insert_result_event_memberships",
    "insert_result_failure_memberships",
)


class _FakeRow:
    def __init__(self, values: dict[str, object]) -> None:
        self._mapping = values


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> list[_FakeRow]:
        self.calls.append(dict(parameters))
        return [
            _FakeRow(
                {
                    "id": identifier,
                    "payload": {"id": identifier},
                }
            )
            for identifier in parameters.values()
        ]


class _DuplicateDurableKeySession(_RecordingSession):
    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> list[_FakeRow]:
        rows = await super().execute(statement, parameters)

        if len(self.calls) == 2:
            rows.append(
                _FakeRow(
                    {
                        "id": "event-0",
                        "payload": {"id": "event-0"},
                    }
                )
            )

        return rows


def test_data14_namespace_derivation() -> None:
    digest = hashlib.sha256(b"quantkynd:data14:advisory-lock-namespace:v1").digest()
    assert int.from_bytes(digest[:4], "big", signed=True) == DATA14_ADVISORY_LOCK_NAMESPACE
    assert DATA14_ADVISORY_LOCK_NAMESPACE == -1377601296


def test_result_identity_excludes_implementation_evidence() -> None:
    identity = DurableResultIdentity("sha256:" + "1" * 64)
    assert identity.normalizer_implementation_version == CANONICAL_IMPLEMENTATION
    assert identity.result_id == DurableResultIdentity(identity.raw_event_id).result_id
    with pytest.raises(ValueError):
        DurableResultIdentity(identity.raw_event_id, normalizer_implementation_version="other")


def test_cursor_requires_supported_schema() -> None:
    assert QueryCursor(1).schema_version == 1
    with pytest.raises(ValueError):
        QueryCursor(2)


def test_lock_stripes_are_stable_unique_and_sorted() -> None:
    roots = tuple(("event", f"sha256:{value:064x}") for value in range(5000))
    stripes = derive_lock_stripes(roots + roots)
    assert stripes == tuple(sorted(set(stripes)))
    assert len(stripes) <= 64
    assert lock_stripe("event", "sha256:" + "0" * 64) == 63


def test_parameter_chunks_obey_budget_and_thousand_row_cap() -> None:
    chunks = plan_parameter_chunks(5000, 61)
    assert chunks[0].size == 983
    assert sum(chunk.size for chunk in chunks) == 5000
    assert all(chunk.size <= 1000 and chunk.size * 61 <= 60000 for chunk in chunks)
    assert plan_parameter_chunks(5000, 1)[0].size == 1000
    assert plan_parameter_chunks(0, 1) == ()


def test_exact_event_membership_retry_ignores_created_at() -> None:
    existing = {
        "id": "result:event:0",
        "result_id": "result",
        "raw_event_id": "raw",
        "event_id": "event",
        "event_ordinal": 0,
    }
    proposed = {
        **existing,
        "created_at": datetime(2026, 8, 5, tzinfo=UTC),
    }

    assert _rows_match_on_fields(
        existing,
        proposed,
        EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    )

    changed = {**proposed, "event_ordinal": 1}
    assert not _rows_match_on_fields(
        existing,
        changed,
        EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    )


def test_exact_failure_membership_retry_ignores_created_at() -> None:
    existing = {
        "id": "result:entry:0",
        "result_id": "result",
        "raw_event_id": "raw",
        "failure_id": "failure",
        "failure_role": "entry",
        "failure_ordinal": 0,
    }
    proposed = {
        **existing,
        "created_at": datetime(2026, 8, 5, tzinfo=UTC),
    }

    assert _rows_match_on_fields(
        existing,
        proposed,
        FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    )

    changed = {**proposed, "failure_role": "frame"}
    assert not _rows_match_on_fields(
        existing,
        changed,
        FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    )


@pytest.mark.anyio
async def test_existing_row_prefetch_chunks_five_thousand_ids() -> None:
    session = _RecordingSession()
    repository = PostgresMarketEventRepository(
        session,
        require_active=lambda: None,
    )
    identifiers = tuple(
        f"event-{index}"
        for index in range(5_000)
    )

    rows = await repository._fetch_existing_rows(
        "market_observations",
        "id",
        identifiers,
        ("id", "payload"),
    )

    assert len(rows) == 5_000
    assert len(session.calls) == 5
    assert [len(call) for call in session.calls] == [
        1_000,
        1_000,
        1_000,
        1_000,
        1_000,
    ]
    assert all(len(call) <= 1_000 for call in session.calls)


@pytest.mark.anyio
async def test_existing_row_prefetch_deduplicates_requested_ids() -> None:
    session = _RecordingSession()
    repository = PostgresMarketEventRepository(
        session,
        require_active=lambda: None,
    )

    rows = await repository._fetch_existing_rows(
        "market_observations",
        "id",
        ("event-0", "event-0", "event-1"),
        ("id", "payload"),
    )

    assert set(rows) == {"event-0", "event-1"}
    assert len(session.calls) == 1
    assert len(session.calls[0]) == 2


@pytest.mark.anyio
async def test_existing_row_prefetch_rejects_duplicate_durable_key() -> None:
    session = _DuplicateDurableKeySession()
    repository = PostgresMarketEventRepository(
        session,
        require_active=lambda: None,
    )
    identifiers = tuple(
        f"event-{index}"
        for index in range(1_001)
    )

    with pytest.raises(
        MarketEventDurableCorruptionError,
        match="duplicate durable key",
    ):
        await repository._fetch_existing_rows(
            "market_observations",
            "id",
            identifiers,
            ("id", "payload"),
        )

    assert len(session.calls) == 2


def test_market_event_repository_does_not_expose_placeholder_writes() -> None:
    repository = PostgresMarketEventRepository(
        session=object(),
        require_active=lambda: None,
    )

    assert all(
        not hasattr(repository, method_name)
        for method_name in REMOVED_PLACEHOLDER_METHODS
    )
    assert callable(repository.persist_frame_result)


def test_raw_market_frames_metadata_uses_durable_identity() -> None:
    table = Base.metadata.tables["raw_market_frames"]

    assert tuple(table.primary_key.columns.keys()) == (
        "raw_event_id",
    )
    assert "id" not in table.c
    assert "created_at" not in table.c
    assert "persistence_recorded_at" in table.c
    assert isinstance(table.c.source_order.type, BigInteger)
    assert isinstance(table.c.frame_bytes.type, LargeBinary)

    expected_columns = {
        "raw_event_id",
        "provider",
        "provider_schema_id",
        "provider_schema_sha256",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
        "frame_bytes",
        "frame_content_hash",
        "received_at",
        "available_at",
        "recorded_at",
        "capture_basis",
        "source_file_id",
        "source_record_id",
        "persistence_recorded_at",
    }

    assert set(table.c.keys()) == expected_columns

    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "provider",
        "provider_schema_id",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
    ) in unique_columns