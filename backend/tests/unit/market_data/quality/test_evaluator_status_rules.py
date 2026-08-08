from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import (
    DependencyOutcome,
    EvaluationContext,
    QualityDisposition,
)
from app.market_data.quality.errors import InvalidQualityEvaluationCommandError
from app.market_data.quality.evaluator import (
    ConnectionFact,
    QualityEvaluationInput,
    SessionFact,
    StatusTarget,
    TargetDependencies,
    evaluate_quality,
)
from app.market_data.quality.policy_parser import parse_quality_policy

M = datetime(2026, 8, 7, 10, tzinfo=UTC)
K = datetime(2026, 8, 7, 11, tzinfo=UTC)
CONTEXT = EvaluationContext(M, K)
ROOT = Path(__file__).resolve().parents[5]
POLICY_BYTES = (
    ROOT / "config/data_quality/upstox-nse-market-observation-quality-v1.yaml"
).read_bytes()
POLICY = parse_quality_policy(POLICY_BYTES)


def ident(seed: str) -> str:
    return stable_hash(seed)


def deps():
    return TargetDependencies(
        trading_session=SessionFact(
            dependency_id=ident("session"),
            search_scope_hash=ident("session-search"),
            outcome=DependencyOutcome.SELECTED,
            candidate_count=1,
            timezone="Asia/Kolkata",
            status="scheduled",
            open_at=M - timedelta(hours=1),
            close_at=M + timedelta(hours=1),
            selected_session_version_id=ident("session-version"),
            selected_record_id=ident("session-record"),
            exchange_date="2026-08-07",
        ),
        connection=ConnectionFact(
            dependency_id=ident("connection"),
            search_scope_hash=ident("connection-search"),
            outcome=DependencyOutcome.SELECTED,
            candidate_count=1,
            state="authorized",
            occurred_at=M - timedelta(hours=1),
            selected_event_id=ident("connection-event"),
        ),
    )


def target(**overrides):
    values = dict(
        event_id=ident("status-event"),
        provider="upstox",
        segment="NSE_FO",
        normalization_schema_version=1,
        normalizer_implementation_version="upstox-v3-normalizer-1",
        provider_timestamp=M - timedelta(seconds=1),
        available_at=M - timedelta(seconds=1),
        availability_basis="received",
        status_is_known=True,
        status_name="NORMAL_OPEN",
    )
    values.update(overrides)
    return StatusTarget(**values)


def evaluate(value=None, dependencies=None, policy=POLICY):
    return evaluate_quality(
        QualityEvaluationInput(policy, CONTEXT, value or target(), dependencies or deps())
    )


def codes(result):
    return [item.reason_code for item in result.reasons]


def test_clean_status_target_is_eligible_without_self_dependency():
    result = evaluate()
    assert result.disposition is QualityDisposition.ELIGIBLE
    assert result.reasons == ()


def test_status_unknown_and_not_open_are_mutually_exclusive():
    unknown = evaluate(target(status_is_known=False, status_name="UNKNOWN_99"))
    assert "segment_status_unknown" in codes(unknown)
    assert "segment_not_normal_open" not in codes(unknown)
    closed = evaluate(target(status_name="NORMAL_CLOSE"))
    assert "segment_not_normal_open" in codes(closed)


def test_status_freshness_boundaries_and_future_suppression():
    warning = evaluate(target(provider_timestamp=M - timedelta(seconds=60)))
    assert "status_age_warning" in codes(warning)
    stale = evaluate(target(provider_timestamp=M - timedelta(seconds=300)))
    assert "status_stale" in codes(stale)
    assert "status_age_warning" not in codes(stale)
    future = evaluate(target(provider_timestamp=M + timedelta(microseconds=1)))
    assert "provider_timestamp_in_future" in codes(future)
    assert "status_age_warning" not in codes(future)
    assert "status_stale" not in codes(future)


def test_status_target_requires_valid_segment_session_and_connection():
    base = deps()
    broken = replace(
        base,
        trading_session=replace(base.trading_session, timezone="UTC"),
        connection=replace(base.connection, state="closed"),
    )
    result = evaluate(target(segment="OTHER"), broken)
    assert set(codes(result)) >= {
        "provider_segment_mismatch",
        "trading_session_timezone_mismatch",
        "connection_not_authorized",
    }


def test_status_freshness_is_read_from_policy_semantics():
    fast_warning = parse_quality_policy(
        POLICY_BYTES.replace(
            b'warning_ms: "60000"\n    error_ms: "300000"',
            b'warning_ms: "1000"\n    error_ms: "300000"',
            1,
        )
    )
    value = target(provider_timestamp=M - timedelta(seconds=2))
    assert "status_age_warning" not in codes(evaluate(value))
    assert "status_age_warning" in codes(evaluate(value, policy=fast_warning))


def test_status_target_rejects_non_applicable_dependencies():
    broken = replace(deps(), market_segment_status=object())
    with pytest.raises(
        InvalidQualityEvaluationCommandError,
        match="cannot carry quote-only or self-status dependencies",
    ):
        evaluate(dependencies=broken)
