from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import (
    DependencyOutcome,
    EvaluationContext,
    QualityDisposition,
    TargetKind,
)
from app.market_data.quality.evaluator import (
    ConnectionFact,
    EvidenceValue,
    MarketStatusFact,
    ProvenanceDependencyFact,
    QualityEvaluationInput,
    QualityReasonOccurrence,
    ReasonEvidence,
    QuoteTarget,
    SessionFact,
    SubjectScopeFact,
    SubscriptionFact,
    SubscriptionResolutionState,
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


def provenance(name: str, *, tick_size: Decimal | None = None, trading_status: str | None = None):
    semantic = ident(f"{name}:semantic")
    record = ident(f"{name}:record")
    return ProvenanceDependencyFact(
        dependency_id=ident(f"{name}:dependency"),
        search_scope_hash=ident(f"{name}:scope"),
        outcome=DependencyOutcome.SELECTED,
        candidate_count=1,
        has_visible_knowledge_leaf=True,
        persisted_semantic_id=semantic,
        persisted_record_id=record,
        selected_semantic_id=semantic,
        selected_record_id=record,
        tick_size=tick_size,
        trading_status=trading_status,
    )


def dependencies() -> TargetDependencies:
    return TargetDependencies(
        subject_scope=SubjectScopeFact(
            dependency_id=ident("subject-scope-dependency"),
            search_scope_hash=ident("subject-scope-search"),
            in_scope=True,
            catalogue_profile="upstox-nse-nifty-index-derivatives-v1",
            candidate_count=1,
            membership_id=ident("catalogue-membership"),
        ),
        provider_mapping=provenance("mapping"),
        instrument_version=provenance(
            "instrument", tick_size=Decimal("0.05"), trading_status="active"
        ),
        catalogue_version=provenance("catalogue"),
        trading_session=SessionFact(
            dependency_id=ident("session-dependency"),
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
        market_segment_status=MarketStatusFact(
            dependency_id=ident("status-dependency"),
            search_scope_hash=ident("status-search"),
            outcome=DependencyOutcome.SELECTED,
            candidate_count=1,
            provider_timestamp=M - timedelta(seconds=1),
            status_is_known=True,
            status_name="NORMAL_OPEN",
            selected_event_id=ident("status-event"),
        ),
        connection=ConnectionFact(
            dependency_id=ident("connection-dependency"),
            search_scope_hash=ident("connection-search"),
            outcome=DependencyOutcome.SELECTED,
            candidate_count=1,
            state="authorized",
            occurred_at=M - timedelta(hours=1),
            selected_event_id=ident("connection-event"),
        ),
        subscription=SubscriptionFact(
            dependency_id=ident("subscription-dependency"),
            search_scope_hash=ident("subscription-search"),
            state=SubscriptionResolutionState.SELECTED,
            candidate_count=1,
            scope_id="scope-1",
            effective_mode="full_d5",
            occurred_at=M - timedelta(minutes=30),
            selected_event_id=ident("subscription-event"),
            instrument_set_digest=ident("subscription-set"),
        ),
    )


def quote(**overrides) -> QuoteTarget:
    values = dict(
        event_id=ident("event"),
        target_kind=TargetKind.FUTURES_QUOTE,
        provider="upstox",
        provider_contract_key="NSE_FO|123",
        normalization_schema_version=1,
        normalizer_implementation_version="upstox-v3-normalizer-1",
        provider_timestamp=M - timedelta(seconds=1),
        available_at=M - timedelta(seconds=1),
        availability_basis="received",
        feed_response_type="live_feed",
        request_mode="full_d5",
        resolution_market_as_of=M - timedelta(seconds=1),
        resolution_known_as_of=K - timedelta(seconds=1),
        bid_price=Decimal("100.00"),
        bid_size=1,
        ask_price=Decimal("100.05"),
        ask_size=1,
        last_price=Decimal("100.00"),
    )
    values.update(overrides)
    if "resolution_market_as_of" not in overrides:
        values["resolution_market_as_of"] = min(values["provider_timestamp"], M)
    return QuoteTarget(**values)


def evaluate(target=None, deps=None, policy=POLICY):
    value = target or quote()
    selected_dependencies = deps or dependencies()
    if deps is None:
        selected_dependencies = replace(
            selected_dependencies,
            market_segment_status=replace(
                selected_dependencies.market_segment_status,
                provider_timestamp=value.provider_timestamp - timedelta(microseconds=1),
            ),
        )
    return evaluate_quality(
        QualityEvaluationInput(policy, CONTEXT, value, selected_dependencies)
    )


def codes(result):
    return [item.reason_code for item in result.reasons]


def test_clean_futures_quote_is_eligible():
    result = evaluate()
    assert result.disposition is QualityDisposition.ELIGIBLE
    assert result.reasons == ()


def test_future_target_is_ineligible_and_suppresses_freshness_reasons():
    result = evaluate(quote(provider_timestamp=M + timedelta(microseconds=1)))
    assert codes(result) == ["provider_timestamp_in_future"]
    assert result.dependency_market_as_of == M


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(milliseconds=1999, microseconds=999), []),
        (timedelta(milliseconds=2000), ["quote_age_warning"]),
        (timedelta(milliseconds=5000), ["quote_stale"]),
    ],
)
def test_freshness_boundaries_are_inclusive(age, expected):
    result = evaluate(quote(provider_timestamp=M - age))
    actual = [
        code
        for code in codes(result)
        if code in {"quote_age_warning", "quote_stale"}
    ]
    assert actual == expected


def test_locked_market_suppresses_spread_reason():
    result = evaluate(quote(bid_price=Decimal("100"), ask_price=Decimal("100")))
    assert "market_locked" in codes(result)
    assert "spread_warning" not in codes(result)
    assert "spread_limit_exceeded" not in codes(result)


def test_crossed_market_suppresses_locked_and_spread_reasons():
    result = evaluate(quote(bid_price=Decimal("100.05"), ask_price=Decimal("100")))
    assert "market_crossed" in codes(result)
    assert "market_locked" not in codes(result)
    assert "spread_warning" not in codes(result)


def test_spread_warning_and_error_use_one_aggregate_reason():
    warning = evaluate(quote(bid_price=Decimal("100"), ask_price=Decimal("100.20")))
    assert codes(warning).count("spread_warning") == 1
    error = evaluate(quote(bid_price=Decimal("100"), ask_price=Decimal("100.60")))
    assert codes(error).count("spread_limit_exceeded") == 1
    assert "spread_warning" not in codes(error)


def test_every_present_executable_price_is_tick_checked():
    result = evaluate(
        quote(
            bid_price=Decimal("100.03"),
            ask_price=Decimal("100.08"),
            last_price=Decimal("100.02"),
        )
    )
    off_tick = [
        item.subject_key
        for item in result.reasons
        if item.reason_code == "price_not_tick_aligned"
    ]
    assert off_tick == ["ask_price", "bid_price", "last_price"]


def test_missing_and_orphan_components_are_reported_independently():
    result = evaluate(
        quote(
            bid_price=None,
            bid_size=1,
            ask_price=None,
            ask_size=None,
            last_price=None,
            last_size=2,
            last_trade_at=M,
        )
    )
    assert set(codes(result)) >= {
        "bid_missing",
        "ask_missing",
        "ask_size_missing",
        "orphan_quote_component",
    }
    orphan_subjects = {
        item.subject_key
        for item in result.reasons
        if item.reason_code == "orphan_quote_component"
    }
    assert orphan_subjects == {"bid_size", "last_size", "last_trade_at"}


def test_historical_import_and_completeness_are_warnings():
    result = evaluate(
        quote(
            availability_basis="historical_import",
            unadopted_schema_paths=("feeds.*.foo",),
            present_unadopted_message_paths=("feeds.*.bar",),
            secondary_payload_paths_present=("feeds.*.baz",),
            provider_depth_levels_present=5,
            normalized_depth_levels=1,
            unadopted_depth_level_count=4,
        )
    )
    assert result.disposition is QualityDisposition.WARNING
    assert set(codes(result)) >= {
        "historical_import_availability",
        "unadopted_schema_paths_present",
        "present_unadopted_message_paths",
        "secondary_payload_paths_present",
        "depth_truncated",
    }


def test_dependency_missing_not_effective_ambiguous_and_mismatch_are_exclusive():
    base = dependencies()
    missing = replace(
        base.instrument_version,
        outcome=DependencyOutcome.ABSENT,
        candidate_count=0,
        has_visible_knowledge_leaf=False,
        selected_semantic_id=None,
        selected_record_id=None,
        tick_size=None,
        trading_status=None,
    )
    result = evaluate(deps=replace(base, instrument_version=missing))
    assert "instrument_version_missing" in codes(result)
    assert "instrument_version_not_effective" not in codes(result)
    assert "tick_size_missing_or_invalid" not in codes(result)

    not_effective = replace(missing, has_visible_knowledge_leaf=True)
    result = evaluate(deps=replace(base, instrument_version=not_effective))
    assert "instrument_version_not_effective" in codes(result)

    ambiguous = replace(
        missing,
        outcome=DependencyOutcome.AMBIGUOUS,
        candidate_count=2,
        candidate_set_hash=ident("instrument-candidates"),
    )
    result = evaluate(deps=replace(base, instrument_version=ambiguous))
    assert "instrument_version_ambiguous" in codes(result)

    mismatch = replace(
        base.instrument_version,
        selected_semantic_id=ident("different-semantic"),
    )
    result = evaluate(deps=replace(base, instrument_version=mismatch))
    assert "instrument_version_mismatch" in codes(result)


def test_session_status_connection_and_subscription_are_independent():
    base = dependencies()
    bad = replace(
        base,
        trading_session=replace(base.trading_session, status="cancelled"),
        market_segment_status=replace(base.market_segment_status, status_name="NORMAL_CLOSE"),
        connection=replace(base.connection, state="closed"),
        subscription=replace(base.subscription, effective_mode="ltpc"),
    )
    result = evaluate(deps=bad)
    assert set(codes(result)) >= {
        "trading_session_not_scheduled",
        "segment_not_normal_open",
        "connection_not_authorized",
        "subscription_mode_mismatch",
    }


def test_lifecycle_lease_accepts_exact_boundary_and_rejects_one_microsecond_after():
    base = dependencies()
    exact = replace(
        base,
        connection=replace(base.connection, occurred_at=M - timedelta(hours=12, seconds=1)),
        subscription=replace(base.subscription, occurred_at=M - timedelta(hours=12, seconds=1)),
    )
    assert "connection_state_stale" not in codes(evaluate(deps=exact))
    late = replace(
        base,
        connection=replace(
            base.connection,
            occurred_at=M - timedelta(hours=12, seconds=1, microseconds=1),
        ),
        subscription=replace(
            base.subscription,
            occurred_at=M - timedelta(hours=12, seconds=1, microseconds=1),
        ),
    )
    result = evaluate(deps=late)
    assert "connection_state_stale" in codes(result)
    assert "subscription_state_stale" in codes(result)


def test_reasons_are_sorted_by_registry_ordinal_not_rule_execution_order():
    result = evaluate(
        quote(
            provider="other",
            availability_basis="historical_import",
            bid_price=Decimal("100.03"),
            ask_price=Decimal("100.08"),
        )
    )
    ordinals = [item.definition.ordinal for item in result.reasons]
    assert ordinals == sorted(ordinals)
    assert result.reason_set_hash == stable_hash(
        tuple(item.canonical_payload for item in result.reasons)
    )


def test_subscription_mode_is_bound_to_target_request_mode():
    base = dependencies()
    selected = replace(base.subscription, effective_mode="ltpc")
    assert "subscription_mode_mismatch" in codes(
        evaluate(quote(request_mode="full_d5"), replace(base, subscription=selected))
    )
    assert "subscription_mode_mismatch" not in codes(
        evaluate(quote(request_mode="ltpc"), replace(base, subscription=selected))
    )


def test_lifecycle_lease_is_read_from_policy_semantics():
    short_lease = parse_quality_policy(
        POLICY_BYTES.replace(b'lease_ms: "43200000"', b'lease_ms: "1000"', 1)
    )
    base = dependencies()
    selected = replace(
        base,
        connection=replace(base.connection, occurred_at=M - timedelta(seconds=3)),
        subscription=replace(base.subscription, occurred_at=M - timedelta(seconds=3)),
    )
    assert "connection_state_stale" not in codes(evaluate(deps=selected))
    result = evaluate(deps=selected, policy=short_lease)
    assert "connection_state_stale" in codes(result)
    assert "subscription_state_stale" in codes(result)


def test_subject_scope_is_an_explicit_dependency_with_bounded_evidence():
    base = dependencies()
    out_of_scope = SubjectScopeFact(
        dependency_id=ident("subject-scope-dependency"),
        search_scope_hash=ident("subject-scope-search"),
        in_scope=False,
        catalogue_profile="upstox-nse-nifty-index-derivatives-v1",
        candidate_count=0,
    )
    result = evaluate(deps=replace(base, subject_scope=out_of_scope))
    reason = next(
        item for item in result.reasons if item.reason_code == "unsupported_subject_scope"
    )
    assert reason.evidence.subject_key == "observation"
    assert reason.evidence.dependency_ids == (out_of_scope.dependency_id,)
    assert {item.name for item in reason.evidence.details} == {
        "candidate_count",
        "search_scope_hash",
    }


def test_missing_dependency_evidence_binds_t_k_and_search_scope():
    base = dependencies()
    missing = replace(
        base.provider_mapping,
        outcome=DependencyOutcome.ABSENT,
        candidate_count=0,
        has_visible_knowledge_leaf=False,
        selected_semantic_id=None,
        selected_record_id=None,
    )
    result = evaluate(deps=replace(base, provider_mapping=missing))
    reason = next(item for item in result.reasons if item.reason_code == "provider_mapping_missing")
    assert {item.name for item in reason.evidence.details} == {
        "knowledge_cutoff",
        "market_cutoff",
        "search_scope_hash",
    }


def test_evidence_scalars_and_subject_key_fail_closed():
    with pytest.raises(ValueError, match="canonical base-10"):
        EvidenceValue("count", "integer", "01", "count")
    with pytest.raises(ValueError, match="canonical UTC"):
        EvidenceValue("at", "timestamp", "2026-08-07T15:30:00+05:30", "none")
    evidence = ReasonEvidence(
        "wrong_subject",
        observed=(
            EvidenceValue("availability_basis", "state", "received", "state"),
            EvidenceValue("available_at", "timestamp", M.isoformat(), "none"),
        ),
    )
    with pytest.raises(ValueError, match="subject key mismatch"):
        QualityReasonOccurrence(
            "historical_import_availability",
            "observation",
            TargetKind.FUTURES_QUOTE,
            evidence,
        )


def test_completeness_metadata_corruption_is_not_silently_normalized():
    with pytest.raises(ValueError, match="depth metadata reconciliation"):
        quote(
            provider_depth_levels_present=5,
            normalized_depth_levels=1,
            unadopted_depth_level_count=3,
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        quote(unadopted_schema_paths=("feeds.*.z", "feeds.*.a"))
