from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.quality.contracts import (
    AssessmentIdentity,
    AssessmentRunIdentity,
    EvaluationContext,
    QualityDisposition,
    QualityPolicyIdentity,
    QualityPolicyVersionIdentity,
    QualitySeverity,
    reduce_disposition,
)

ZERO_ID = "sha256:" + "0" * 64
ONE_ID = "sha256:" + "1" * 64
TWO_ID = "sha256:" + "2" * 64


def test_frozen_policy_identity_vector() -> None:
    assert QualityPolicyIdentity().policy_id == (
        "sha256:eb8daac12517a8e65f25e2a0aee14cda8eeb4a3b2308a80719f747bdcb333d01"
    )


def test_frozen_policy_version_identity_vector() -> None:
    assert QualityPolicyVersionIdentity(ZERO_ID).policy_version_id == (
        "sha256:85eafa1a1b1517e373c0784d2842d11b065cd8c0ae3502d1aeb1398e4bea929d"
    )


def test_context_rejects_known_before_market() -> None:
    market = datetime(2026, 8, 7, 10, tzinfo=UTC)
    with pytest.raises(ValueError, match="cannot precede"):
        EvaluationContext(market, market - timedelta(microseconds=1))


def test_dependency_market_cutoff_uses_minimum() -> None:
    market = datetime(2026, 8, 7, 10, tzinfo=UTC)
    context = EvaluationContext(market, market + timedelta(seconds=1))
    assert context.dependency_market_as_of(market + timedelta(milliseconds=1)) == market
    assert context.dependency_market_as_of(market - timedelta(milliseconds=1)) == market - timedelta(milliseconds=1)


def test_assessment_identity_excludes_result_and_run_packaging() -> None:
    context = EvaluationContext(
        datetime(2026, 8, 7, 10, tzinfo=UTC),
        datetime(2026, 8, 7, 10, 0, 1, tzinfo=UTC),
    )
    first = AssessmentIdentity(ONE_ID, TWO_ID, context)
    second = AssessmentIdentity(ONE_ID, TWO_ID, context)
    assert first.assessment_id == second.assessment_id


def test_run_identity_sorts_and_rejects_duplicate_targets() -> None:
    context = EvaluationContext(
        datetime(2026, 8, 7, 10, tzinfo=UTC),
        datetime(2026, 8, 7, 10, 0, 1, tzinfo=UTC),
    )
    run = AssessmentRunIdentity(TWO_ID, context, (TWO_ID, ONE_ID))
    assert run.ordered_target_event_ids == (ONE_ID, TWO_ID)
    with pytest.raises(ValueError, match="unique"):
        AssessmentRunIdentity(TWO_ID, context, (ONE_ID, ONE_ID))


def test_disposition_reduction() -> None:
    assert reduce_disposition(()) is QualityDisposition.ELIGIBLE
    assert reduce_disposition((QualitySeverity.WARNING,)) is QualityDisposition.WARNING
    assert reduce_disposition((QualitySeverity.WARNING, QualitySeverity.ERROR)) is QualityDisposition.INELIGIBLE
