from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import DependencyOutcome, EvaluationContext, ReceiptBasis, TargetKind
from app.market_data.quality.dependency_resolution import RankedCandidate, TemporalCandidate
from app.market_data.quality.evaluator import (
    ConnectionFact,
    MarketStatusFact,
    ProvenanceDependencyFact,
    QualityEvaluationInput,
    QuoteTarget,
    StatusTarget,
    SessionFact,
    SubjectScopeFact,
    SubscriptionFact,
    SubscriptionResolutionState,
    TargetDependencies,
    evaluate_quality,
)
from app.market_data.quality.policy_parser import parse_quality_policy
from app.market_data.quality.ports import (
    AssessmentPlan,
    AssessmentRunPlan,
    AuditCursor,
    CatalogueCandidateReference,
    CatalogueMembershipCandidateReference,
    CatalogueMembershipReceipt,
    CatalogueScope,
    ConnectionScope,
    DATA15_ADVISORY_LOCK_NAMESPACE,
    DEPENDENCY_KIND_ORDER,
    DependencyCandidates,
    DependencyKind,
    InstrumentScope,
    InstrumentVersionCandidateReference,
    LockEntityNamespace,
    LifecycleCandidateReference,
    LockRoot,
    MappingScope,
    MarketDataQualityRepository,
    MarketEventCandidateReference,
    MembershipDependencyCandidate,
    MembershipScope,
    PolicyRegistrationBundle,
    ProviderMappingCandidateReference,
    QualityPolicyBundle,
    RankedDependencyCandidate,
    ReceiptTargetKind,
    SegmentScope,
    SessionScope,
    SubscriptionScope,
    TargetBundle,
    TemporalDependencyCandidate,
    TemporalRecordReceipt,
    TradingSessionCandidateReference,
    WriteFamily,
    data15_lock_stripe,
    derive_data15_lock_stripes,
    plan_assessment_run_writes,
)

M = datetime(2026, 8, 7, 10, tzinfo=UTC)
K = datetime(2026, 8, 7, 11, tzinfo=UTC)
CONTEXT = EvaluationContext(M, K)
ROOT = Path(__file__).resolve().parents[5]
POLICY = parse_quality_policy(
    (ROOT / "config/data_quality/upstox-nse-market-observation-quality-v1.yaml").read_bytes()
)


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


def evaluation_dependencies(provider_timestamp: datetime) -> TargetDependencies:
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
            provider_timestamp=provider_timestamp - timedelta(microseconds=1),
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


def quote(event_seed: str = "event") -> QuoteTarget:
    provider_timestamp = M - timedelta(seconds=1)
    return QuoteTarget(
        event_id=ident(event_seed),
        target_kind=TargetKind.FUTURES_QUOTE,
        provider="upstox",
        provider_contract_key="NSE_FO|123",
        normalization_schema_version=1,
        normalizer_implementation_version="upstox-v3-normalizer-1",
        provider_timestamp=provider_timestamp,
        available_at=provider_timestamp,
        availability_basis="received",
        feed_response_type="live_feed",
        request_mode="full_d5",
        resolution_market_as_of=provider_timestamp,
        resolution_known_as_of=K - timedelta(seconds=1),
        bid_price=Decimal("100.00"),
        bid_size=1,
        ask_price=Decimal("100.05"),
        ask_size=1,
        last_price=Decimal("100.00"),
    )


def target_bundle(event_seed: str = "event") -> TargetBundle:
    target = quote(event_seed)
    return TargetBundle(
        event_id=target.event_id,
        raw_event_id=ident(f"{event_seed}:raw"),
        result_id=ident(f"{event_seed}:result"),
        target=target,
        result_persistence_recorded_at=K - timedelta(minutes=1),
        event_payload_hash=ident(f"{event_seed}:event-payload"),
        result_payload_hash=ident(f"{event_seed}:result-payload"),
        raw_event_payload_hash=ident(f"{event_seed}:raw-payload"),
        connection_session_id="connection-1",
        result_event_ordinal=0,
    )


def _temporal_dependency(
    *,
    event_seed: str,
    context: EvaluationContext,
    target: QuoteTarget,
    kind: DependencyKind,
    subject_key: str,
    scope_payload: dict[str, object],
    semantic_id: str,
    record_id: str,
    reference,
) -> DependencyCandidates:
    candidate = TemporalCandidate(
        record_id=record_id,
        semantic_id=semantic_id,
        scope_id=f"{kind.value}:{event_seed}",
        recorded_at=context.evaluation_market_as_of - timedelta(days=1),
        receipt_at=context.evaluation_market_as_of - timedelta(days=1),
        valid_from=context.evaluation_market_as_of - timedelta(days=10),
        valid_until=None,
        supersedes_record_id=None,
        content_hash=ident(f"{event_seed}:{kind.value}:content"),
        payload={"kind": kind.value, "event_seed": event_seed},
    )
    wrapped = TemporalDependencyCandidate(kind, candidate, reference)
    return DependencyCandidates(
        kind,
        subject_key,
        scope_payload,
        context.dependency_market_as_of(target.provider_timestamp),
        context.evaluation_known_as_of,
        "temporal-successor-graph-with-receipt-v1",
        (wrapped,),
    )


def selected_mapping_candidates(
    event_seed: str = "event",
    context: EvaluationContext = CONTEXT,
    target: QuoteTarget | None = None,
) -> DependencyCandidates:
    value = target or quote(event_seed)
    scope = MappingScope("upstox", value.provider_contract_key)
    record_id = ident(f"{event_seed}:mapping-record")
    mapping_id = ident(f"{event_seed}:mapping")
    return _temporal_dependency(
        event_seed=event_seed,
        context=context,
        target=value,
        kind=DependencyKind.PROVIDER_MAPPING,
        subject_key="provider_mapping",
        scope_payload=scope.canonical_payload,
        semantic_id=mapping_id,
        record_id=record_id,
        reference=ProviderMappingCandidateReference(record_id, mapping_id),
    )


def selected_dependency_drafts(
    event_seed: str,
    context: EvaluationContext,
    target: QuoteTarget,
):
    market_cutoff = context.dependency_market_as_of(target.provider_timestamp)
    known_cutoff = context.evaluation_known_as_of

    mapping = selected_mapping_candidates(event_seed, context, target)

    instrument_id = ident(f"{event_seed}:instrument-id")
    instrument_record = ident(f"{event_seed}:instrument-record")
    instrument_version = ident(f"{event_seed}:instrument-version")
    instrument = _temporal_dependency(
        event_seed=event_seed,
        context=context,
        target=target,
        kind=DependencyKind.INSTRUMENT_VERSION,
        subject_key="instrument_version",
        scope_payload=InstrumentScope(instrument_id).canonical_payload,
        semantic_id=instrument_version,
        record_id=instrument_record,
        reference=InstrumentVersionCandidateReference(
            instrument_record, instrument_version
        ),
    )

    catalogue_record = ident(f"{event_seed}:catalogue-record")
    catalogue_version = ident(f"{event_seed}:catalogue-version")
    catalogue_run = ident(f"{event_seed}:catalogue-run")
    catalogue = _temporal_dependency(
        event_seed=event_seed,
        context=context,
        target=target,
        kind=DependencyKind.CATALOGUE_VERSION,
        subject_key="catalogue_version",
        scope_payload=CatalogueScope("upstox").canonical_payload,
        semantic_id=catalogue_version,
        record_id=catalogue_record,
        reference=CatalogueCandidateReference(
            catalogue_record, catalogue_version, catalogue_run
        ),
    )

    membership_id = ident(f"{event_seed}:membership")
    membership_scope = MembershipScope(
        catalogue_version,
        target.provider_contract_key,
        instrument_id,
        instrument_version,
        market_cutoff,
        known_cutoff,
    )
    membership_candidate = MembershipDependencyCandidate(
        DependencyKind.CATALOGUE_MEMBERSHIP,
        membership_id,
        market_cutoff - timedelta(days=1),
        ident(f"{event_seed}:membership-content"),
        {"profile": "upstox-nse-nifty-index-derivatives-v1"},
        CatalogueMembershipCandidateReference(membership_id, catalogue_run),
    )
    membership = DependencyCandidates(
        DependencyKind.CATALOGUE_MEMBERSHIP,
        "catalogue_membership",
        membership_scope.canonical_payload,
        market_cutoff,
        known_cutoff,
        "catalogue-membership-profile-v1",
        (membership_candidate,),
    )

    exchange_date = market_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date()
    session_record = ident(f"{event_seed}:session-record")
    session_version = ident(f"{event_seed}:session-version")
    session_scope = SessionScope("NSE", exchange_date, "regular", market_cutoff)
    session = _temporal_dependency(
        event_seed=event_seed,
        context=context,
        target=target,
        kind=DependencyKind.TRADING_SESSION,
        subject_key="trading_session",
        scope_payload=session_scope.canonical_payload,
        semantic_id=session_version,
        record_id=session_record,
        reference=TradingSessionCandidateReference(session_record, session_version),
    )

    status_event = ident(f"{event_seed}:status-event")
    status_ranked = RankedCandidate(
        status_event,
        market_cutoff - timedelta(microseconds=1),
        f"{event_seed}:status-scope",
        1,
        ident(f"{event_seed}:status-content"),
        {"status": "NORMAL_OPEN"},
    )
    status = DependencyCandidates(
        DependencyKind.MARKET_SEGMENT_STATUS,
        "market_segment_status",
        SegmentScope("upstox", "NSE_FO").canonical_payload,
        market_cutoff,
        known_cutoff,
        "ranked-market-status-v1",
        (
            RankedDependencyCandidate(
                DependencyKind.MARKET_SEGMENT_STATUS,
                status_ranked,
                market_cutoff - timedelta(microseconds=1),
                known_cutoff - timedelta(microseconds=1),
                MarketEventCandidateReference(
                    status_event,
                    ident(f"{event_seed}:status-result"),
                    ident(f"{event_seed}:status-raw"),
                ),
            ),
        ),
    )

    connection_event = ident(f"{event_seed}:connection-event")
    connection = DependencyCandidates(
        DependencyKind.CONNECTION_SESSION,
        "connection_session",
        ConnectionScope("upstox", "connection-1").canonical_payload,
        market_cutoff,
        known_cutoff,
        "ranked-connection-lifecycle-v1",
        (
            RankedDependencyCandidate(
                DependencyKind.CONNECTION_SESSION,
                RankedCandidate(
                    connection_event,
                    market_cutoff - timedelta(minutes=1),
                    f"{event_seed}:connection-scope",
                    1,
                    ident(f"{event_seed}:connection-content"),
                    {"state": "authorized"},
                ),
                market_cutoff - timedelta(minutes=1),
                known_cutoff - timedelta(microseconds=1),
                LifecycleCandidateReference(
                    connection_event,
                    "connection",
                    ident(f"{event_seed}:connection-batch"),
                ),
            ),
        ),
    )

    subscription_event = ident(f"{event_seed}:subscription-event")
    instrument_set_digest = ident(f"{event_seed}:instrument-set")
    subscription = DependencyCandidates(
        DependencyKind.SUBSCRIPTION_SCOPE,
        "subscription_scope",
        SubscriptionScope(
            "upstox",
            "connection-1",
            target.provider_contract_key,
            target.request_mode,
        ).canonical_payload,
        market_cutoff,
        known_cutoff,
        "staged-subscription-scope-v1",
        (
            RankedDependencyCandidate(
                DependencyKind.SUBSCRIPTION_SCOPE,
                RankedCandidate(
                    subscription_event,
                    market_cutoff - timedelta(minutes=1),
                    f"{event_seed}:subscription-scope",
                    1,
                    ident(f"{event_seed}:subscription-content"),
                    {"state": "subscribed", "mode": target.request_mode},
                ),
                market_cutoff - timedelta(minutes=1),
                known_cutoff - timedelta(microseconds=1),
                LifecycleCandidateReference(
                    subscription_event,
                    "subscription",
                    ident(f"{event_seed}:subscription-batch"),
                    instrument_set_digest,
                ),
            ),
        ),
    )

    candidate_sets = (
        mapping,
        instrument,
        catalogue,
        membership,
        session,
        status,
        connection,
        subscription,
    )
    return tuple(
        (candidate_set, DependencyOutcome.SELECTED, candidate_set.candidates[0].candidate_id)
        for candidate_set in candidate_sets
    )

def status_target_bundle(event_seed: str = "status-target") -> TargetBundle:
    provider_timestamp = M - timedelta(seconds=1)
    target = StatusTarget(
        event_id=ident(event_seed),
        provider="upstox",
        segment="NSE_FO",
        normalization_schema_version=1,
        normalizer_implementation_version="upstox-v3-normalizer-1",
        provider_timestamp=provider_timestamp,
        available_at=provider_timestamp,
        availability_basis="received",
        status_is_known=True,
        status_name="NORMAL_OPEN",
    )
    return TargetBundle(
        event_id=target.event_id,
        raw_event_id=ident(f"{event_seed}:raw"),
        result_id=ident(f"{event_seed}:result"),
        target=target,
        result_persistence_recorded_at=K - timedelta(minutes=1),
        event_payload_hash=ident(f"{event_seed}:event-payload"),
        result_payload_hash=ident(f"{event_seed}:result-payload"),
        raw_event_payload_hash=ident(f"{event_seed}:raw-payload"),
        connection_session_id="connection-1",
        result_event_ordinal=0,
    )


def status_assessment(event_seed: str = "status-target") -> AssessmentPlan:
    target = status_target_bundle(event_seed)
    all_dependencies = evaluation_dependencies(target.target.provider_timestamp)
    result = evaluate_quality(
        QualityEvaluationInput(
            POLICY,
            CONTEXT,
            target.target,
            TargetDependencies(
                trading_session=all_dependencies.trading_session,
                connection=all_dependencies.connection,
            ),
        )
    )
    quote_drafts = selected_dependency_drafts(event_seed, CONTEXT, quote(event_seed))
    status_drafts = tuple(
        item
        for item in quote_drafts
        if item[0].dependency_kind
        in {DependencyKind.TRADING_SESSION, DependencyKind.CONNECTION_SESSION}
    )
    return AssessmentPlan.build(
        policy=policy_bundle(),
        context=CONTEXT,
        target=target,
        evaluation=result,
        dependency_candidates=status_drafts,
    )


def policy_bundle(registered_at: datetime = K - timedelta(days=1)) -> QualityPolicyBundle:
    return QualityPolicyBundle(POLICY, registered_at, (POLICY.source_artifact_id,))


def assessment(
    event_seed: str = "event",
    *,
    registered_at: datetime = K - timedelta(days=1),
    context: EvaluationContext = CONTEXT,
) -> AssessmentPlan:
    target = target_bundle(event_seed)
    result = evaluate_quality(
        QualityEvaluationInput(
            POLICY,
            context,
            target.target,
            evaluation_dependencies(target.target.provider_timestamp),
        )
    )
    return AssessmentPlan.build(
        policy=policy_bundle(registered_at),
        context=context,
        target=target,
        evaluation=result,
        dependency_candidates=selected_dependency_drafts(
            event_seed, context, target.target
        ),
    )


def test_receipts_freeze_bootstrap_and_repository_insert_shapes():
    bootstrap = TemporalRecordReceipt(
        ReceiptTargetKind.PROVIDER_MAPPING_RECORD,
        ident("record"),
        K,
        ReceiptBasis.LEGACY_BOOTSTRAP,
        "20260804_05",
    )
    assert bootstrap.canonical_payload_hash == stable_hash(bootstrap.canonical_payload)
    direct = CatalogueMembershipReceipt(
        ident("membership"),
        ident("run"),
        K,
        ReceiptBasis.REPOSITORY_INSERT,
    )
    assert direct.bootstrap_revision is None
    with pytest.raises(ValueError):
        replace(bootstrap, bootstrap_revision=None)
    with pytest.raises(ValueError):
        replace(direct, bootstrap_revision="20260804_05")


def test_scope_hashes_bind_all_query_material_and_membership_cutoff():
    first = MembershipScope(
        ident("catalogue"),
        "NSE_FO|123",
        ident("subject"),
        ident("version"),
        M,
        K,
    )
    second = replace(first, knowledge_cutoff=K + timedelta(microseconds=1))
    assert first.search_scope_hash == second.search_scope_hash
    assert first.knowledge_cutoff != second.knowledge_cutoff
    assert MappingScope("upstox", "NSE_FO|123").search_scope_hash == stable_hash(
        MappingScope("upstox", "NSE_FO|123").canonical_payload
    )




def test_membership_and_session_scopes_carry_cutoffs_outside_semantic_scope_hash():
    membership = MembershipScope(
        ident("catalogue-cutoff"),
        "NSE_FO|123",
        ident("subject-cutoff"),
        ident("version-cutoff"),
        M,
        K,
    )
    assert "market_cutoff" not in membership.canonical_payload
    assert "knowledge_cutoff" not in membership.canonical_payload
    with pytest.raises(ValueError, match="cannot precede"):
        replace(membership, knowledge_cutoff=M - timedelta(microseconds=1))

    expected_date = M.astimezone(ZoneInfo("Asia/Kolkata")).date()
    session = SessionScope("NSE", expected_date, "regular", M)
    assert session.market_cutoff == M
    with pytest.raises(ValueError, match="derived"):
        replace(session, session_date=expected_date + timedelta(days=1))

def test_temporal_candidate_contract_is_receipt_aware_and_canonically_sorted():
    selected = selected_mapping_candidates()
    assert selected.candidate_set_hash == stable_hash(
        tuple(item.canonical_payload for item in selected.candidates)
    )
    late = replace(
        selected.candidates[0].candidate,
        receipt_at=K + timedelta(microseconds=1),
    )
    with pytest.raises(ValueError, match="receipt"):
        replace(
            selected,
            candidates=(
                TemporalDependencyCandidate(
                    DependencyKind.PROVIDER_MAPPING,
                    late,
                    selected.candidates[0].reference,
                ),
            ),
        )


def test_temporal_reference_must_bind_record_and_semantic_identity():
    selected = selected_mapping_candidates()
    wrapped = selected.candidates[0]
    with pytest.raises(ValueError, match="semantic"):
        replace(
            wrapped,
            reference=ProviderMappingCandidateReference(
                wrapped.candidate.record_id,
                ident("different-mapping"),
            ),
        )


def test_ranked_candidates_reject_post_cutoff_market_or_knowledge_state():
    event_id = ident("status-event-candidate")
    ranked = RankedCandidate(
        event_id,
        M,
        "status-scope",
        1,
        ident("status-content"),
        {"state": "NORMAL_OPEN"},
    )
    wrapped = RankedDependencyCandidate(
        DependencyKind.MARKET_SEGMENT_STATUS,
        ranked,
        M,
        K - timedelta(seconds=1),
        MarketEventCandidateReference(event_id, ident("result"), ident("raw")),
    )
    scope = SegmentScope("upstox", "NSE_FO")
    valid = DependencyCandidates(
        DependencyKind.MARKET_SEGMENT_STATUS,
        "market_segment_status",
        scope.canonical_payload,
        M,
        K,
        "ranked-market-status-v1",
        (wrapped,),
    )
    assert len(valid.candidates) == 1
    with pytest.raises(ValueError, match="market cutoff"):
        replace(valid, market_cutoff=M - timedelta(microseconds=1))
    with pytest.raises(ValueError, match="knowledge cutoff"):
        replace(valid, knowledge_cutoff=K - timedelta(minutes=2))




def test_lifecycle_candidate_references_enforce_connection_and_subscription_shapes():
    event_id = ident("lifecycle-event")
    ranked = RankedCandidate(
        event_id,
        M,
        "lifecycle-scope",
        1,
        ident("lifecycle-content"),
        {"state": "authorized"},
    )
    with pytest.raises(ValueError, match="connection candidate"):
        RankedDependencyCandidate(
            DependencyKind.CONNECTION_SESSION,
            ranked,
            M,
            K,
            LifecycleCandidateReference(
                event_id,
                "subscription",
                ident("batch"),
                ident("instrument-set"),
            ),
        )
    with pytest.raises(ValueError, match="subscription candidate"):
        RankedDependencyCandidate(
            DependencyKind.SUBSCRIPTION_SCOPE,
            ranked,
            M,
            K,
            LifecycleCandidateReference(event_id, "subscription", ident("batch")),
        )

def test_dependency_contract_rejects_wrong_rule_subject_or_scope_kind():
    selected = selected_mapping_candidates()
    with pytest.raises(ValueError, match="selection_rule_version"):
        replace(selected, selection_rule_version="ranked-market-status-v1")
    with pytest.raises(ValueError, match="subject_key"):
        replace(selected, subject_key="instrument_version")
    with pytest.raises(ValueError, match="search scope"):
        replace(
            selected,
            search_scope_payload=SegmentScope("upstox", "NSE_FO").canonical_payload,
        )


def test_lock_namespace_and_frozen_stripe_vectors():
    assert DATA15_ADVISORY_LOCK_NAMESPACE == -806150233
    assert data15_lock_stripe(
        LockEntityNamespace.POLICY_VERSION,
        "sha256:" + "0" * 64,
    ) == 125
    assert data15_lock_stripe(
        LockEntityNamespace.ASSESSMENT,
        "sha256:" + "1" * 64,
    ) == 76
    assert data15_lock_stripe(
        LockEntityNamespace.ASSESSMENT_RUN,
        "sha256:" + "2" * 64,
    ) == 83


def test_lock_stripes_are_deduplicated_and_sorted():
    roots = (
        LockRoot(LockEntityNamespace.ASSESSMENT, ident("a")),
        LockRoot(LockEntityNamespace.ASSESSMENT, ident("a")),
        LockRoot(LockEntityNamespace.ASSESSMENT_RUN, ident("run")),
    )
    stripes = derive_data15_lock_stripes(roots)
    assert stripes == tuple(sorted(set(stripes)))


def test_policy_registration_bundle_separates_semantics_from_source_artifact():
    bundle = PolicyRegistrationBundle(POLICY)
    assert bundle.canonical_payload["policy_definition_hash"] == POLICY.policy_definition_hash
    assert bundle.canonical_payload["source_artifact_id"] == POLICY.source_artifact_id
    assert len(bundle.canonical_payload["reason_definitions"]) == 69
    assert bundle.bundle_hash == stable_hash(bundle.canonical_payload)


def test_target_bundle_binds_exact_event_result_raw_and_persistence_clock():
    bundle = target_bundle()
    assert bundle.target_kind is TargetKind.FUTURES_QUOTE
    assert bundle.canonical_payload_hash == stable_hash(bundle.canonical_payload)
    with pytest.raises(ValueError, match="event identity"):
        replace(bundle, event_id=ident("other-event"))
    with pytest.raises(ValueError, match="persistence"):
        replace(bundle, result_persistence_recorded_at=bundle.target.available_at - timedelta(microseconds=1))


def test_assessment_plan_binds_identity_reasons_dependencies_and_counterfactual_flag():
    plan = assessment(registered_at=K + timedelta(microseconds=1))
    assert plan.policy_registered_after_known_as_of is True
    assert plan.assessment_id == plan.canonical_payload["assessment_id"]
    assert plan.reason_set_hash == plan.evaluation.reason_set_hash
    assert tuple(item.dependency_kind for item in plan.dependencies) == DEPENDENCY_KIND_ORDER
    assert plan.dependencies[0].selected_candidate_ordinal == 0
    assert plan.dependency_closure_hash == stable_hash(
        tuple(item.canonical_payload for item in plan.dependencies)
    )


def test_status_assessment_has_only_session_and_connection_dependencies():
    plan = status_assessment()
    assert {item.dependency_kind for item in plan.dependencies} == {
        DependencyKind.TRADING_SESSION,
        DependencyKind.CONNECTION_SESSION,
    }


def test_assessment_plan_rejects_non_applicable_or_mismatched_dependency_cutoffs():
    target = target_bundle("applicability")
    result = evaluate_quality(
        QualityEvaluationInput(
            POLICY,
            CONTEXT,
            target.target,
            evaluation_dependencies(target.target.provider_timestamp),
        )
    )
    drafts = selected_dependency_drafts("applicability", CONTEXT, target.target)
    missing = tuple(
        item for item in drafts if item[0].dependency_kind is not DependencyKind.SUBSCRIPTION_SCOPE
    )
    with pytest.raises(ValueError, match="applicability"):
        AssessmentPlan.build(
            policy=policy_bundle(),
            context=CONTEXT,
            target=target,
            evaluation=result,
            dependency_candidates=missing,
        )

    first, *rest = drafts
    shifted = replace(
        first[0],
        market_cutoff=first[0].market_cutoff - timedelta(microseconds=1),
    )
    with pytest.raises(ValueError, match="cutoffs"):
        AssessmentPlan.build(
            policy=policy_bundle(),
            context=CONTEXT,
            target=target,
            evaluation=result,
            dependency_candidates=((shifted, first[1], first[2]), *rest),
        )


def test_assessment_run_identity_and_memberships_ignore_input_order():
    left = assessment("event-a")
    right = assessment("event-b")
    first = AssessmentRunPlan.build((right, left))
    second = AssessmentRunPlan.build((left, right))
    assert first == second
    assert first.ordered_target_event_ids == tuple(sorted(first.ordered_target_event_ids))
    assert tuple(item.target_ordinal for item in first.memberships) == (0, 1)
    assert first.complete_plan_hash == second.complete_plan_hash


def test_assessment_run_rejects_mixed_contexts_or_policy_versions():
    left = assessment("event-a")
    right = assessment("event-b")
    other_context = EvaluationContext(M, K + timedelta(microseconds=1))
    right_other = assessment("event-b", context=other_context)
    with pytest.raises(ValueError, match="contexts"):
        AssessmentRunPlan.build((left, right_other))


def test_bulk_write_planning_reuses_parameter_budget_and_caps_at_1000():
    run = AssessmentRunPlan.build((assessment("event-a"), assessment("event-b")))
    params = {
        WriteFamily.ASSESSMENTS: 21,
        WriteFamily.REASONS: 11,
        WriteFamily.DEPENDENCIES: 16,
        WriteFamily.CANDIDATES: 21,
        WriteFamily.MEMBERSHIPS: 4,
    }
    plans = plan_assessment_run_writes(run, params)
    assert tuple(item.family for item in plans) == tuple(WriteFamily)
    assert all(chunk.size <= 1000 for item in plans for chunk in item.chunks)
    with pytest.raises(ValueError, match="every write family"):
        plan_assessment_run_writes(run, {WriteFamily.ASSESSMENTS: 21})
    oversized = dict(params)
    oversized[WriteFamily.CANDIDATES] = 60001
    with pytest.raises(ValueError, match="1..60000"):
        plan_assessment_run_writes(run, oversized)


def test_protocol_has_exact_queries_and_no_implicit_latest_api():
    names = set(MarketDataQualityRepository.__dict__)
    required = {
        "register_policy_bundle",
        "get_policy_bundle",
        "load_visible_targets",
        "list_provider_mapping_candidates",
        "list_instrument_version_candidates",
        "list_catalogue_candidates",
        "list_catalogue_membership_candidates",
        "list_trading_session_candidates",
        "list_segment_status_candidates",
        "list_connection_candidates",
        "list_subscription_scope_candidates",
        "acquire_write_locks",
        "persist_assessment_run",
        "get_assessment_exact",
        "list_assessments_for_audit",
        "reconstruct_run",
    }
    assert required <= names
    assert not any(
        forbidden in name
        for name in names
        for forbidden in ("latest", "current_policy", "option_chain")
    )


def test_audit_cursor_requires_exact_schema_and_canonical_position():
    cursor = AuditCursor(position=ident("position"))
    assert cursor.schema_version == 1
    with pytest.raises(ValueError):
        AuditCursor(schema_version=2)
    with pytest.raises(ValueError):
        AuditCursor(position="not-a-hash")


def test_connection_and_subscription_scope_hashes_bind_target_material():
    connection = ConnectionScope("upstox", "connection-1")
    subscription = SubscriptionScope(
        "upstox", "connection-1", "NSE_FO|123", "full_d5"
    )
    assert connection.search_scope_hash != subscription.search_scope_hash
    assert replace(subscription, request_mode="ltpc").search_scope_hash != subscription.search_scope_hash
