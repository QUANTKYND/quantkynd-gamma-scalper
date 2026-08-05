from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.instruments.temporal_records import (
    AmbiguousPointInTimeResultError,
    InvalidTemporalGraphError,
    TemporalRecord,
    TemporalRecordKind,
    TemporalState,
    resolve_temporal_knowledge_leaf,
    resolve_temporal_state,
)


NOW = datetime(2026, 8, 4, tzinfo=UTC)


@dataclass(frozen=True)
class Value:
    name: str
    eligible: bool = True


@dataclass(frozen=True)
class CorruptRecord:
    record_id: str
    kind: TemporalRecordKind
    semantic_id: str
    scope_id: str
    recorded_at: datetime
    supersedes_record_id: str | None = None


def record(
    semantic_id: str,
    recorded_at: datetime,
    supersedes_record_id: str | None = None,
) -> TemporalRecord:
    return TemporalRecord(
        TemporalRecordKind.CATALOGUE_VERSION,
        semantic_id,
        "provider",
        recorded_at,
        supersedes_record_id,
        "source",
    )


def test_record_identity_is_deterministic_and_separate_from_semantic_identity() -> None:
    first = record("semantic", NOW)
    repeated = record("semantic", NOW)
    later = record("semantic", NOW + timedelta(seconds=1))
    assert first.record_id == repeated.record_id
    assert first.semantic_id == later.semantic_id
    assert first.record_id != later.record_id


def test_historical_and_current_selection_follow_visible_successors() -> None:
    first = record("first", NOW)
    second = record("second", NOW + timedelta(hours=1), first.record_id)
    states = (TemporalState(first, Value("first")), TemporalState(second, Value("second")))
    historical = resolve_temporal_state(
        states,
        NOW + timedelta(minutes=30),
        lambda value: value.eligible,
    )
    current = resolve_temporal_state(states, None, lambda value: value.eligible)
    assert historical is not None and historical.value.name == "first"
    assert current is not None and current.value.name == "second"


def test_ineligible_successor_does_not_hide_market_eligible_predecessor() -> None:
    first = record("first", NOW)
    second = record("second", NOW + timedelta(hours=1), first.record_id)
    resolved = resolve_temporal_state(
        (
            TemporalState(first, Value("first", True)),
            TemporalState(second, Value("second", False)),
        ),
        None,
        lambda value: value.eligible,
    )
    assert resolved is not None and resolved.value.name == "first"


def test_eligible_descendant_hides_eligible_ancestor_through_ineligible_intermediate() -> None:
    first = record("A", NOW)
    second = record("B", NOW + timedelta(hours=1), first.record_id)
    historical = record("H", NOW + timedelta(hours=2), second.record_id)

    resolved = resolve_temporal_state(
        (
            TemporalState(first, Value("A", True)),
            TemporalState(second, Value("B", False)),
            TemporalState(historical, Value("H", True)),
        ),
        None,
        lambda value: value.eligible,
    )

    assert resolved is not None and resolved.value.name == "H"


def test_ineligible_descendant_leaves_latest_eligible_ancestor() -> None:
    first = record("A", NOW)
    second = record("B", NOW + timedelta(hours=1), first.record_id)
    historical = record("H", NOW + timedelta(hours=2), second.record_id)

    resolved = resolve_temporal_state(
        (
            TemporalState(first, Value("A", True)),
            TemporalState(second, Value("B", True)),
            TemporalState(historical, Value("H", False)),
        ),
        None,
        lambda value: value.eligible,
    )

    assert resolved is not None and resolved.value.name == "B"


def test_only_eligible_root_remains_selected() -> None:
    first = record("A", NOW)
    second = record("B", NOW + timedelta(hours=1), first.record_id)
    historical = record("H", NOW + timedelta(hours=2), second.record_id)

    resolved = resolve_temporal_state(
        (
            TemporalState(first, Value("A", True)),
            TemporalState(second, Value("B", False)),
            TemporalState(historical, Value("H", False)),
        ),
        None,
        lambda value: value.eligible,
    )

    assert resolved is not None and resolved.value.name == "A"


def test_historical_cutoff_changes_selection_from_ancestor_to_transitive_descendant() -> None:
    first = record("A", NOW)
    second = record("B", NOW + timedelta(hours=1), first.record_id)
    historical = record("H", NOW + timedelta(hours=2), second.record_id)
    states = (
        TemporalState(first, Value("A", True)),
        TemporalState(second, Value("B", False)),
        TemporalState(historical, Value("H", True)),
    )

    before_h = resolve_temporal_state(
        states,
        NOW + timedelta(hours=1, minutes=30),
        lambda value: value.eligible,
    )
    after_h = resolve_temporal_state(states, None, lambda value: value.eligible)

    assert before_h is not None and before_h.value.name == "A"
    assert after_h is not None and after_h.value.name == "H"


def test_knowledge_leaf_ignores_market_eligibility() -> None:
    first = record("first", NOW)
    second = record("second", NOW + timedelta(hours=1), first.record_id)
    states = (
        TemporalState(first, Value("first", True)),
        TemporalState(second, Value("second", False)),
    )

    resolved = resolve_temporal_knowledge_leaf(states, None)

    assert resolved is not None and resolved.value.name == "second"


def test_knowledge_leaf_honors_knowledge_cutoff() -> None:
    first = record("first", NOW)
    second = record("second", NOW + timedelta(hours=1), first.record_id)
    states = (TemporalState(first, Value("first")), TemporalState(second, Value("second")))

    resolved = resolve_temporal_knowledge_leaf(states, NOW + timedelta(minutes=30))

    assert resolved is not None and resolved.value.name == "first"


@pytest.mark.parametrize(
    "records, message",
    [
        (
            (CorruptRecord("self", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW, "self"),),
            "themselves",
        ),
        (
            (CorruptRecord("missing", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW, "absent"),),
            "missing",
        ),
        (
            (
                CorruptRecord("a", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW),
                CorruptRecord("b", TemporalRecordKind.CATALOGUE_VERSION, "b", "q", NOW + timedelta(seconds=1), "a"),
            ),
            "scope",
        ),
        (
            (
                CorruptRecord("a", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW),
                CorruptRecord(
                    "b",
                    TemporalRecordKind.INSTRUMENT_VERSION,
                    "b",
                    "p",
                    NOW + timedelta(seconds=1),
                    "a",
                ),
            ),
            "scope",
        ),
        (
            (
                CorruptRecord("a", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW),
                CorruptRecord("b", TemporalRecordKind.CATALOGUE_VERSION, "b", "p", NOW + timedelta(seconds=1), "a"),
                CorruptRecord("c", TemporalRecordKind.CATALOGUE_VERSION, "c", "p", NOW + timedelta(seconds=2), "a"),
            ),
            "branch",
        ),
        (
            (
                CorruptRecord("a", TemporalRecordKind.CATALOGUE_VERSION, "a", "p", NOW + timedelta(seconds=1), "b"),
                CorruptRecord("b", TemporalRecordKind.CATALOGUE_VERSION, "b", "p", NOW, "a"),
            ),
            "strictly after|cycle",
        ),
    ],
)
def test_corrupt_graphs_fail_closed(records, message: str) -> None:
    states = tuple(TemporalState(item, Value(item.semantic_id)) for item in records)
    with pytest.raises(InvalidTemporalGraphError, match=message):
        resolve_temporal_state(states, None, lambda value: value.eligible)


def test_multiple_root_leaves_are_ambiguous() -> None:
    states = (
        TemporalState(record("a", NOW), Value("a")),
        TemporalState(record("b", NOW + timedelta(seconds=1)), Value("b")),
    )
    with pytest.raises(AmbiguousPointInTimeResultError):
        resolve_temporal_state(states, None, lambda value: value.eligible)
    with pytest.raises(AmbiguousPointInTimeResultError):
        resolve_temporal_knowledge_leaf(states, None)
