from datetime import UTC, datetime, timedelta

import pytest

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import DependencyOutcome
from app.market_data.quality.dependency_resolution import (
    RankedCandidate,
    TemporalCandidate,
    resolve_ranked_candidates,
    resolve_temporal_candidates,
)
from app.market_data.quality.errors import QualityDurableCorruptionError

BASE = datetime(2026, 8, 7, 10, tzinfo=UTC)


def ident(seed: str) -> str:
    return stable_hash(seed)


def temporal(
    seed: str,
    *,
    recorded_minutes: int = 0,
    receipt_minutes: int = 0,
    valid_from_minutes: int = -60,
    valid_until_minutes: int | None = None,
    predecessor: str | None = None,
    scope: str = "scope",
) -> TemporalCandidate:
    return TemporalCandidate(
        record_id=ident(f"record:{seed}"),
        semantic_id=ident(f"semantic:{seed}"),
        scope_id=scope,
        recorded_at=BASE + timedelta(minutes=recorded_minutes),
        receipt_at=BASE + timedelta(minutes=receipt_minutes),
        valid_from=BASE + timedelta(minutes=valid_from_minutes),
        valid_until=(
            None
            if valid_until_minutes is None
            else BASE + timedelta(minutes=valid_until_minutes)
        ),
        supersedes_record_id=predecessor,
        content_hash=ident(f"content:{seed}"),
        payload={"seed": seed},
    )


def ranked(seed: str, *, scope: str, order: int, content: str, minute: int = 0):
    return RankedCandidate(
        candidate_id=ident(f"candidate:{seed}"),
        effective_at=BASE + timedelta(minutes=minute),
        source_order_scope_id=scope,
        source_order=order,
        content_hash=ident(f"content:{content}"),
        payload={"content": content},
    )


def test_temporal_resolution_selects_one_effective_leaf():
    first = temporal("first")
    second = temporal("second", recorded_minutes=1, predecessor=first.record_id)
    result = resolve_temporal_candidates((first, second), BASE + timedelta(minutes=2), BASE + timedelta(minutes=2))
    assert result.outcome is DependencyOutcome.SELECTED
    assert result.selected == second


def test_temporal_resolution_keeps_effective_predecessor_when_successor_is_not_yet_effective():
    first = temporal("first")
    second = temporal(
        "second",
        recorded_minutes=1,
        valid_from_minutes=30,
        predecessor=first.record_id,
    )
    result = resolve_temporal_candidates((first, second), BASE + timedelta(minutes=2), BASE + timedelta(minutes=2))
    assert result.outcome is DependencyOutcome.SELECTED
    assert result.selected == first


def test_temporal_resolution_distinguishes_missing_from_not_effective():
    candidate = temporal("future", valid_from_minutes=30)
    result = resolve_temporal_candidates((candidate,), BASE, BASE)
    assert result.outcome is DependencyOutcome.ABSENT
    assert result.has_visible_knowledge_leaf is True

    hidden = temporal("hidden", recorded_minutes=5, receipt_minutes=5)
    hidden_result = resolve_temporal_candidates((hidden,), BASE, BASE)
    assert hidden_result.outcome is DependencyOutcome.ABSENT
    assert hidden_result.has_visible_knowledge_leaf is False


def test_temporal_resolution_reports_multiple_effective_roots_as_ambiguous():
    one = temporal("one", scope="same")
    two = temporal("two", scope="same")
    result = resolve_temporal_candidates((one, two), BASE, BASE)
    assert result.outcome is DependencyOutcome.AMBIGUOUS
    assert len(result.effective_candidates) == 2


def test_visible_successor_with_hidden_predecessor_is_corruption():
    predecessor = temporal("predecessor", receipt_minutes=5)
    successor = temporal("successor", predecessor=predecessor.record_id)
    with pytest.raises(QualityDurableCorruptionError, match="target is missing"):
        resolve_temporal_candidates((predecessor, successor), BASE, BASE)


def test_ranked_exact_duplicates_across_scopes_are_benign():
    one = ranked("one", scope="a", order=1, content="same")
    two = ranked("two", scope="b", order=9, content="same")
    result = resolve_ranked_candidates((two, one), BASE)
    assert result.outcome is DependencyOutcome.SELECTED
    assert result.selected.candidate_id == min(one.candidate_id, two.candidate_id)
    assert len(result.benign_duplicate_ids) == 1


def test_ranked_equal_time_conflict_across_scopes_is_ambiguous():
    one = ranked("one", scope="a", order=1, content="left")
    two = ranked("two", scope="b", order=1, content="right")
    result = resolve_ranked_candidates((one, two), BASE)
    assert result.outcome is DependencyOutcome.AMBIGUOUS
    assert result.selected is None


def test_ranked_same_scope_same_order_conflict_is_corruption():
    one = ranked("one", scope="a", order=1, content="left")
    two = ranked("two", scope="a", order=1, content="right")
    with pytest.raises(QualityDurableCorruptionError, match="source-order rank"):
        resolve_ranked_candidates((one, two), BASE)


def test_seventeen_candidate_ambiguity_is_complete_and_deterministic():
    candidates = tuple(
        ranked(str(index), scope=f"scope-{index}", order=index, content=f"state-{index}")
        for index in range(17)
    )
    first = resolve_ranked_candidates(candidates, BASE)
    second = resolve_ranked_candidates(tuple(reversed(candidates)), BASE)
    assert first.outcome is DependencyOutcome.AMBIGUOUS
    assert len(first.ranked_candidates) == 17
    assert first.candidate_set_hash == second.candidate_set_hash
