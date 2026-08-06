import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.market_data.persistence.contracts import (
    CANONICAL_IMPLEMENTATION,
    DATA14_ADVISORY_LOCK_NAMESPACE,
    DurableResultIdentity,
    QueryCursor,
)
from app.market_data.persistence.errors import (
    CatalogueProvenanceConflictError,
    MarketEventDurableCorruptionError,
    MarketEventReferentialIntegrityError,
    PersistenceTimeBindingError,
)
from app.market_data.persistence.planner import (
    derive_lock_stripes,
    lock_stripe,
    plan_parameter_chunks,
)
from app.persistence.postgres.base import Base
from app.persistence.postgres.repositories import (
    EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    OBSERVATION_IMMUTABLE_FIELDS,
    QUOTE_SUBTYPE_IMMUTABLE_FIELDS,
    STATUS_SUBTYPE_IMMUTABLE_FIELDS,
    PostgresMarketEventRepository,
    _rows_match_on_fields,
)


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
    def __init__(
        self,
        values: dict[str, object],
    ) -> None:
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
                    "payload": {
                        "id": identifier,
                    },
                }
            )
            for identifier in parameters.values()
        ]


class _AggregateResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _AggregateSession:
    def __init__(self, event_row):
        self.event_row = event_row

    async def execute(self, statement, parameters):
        sql = str(statement)
        if "FROM market_normalization_result_events AS m" in sql:
            return _AggregateResult([self.event_row])
        if "FROM market_normalization_result_failures AS m" in sql:
            return _AggregateResult([])
        raise AssertionError(f"unexpected aggregate query: {sql}")


class _AggregateRepository(PostgresMarketEventRepository):
    def __init__(self, session, result, raw_frame, subtype):
        super().__init__(session, require_active=lambda: None)
        self._result = result
        self._raw_frame = raw_frame
        self._subtype = subtype

    async def get_result(
        self,
        raw_event_id,
        normalization_schema_version,
    ):
        return self._result

    async def get_raw_frame(self, raw_event_id):
        return self._raw_frame

    async def _fetch_existing_rows(
        self,
        table,
        key_name,
        identifiers,
        fields,
    ):
        assert table == "option_quote_observations"
        assert key_name == "event_id"
        assert identifiers == (self._subtype["event_id"],)
        return {self._subtype["event_id"]: self._subtype}


class _DuplicateDurableKeySession(
    _RecordingSession
):
    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> list[_FakeRow]:
        rows = await super().execute(
            statement,
            parameters,
        )

        if len(self.calls) == 2:
            rows.append(
                _FakeRow(
                    {
                        "id": "event-0",
                        "payload": {
                            "id": "event-0",
                        },
                    }
                )
            )

        return rows


@pytest.mark.anyio
async def test_load_result_aggregate_returns_complete_typed_frame() -> None:
    raw_event_id = "sha256:" + "1" * 64
    result_id = "sha256:" + "2" * 64
    event_id = "sha256:" + "3" * 64
    mapping_record_id = "sha256:" + "4" * 64
    version_record_id = "sha256:" + "5" * 64
    catalogue_record_id = "sha256:" + "6" * 64

    result = SimpleNamespace(
        result_id=result_id,
        raw_event_id=raw_event_id,
        accepted_entry_count=1,
        failed_entry_count=0,
        frame_failure_present=False,
    )
    raw_frame = SimpleNamespace(raw_event_id=raw_event_id)
    event_row = _FakeRow(
        {
            "event_ordinal": 0,
            "event_id": event_id,
            "event_type": "option_quote_observation",
            "provider_mapping_record_id": mapping_record_id,
            "contract_version_record_id": version_record_id,
            "catalogue_version_record_id": catalogue_record_id,
        }
    )
    subtype = {
        field: None
        for field in QUOTE_SUBTYPE_IMMUTABLE_FIELDS
    }
    subtype.update(
        {
            "event_id": event_id,
            "event_type": "option_quote_observation",
            "subject_id": "sha256:" + "7" * 64,
        }
    )
    repository = _AggregateRepository(
        _AggregateSession(event_row),
        result,
        raw_frame,
        subtype,
    )

    aggregate = await repository.load_result_aggregate(
        raw_event_id,
        1,
    )

    assert aggregate["raw_frame"] is raw_frame
    assert aggregate["result"] is result
    assert aggregate["events"][0][
        "provider_mapping_record_id"
    ] == mapping_record_id
    assert aggregate["events"][0][
        "contract_version_record_id"
    ] == version_record_id
    assert aggregate["events"][0][
        "catalogue_version_record_id"
    ] == catalogue_record_id
    assert aggregate["subtypes"][0]["table"] == (
        "option_quote_observations"
    )
    assert aggregate["subtypes"][0]["event_id"] == event_id
    assert aggregate["failures"] == ()


def test_data14_namespace_derivation() -> None:
    digest = hashlib.sha256(
        b"quantkynd:data14:"
        b"advisory-lock-namespace:v1"
    ).digest()

    assert (
        int.from_bytes(
            digest[:4],
            "big",
            signed=True,
        )
        == DATA14_ADVISORY_LOCK_NAMESPACE
    )
    assert (
        DATA14_ADVISORY_LOCK_NAMESPACE
        == -1377601296
    )


def test_result_identity_excludes_implementation_evidence() -> None:
    identity = DurableResultIdentity(
        "sha256:" + "1" * 64
    )

    assert (
        identity.normalizer_implementation_version
        == CANONICAL_IMPLEMENTATION
    )
    assert (
        identity.result_id
        == DurableResultIdentity(
            identity.raw_event_id
        ).result_id
    )

    with pytest.raises(ValueError):
        DurableResultIdentity(
            identity.raw_event_id,
            normalizer_implementation_version=(
                "other"
            ),
        )


def test_cursor_requires_supported_schema() -> None:
    assert QueryCursor(1).schema_version == 1

    with pytest.raises(ValueError):
        QueryCursor(2)


def test_lock_stripes_are_stable_unique_and_sorted() -> None:
    roots = tuple(
        (
            "event",
            f"sha256:{value:064x}",
        )
        for value in range(5000)
    )

    stripes = derive_lock_stripes(
        roots + roots
    )

    assert stripes == tuple(
        sorted(set(stripes))
    )
    assert len(stripes) <= 64
    assert (
        lock_stripe(
            "event",
            "sha256:" + "0" * 64,
        )
        == 63
    )


def test_parameter_chunks_obey_budget_and_thousand_row_cap() -> None:
    chunks = plan_parameter_chunks(
        5000,
        61,
    )

    assert chunks[0].size == 983
    assert (
        sum(
            chunk.size
            for chunk in chunks
        )
        == 5000
    )
    assert all(
        chunk.size <= 1000
        and chunk.size * 61 <= 60000
        for chunk in chunks
    )
    assert (
        plan_parameter_chunks(
            5000,
            1,
        )[0].size
        == 1000
    )
    assert (
        plan_parameter_chunks(
            0,
            1,
        )
        == ()
    )


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
        "created_at": datetime(
            2026,
            8,
            5,
            tzinfo=UTC,
        ),
    }

    assert _rows_match_on_fields(
        existing,
        proposed,
        EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    )

    changed = {
        **proposed,
        "event_ordinal": 1,
    }

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
        "created_at": datetime(
            2026,
            8,
            5,
            tzinfo=UTC,
        ),
    }

    assert _rows_match_on_fields(
        existing,
        proposed,
        FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    )

    changed = {
        **proposed,
        "failure_role": "frame",
    }

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
        (
            "id",
            "payload",
        ),
    )

    assert len(rows) == 5_000
    assert len(session.calls) == 5
    assert [
        len(call)
        for call in session.calls
    ] == [
        1_000,
        1_000,
        1_000,
        1_000,
        1_000,
    ]
    assert all(
        len(call) <= 1_000
        for call in session.calls
    )


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
        (
            "event-0",
            "event-0",
            "event-1",
        ),
        (
            "id",
            "payload",
        ),
    )

    assert set(rows) == {
        "event-0",
        "event-1",
    }
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
            (
                "id",
                "payload",
            ),
        )

    assert len(session.calls) == 2


def test_market_event_repository_does_not_expose_placeholder_writes() -> None:
    repository = PostgresMarketEventRepository(
        session=object(),
        require_active=lambda: None,
    )

    assert all(
        not hasattr(
            repository,
            method_name,
        )
        for method_name
        in REMOVED_PLACEHOLDER_METHODS
    )
    assert callable(
        repository.persist_frame_result
    )


def test_raw_market_frames_metadata_uses_durable_identity() -> None:
    table = Base.metadata.tables[
        "raw_market_frames"
    ]

    assert tuple(
        table.primary_key.columns.keys()
    ) == (
        "raw_event_id",
    )
    assert "id" not in table.c
    assert "created_at" not in table.c
    assert (
        "persistence_recorded_at"
        in table.c
    )
    assert isinstance(
        table.c.source_order.type,
        BigInteger,
    )
    assert isinstance(
        table.c.frame_bytes.type,
        LargeBinary,
    )

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

    assert (
        set(table.c.keys())
        == expected_columns
    )

    unique_columns = {
        tuple(
            constraint.columns.keys()
        )
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert (
        "provider",
        "provider_schema_id",
        "connection_session_id",
        "source_order_scope_id",
        "source_order",
    ) in unique_columns


def test_market_normalization_results_metadata_is_durable_root() -> None:
    table = Base.metadata.tables[
        "market_normalization_results"
    ]

    assert tuple(
        table.primary_key.columns.keys()
    ) == (
        "result_id",
    )
    assert "id" not in table.c
    assert "created_at" not in table.c

    assert set(table.c.keys()) == {
        "result_id",
        "raw_event_id",
        "normalization_schema_version",
        "normalizer_implementation_version",
        "response_type",
        "status",
        "decoded_entry_count",
        "accepted_entry_count",
        "failed_entry_count",
        "frame_failure_present",
        "unadopted_schema_paths",
        "present_unadopted_message_paths",
        "secondary_payload_paths_present",
        "full_result_hash",
        "adopted_semantics_hash",
        "metadata_payload",
        "persistence_recorded_at",
    }

    assert isinstance(
        table.c.frame_failure_present.type,
        Boolean,
    )
    assert isinstance(
        table.c.unadopted_schema_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.present_unadopted_message_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.secondary_payload_paths_present.type,
        ARRAY,
    )
    assert isinstance(
        table.c.metadata_payload.type,
        JSONB,
    )

    unique_columns = {
        tuple(
            constraint.columns.keys()
        )
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert (
        "raw_event_id",
        "normalization_schema_version",
    ) in unique_columns
    assert (
        "result_id",
        "raw_event_id",
    ) in unique_columns

    foreign_keys = {
        (
            tuple(
                constraint.column_keys
            ),
            tuple(
                element.target_fullname
                for element
                in constraint.elements
            ),
            tuple(
                element.ondelete
                for element
                in constraint.elements
            ),
        )
        for constraint in table.constraints
        if isinstance(
            constraint,
            ForeignKeyConstraint,
        )
    }

    assert (
        (
            "raw_event_id",
        ),
        (
            "raw_market_frames.raw_event_id",
        ),
        (
            "NO ACTION",
        ),
    ) in foreign_keys

    index_columns = {
        index.name: tuple(
            column.name
            for column
            in index.columns
        )
        for index in table.indexes
    }

    assert index_columns == {
        (
            "ix_market_normalization_results_"
            "schema_raw"
        ): (
            "normalization_schema_version",
            "raw_event_id",
        ),
        (
            "ix_market_normalization_results_"
            "persistence"
        ): (
            "normalization_schema_version",
            "persistence_recorded_at",
            "result_id",
        ),
        (
            "ix_market_normalization_results_"
            "status"
        ): (
            "normalization_schema_version",
            "status",
            "result_id",
        ),
    }


def _unique_column_shapes(table) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_shapes(
    table,
) -> set[
    tuple[
        tuple[str, ...],
        tuple[str, ...],
        tuple[str | None, ...],
    ]
]:
    return {
        (
            tuple(constraint.column_keys),
            tuple(
                element.target_fullname
                for element in constraint.elements
            ),
            tuple(
                element.ondelete
                for element in constraint.elements
            ),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _index_shapes(table) -> dict[str, tuple[str, ...]]:
    return {
        index.name: tuple(
            column.name
            for column in index.columns
        )
        for index in table.indexes
    }


def test_market_observations_metadata_is_explicit_registry() -> None:
    table = Base.metadata.tables[
        "market_observations"
    ]

    assert tuple(
        table.primary_key.columns.keys()
    ) == ("event_id",)
    assert "id" not in table.c
    assert "created_at" not in table.c

    assert set(table.c.keys()) == {
        "event_id",
        "raw_event_id",
        "event_type",
        "subject_id",
        "provider",
        "provider_contract_key",
        "economic_subject_id",
        "provider_mapping_id",
        "contract_version_id",
        "catalogue_version_id",
        "provider_mapping_record_id",
        "contract_version_record_id",
        "catalogue_version_record_id",
        "resolution_market_as_of",
        "resolution_known_as_of",
        "provider_timestamp",
        "exchange_timestamp",
        "received_at",
        "available_at",
        "recorded_at",
        "availability_basis",
        "source_order_scope_id",
        "source_order",
        "normalization_schema_version",
        "normalizer_implementation_version",
        "provider_sequence",
        "supersedes_event_id",
        "payload",
    }

    assert isinstance(
        table.c.source_order.type,
        BigInteger,
    )
    assert isinstance(
        table.c.payload.type,
        JSONB,
    )

    unique_columns = _unique_column_shapes(table)
    assert (
        "event_id",
        "raw_event_id",
    ) in unique_columns
    assert (
        "event_id",
        "event_type",
        "subject_id",
    ) in unique_columns

    foreign_keys = _foreign_key_shapes(table)
    assert (
        ("raw_event_id",),
        ("raw_market_frames.raw_event_id",),
        ("NO ACTION",),
    ) in foreign_keys
    assert (
        (
            "provider_mapping_record_id",
            "provider_mapping_id",
        ),
        (
            "provider_mapping_records.record_id",
            "provider_mapping_records.mapping_id",
        ),
        ("NO ACTION", "NO ACTION"),
    ) in foreign_keys
    assert (
        (
            "contract_version_record_id",
            "contract_version_id",
        ),
        (
            "instrument_version_records.record_id",
            "instrument_version_records.version_id",
        ),
        ("NO ACTION", "NO ACTION"),
    ) in foreign_keys
    assert (
        (
            "catalogue_version_record_id",
            "catalogue_version_id",
        ),
        (
            "catalogue_version_records.record_id",
            "catalogue_version_records.catalogue_version_id",
        ),
        ("NO ACTION", "NO ACTION"),
    ) in foreign_keys

    assert _index_shapes(table) == {
        "ix_market_observations_subject_provider_time": (
            "normalization_schema_version",
            "economic_subject_id",
            "event_type",
            "provider_timestamp",
            "available_at",
            "event_id",
        ),
        "ix_market_observations_subject_availability": (
            "normalization_schema_version",
            "economic_subject_id",
            "availability_basis",
            "available_at",
            "event_id",
        ),
        "ix_market_observations_raw": (
            "raw_event_id",
            "event_id",
        ),
        "ix_market_observations_mapping_provenance": (
            "provider_mapping_id",
            "contract_version_id",
            "catalogue_version_id",
            "event_id",
        ),
        "ix_market_observations_temporal_provenance": (
            "provider_mapping_record_id",
            "contract_version_record_id",
            "catalogue_version_record_id",
            "event_id",
        ),
    }


def test_temporal_record_targets_expose_composite_identity() -> None:
    expected = {
        "provider_mapping_records": "mapping_id",
        "instrument_version_records": "version_id",
        "catalogue_version_records": "catalogue_version_id",
    }

    for table_name, semantic_column in expected.items():
        table = Base.metadata.tables[table_name]
        assert (
            "record_id",
            semantic_column,
        ) in _unique_column_shapes(table)


def _provenance_binding_fixture():
    when = datetime(2026, 8, 5, 9, 15, tzinfo=UTC)
    mapping_id = "sha256:" + "1" * 64
    version_id = "sha256:" + "2" * 64
    catalogue_id = "sha256:" + "3" * 64
    subject_id = "sha256:" + "4" * 64

    mapping = SimpleNamespace(
        mapping_id=mapping_id,
        provider="upstox",
        provider_contract_key="NSE_FO|fixture",
        contract_version_id=version_id,
        effective_at=lambda market_as_of, known_as_of: True,
    )
    version = SimpleNamespace(
        version_id=version_id,
        catalogue_version_id=catalogue_id,
        effective_at=lambda market_as_of, known_as_of: True,
    )
    catalogue = SimpleNamespace(
        provider="upstox",
        catalogue_version_id=catalogue_id,
        visible_at=lambda market_as_of, known_as_of: True,
    )
    subject = SimpleNamespace(
        resolution_market_as_of=when,
        resolution_known_as_of=when,
        provider_mapping=mapping,
        contract_version=version,
    )
    event = SimpleNamespace(
        provider="upstox",
        provider_contract_key="NSE_FO|fixture",
        provider_mapping_id=mapping_id,
        contract_version_id=version_id,
        economic_subject_id=subject_id,
        subject=subject,
    )
    command = SimpleNamespace(
        market_as_of=when,
        known_as_of=when,
    )
    mapping_state = SimpleNamespace(
        value=mapping,
        record=SimpleNamespace(
            record_id="sha256:" + "5" * 64
        ),
    )
    version_state = SimpleNamespace(
        value=version,
        record=SimpleNamespace(
            record_id="sha256:" + "6" * 64
        ),
    )
    catalogue_state = SimpleNamespace(
        value=catalogue,
        record=SimpleNamespace(
            record_id="sha256:" + "7" * 64
        ),
    )
    return (
        event,
        command,
        mapping_state,
        subject_id,
        version_state,
        catalogue_state,
    )


def test_quote_provenance_binding_returns_exact_record_ids() -> None:
    (
        event,
        command,
        mapping_state,
        mapping_instrument_id,
        version_state,
        catalogue_state,
    ) = _provenance_binding_fixture()

    values = (
        PostgresMarketEventRepository
        ._bind_resolved_quote_provenance(
            event,
            command,
            mapping_state,
            mapping_instrument_id,
            version_state,
            catalogue_state,
        )
    )

    assert values == {
        "provider_mapping_record_id": (
            mapping_state.record.record_id
        ),
        "contract_version_record_id": (
            version_state.record.record_id
        ),
        "catalogue_version_record_id": (
            catalogue_state.record.record_id
        ),
    }
    assert all(
        field in OBSERVATION_IMMUTABLE_FIELDS
        for field in values
    )


def test_quote_provenance_binding_rejects_time_mismatch() -> None:
    (
        event,
        command,
        mapping_state,
        mapping_instrument_id,
        version_state,
        catalogue_state,
    ) = _provenance_binding_fixture()
    event.subject.resolution_known_as_of = datetime(
        2026,
        8,
        5,
        9,
        16,
        tzinfo=UTC,
    )

    with pytest.raises(PersistenceTimeBindingError):
        (
            PostgresMarketEventRepository
            ._bind_resolved_quote_provenance(
                event,
                command,
                mapping_state,
                mapping_instrument_id,
                version_state,
                catalogue_state,
            )
        )


def test_quote_provenance_binding_rejects_cross_link() -> None:
    (
        event,
        command,
        mapping_state,
        mapping_instrument_id,
        version_state,
        catalogue_state,
    ) = _provenance_binding_fixture()

    with pytest.raises(CatalogueProvenanceConflictError):
        (
            PostgresMarketEventRepository
            ._bind_resolved_quote_provenance(
                event,
                command,
                mapping_state,
                "sha256:" + "8" * 64,
                version_state,
                catalogue_state,
            )
        )


def test_quote_provenance_binding_rejects_missing_record() -> None:
    (
        event,
        command,
        mapping_state,
        mapping_instrument_id,
        version_state,
        catalogue_state,
    ) = _provenance_binding_fixture()

    with pytest.raises(MarketEventReferentialIntegrityError):
        (
            PostgresMarketEventRepository
            ._bind_resolved_quote_provenance(
                event,
                command,
                None,
                mapping_instrument_id,
                version_state,
                catalogue_state,
            )
        )


def test_result_event_membership_metadata_preserves_order() -> None:
    table = Base.metadata.tables[
        "market_normalization_result_events"
    ]

    assert set(table.c.keys()) == {
        "result_id",
        "raw_event_id",
        "event_ordinal",
        "event_id",
    }
    assert tuple(
        table.primary_key.columns.keys()
    ) == (
        "result_id",
        "event_ordinal",
    )
    assert (
        "result_id",
        "event_id",
    ) in _unique_column_shapes(table)

    foreign_keys = _foreign_key_shapes(table)
    assert (
        (
            "result_id",
            "raw_event_id",
        ),
        (
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
        ),
    ) in foreign_keys
    assert (
        (
            "event_id",
            "raw_event_id",
        ),
        (
            "market_observations.event_id",
            "market_observations.raw_event_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
        ),
    ) in foreign_keys

    assert _index_shapes(table) == {
        "ix_market_normalization_result_events_event": (
            "event_id",
            "result_id",
        ),
    }


def test_market_normalization_failures_metadata_is_explicit_registry() -> None:
    table = Base.metadata.tables[
        "market_normalization_failures"
    ]

    assert tuple(
        table.primary_key.columns.keys()
    ) == ("failure_id",)
    assert "id" not in table.c
    assert "created_at" not in table.c

    assert set(table.c.keys()) == {
        "failure_id",
        "result_id",
        "raw_event_id",
        "scope",
        "reason_code",
        "provider_contract_key",
        "segment",
        "safe_detail_code",
        "selected_feed_union",
        "provider_depth_levels_present",
        "field_paths",
        "unadopted_schema_paths",
        "present_unadopted_message_paths",
        "payload",
    }

    assert isinstance(
        table.c.field_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.unadopted_schema_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.present_unadopted_message_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.payload.type,
        JSONB,
    )

    assert (
        "failure_id",
        "result_id",
        "raw_event_id",
    ) in _unique_column_shapes(table)

    assert (
        (
            "result_id",
            "raw_event_id",
        ),
        (
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
        ),
    ) in _foreign_key_shapes(table)

    assert _index_shapes(table) == {
        "ix_market_normalization_failures_result_scope": (
            "result_id",
            "scope",
            "failure_id",
        ),
        "ix_market_normalization_failures_reason": (
            "reason_code",
            "failure_id",
        ),
    }


def test_result_failure_membership_metadata_preserves_role_order() -> None:
    table = Base.metadata.tables[
        "market_normalization_result_failures"
    ]

    assert set(table.c.keys()) == {
        "result_id",
        "raw_event_id",
        "failure_role",
        "failure_ordinal",
        "failure_id",
    }
    assert tuple(
        table.primary_key.columns.keys()
    ) == (
        "result_id",
        "failure_role",
        "failure_ordinal",
    )
    assert (
        "result_id",
        "raw_event_id",
        "failure_role",
        "failure_ordinal",
    ) in _unique_column_shapes(table)

    foreign_keys = _foreign_key_shapes(table)
    assert (
        (
            "result_id",
            "raw_event_id",
        ),
        (
            "market_normalization_results.result_id",
            "market_normalization_results.raw_event_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
        ),
    ) in foreign_keys
    assert (
        (
            "failure_id",
            "result_id",
            "raw_event_id",
        ),
        (
            "market_normalization_failures.failure_id",
            "market_normalization_failures.result_id",
            "market_normalization_failures.raw_event_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
            "NO ACTION",
        ),
    ) in foreign_keys

    indexes = {
        index.name: (
            tuple(
                column.name
                for column in index.columns
            ),
            index.unique,
        )
        for index in table.indexes
    }
    assert indexes == {
        "uq_market_normalization_result_failures_one_frame": (
            ("result_id",),
            True,
        ),
        "ix_market_normalization_result_failures_failure": (
            (
                "failure_id",
                "result_id",
            ),
            False,
        ),
    }


QUOTE_SUBTYPE_COLUMNS = {
    "event_id",
    "event_type",
    "subject_id",
    "feed_response_type",
    "request_mode",
    "feed_union",
    "is_snapshot",
    "presence_semantics",
    "numeric_basis",
    "quantity_basis",
    "bid_price",
    "bid_size",
    "ask_price",
    "ask_size",
    "last_price",
    "last_size",
    "last_trade_at",
    "previous_close_price",
    "reported_volume",
    "open_interest",
    "provider_depth_levels_present",
    "normalized_depth_levels",
    "unadopted_depth_level_count",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "secondary_payload_paths_present",
}


@pytest.mark.parametrize(
    ("table_name", "event_type"),
    (
        (
            "underlying_quote_observations",
            "underlying_quote_observation",
        ),
        (
            "futures_quote_observations",
            "futures_quote_observation",
        ),
        (
            "option_quote_observations",
            "option_quote_observation",
        ),
    ),
)
def test_quote_subtype_metadata_is_typed_and_bound(
    table_name: str,
    event_type: str,
) -> None:
    table = Base.metadata.tables[table_name]

    assert tuple(
        table.primary_key.columns.keys()
    ) == ("event_id",)
    assert "id" not in table.c
    assert "created_at" not in table.c
    assert set(table.c.keys()) == QUOTE_SUBTYPE_COLUMNS

    for column_name in (
        "bid_price",
        "ask_price",
        "last_price",
        "previous_close_price",
    ):
        assert isinstance(
            table.c[column_name].type,
            Numeric,
        )

    for column_name in (
        "bid_size",
        "ask_size",
        "last_size",
        "reported_volume",
        "open_interest",
    ):
        assert isinstance(
            table.c[column_name].type,
            BigInteger,
        )

    assert isinstance(table.c.is_snapshot.type, Boolean)
    assert isinstance(
        table.c.unadopted_schema_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.present_unadopted_message_paths.type,
        ARRAY,
    )
    assert isinstance(
        table.c.secondary_payload_paths_present.type,
        ARRAY,
    )

    assert (
        (
            "event_id",
            "event_type",
            "subject_id",
        ),
        (
            "market_observations.event_id",
            "market_observations.event_type",
            "market_observations.subject_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
            "NO ACTION",
        ),
    ) in _foreign_key_shapes(table)

    assert _index_shapes(table) == {
        f"ix_{table_name}_mode_union": (
            "request_mode",
            "feed_union",
            "event_id",
        ),
    }

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert event_type in checks[
        f"ck_{table_name}_event_type"
    ]
    assert f"ck_{table_name}_feed_shape" in checks
    assert f"ck_{table_name}_depth_reconciliation" in checks


def test_market_segment_status_subtype_metadata_is_typed_and_bound() -> None:
    table = Base.metadata.tables[
        "market_segment_status_observations"
    ]

    assert tuple(
        table.primary_key.columns.keys()
    ) == ("event_id",)
    assert "id" not in table.c
    assert "created_at" not in table.c
    assert set(table.c.keys()) == {
        "event_id",
        "event_type",
        "subject_id",
        "segment",
        "provider_status_name",
        "provider_status_numeric",
        "status_is_known",
    }
    assert isinstance(
        table.c.provider_status_numeric.type,
        Integer,
    )
    assert isinstance(
        table.c.status_is_known.type,
        Boolean,
    )
    assert (
        (
            "event_id",
            "event_type",
            "subject_id",
        ),
        (
            "market_observations.event_id",
            "market_observations.event_type",
            "market_observations.subject_id",
        ),
        (
            "NO ACTION",
            "NO ACTION",
            "NO ACTION",
        ),
    ) in _foreign_key_shapes(table)
    assert _index_shapes(table) == {
        "ix_market_segment_status_segment_code": (
            "segment",
            "provider_status_numeric",
            "event_id",
        ),
    }


def test_quote_subtype_projection_preserves_exact_numeric_values() -> None:
    event_id = "sha256:" + "7" * 64
    subject_id = "sha256:" + "8" * 64
    event = SimpleNamespace(
        event_id=event_id,
        identity=SimpleNamespace(
            event_type="option_quote_observation",
            subject_id=subject_id,
        ),
        feed_response_type=SimpleNamespace(value="live_feed"),
        request_mode=SimpleNamespace(value="option_greeks"),
        feed_union=SimpleNamespace(
            value="firstLevelWithGreeks"
        ),
        is_snapshot=False,
        presence_semantics="proto3_parent_implied_v1",
        numeric_basis=(
            "protobuf_double_roundtrip_decimal_v1"
        ),
        quantity_basis="upstox_reported_quantity_v1",
        bid_price=Decimal("101.125"),
        bid_size=5,
        ask_price=Decimal("101.250"),
        ask_size=7,
        last_price=Decimal("101.200"),
        last_size=2,
        last_trade_at=datetime(2026, 8, 5, tzinfo=UTC),
        previous_close_price=Decimal("100.000"),
        reported_volume=1000,
        open_interest=500,
        provider_depth_levels_present=1,
        normalized_depth_levels=1,
        unadopted_depth_level_count=0,
        unadopted_schema_paths=("feeds[*].ff",),
        present_unadopted_message_paths=(),
        secondary_payload_paths_present=(),
    )

    table_name, values = (
        PostgresMarketEventRepository._subtype_values(
            event
        )
    )

    assert table_name == "option_quote_observations"
    assert tuple(values) == QUOTE_SUBTYPE_IMMUTABLE_FIELDS
    assert values["bid_price"] == Decimal("101.125")
    assert values["ask_price"] == Decimal("101.250")
    assert values["unadopted_schema_paths"] == [
        "feeds[*].ff"
    ]


def test_status_subtype_projection_preserves_provider_code() -> None:
    event = SimpleNamespace(
        event_id="sha256:" + "9" * 64,
        identity=SimpleNamespace(
            event_type=(
                "market_segment_status_observation"
            ),
            subject_id="sha256:" + "a" * 64,
        ),
        segment="NSE_FO",
        provider_status_name="NORMAL_OPEN",
        provider_status_numeric=2,
        status_is_known=True,
    )

    table_name, values = (
        PostgresMarketEventRepository._subtype_values(
            event
        )
    )

    assert (
        table_name
        == "market_segment_status_observations"
    )
    assert tuple(values) == STATUS_SUBTYPE_IMMUTABLE_FIELDS
    assert values["provider_status_numeric"] == 2
    assert values["status_is_known"] is True
