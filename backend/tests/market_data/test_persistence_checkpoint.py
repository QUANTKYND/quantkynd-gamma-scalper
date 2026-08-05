import hashlib
from datetime import UTC, datetime

import pytest

from app.persistence.postgres.repositories import (
    EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
    FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
    _rows_match_on_fields,
)

from app.market_data.persistence.contracts import (
    CANONICAL_IMPLEMENTATION,
    DATA14_ADVISORY_LOCK_NAMESPACE,
    DurableResultIdentity,
    QueryCursor,
)
from app.market_data.persistence.planner import derive_lock_stripes, lock_stripe, plan_parameter_chunks


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