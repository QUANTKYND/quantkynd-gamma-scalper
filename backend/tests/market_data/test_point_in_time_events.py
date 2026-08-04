from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import permutations

import pytest

from app.instruments.identity import (
    ExerciseStyle,
    InstrumentType,
    OptionContractIdentity,
    OptionContractVersion,
    OptionSide,
    ProviderContractMapping,
    SettlementType,
    TradingStatus,
    UnderlyingInstrumentIdentity,
)
from app.market_data.point_in_time import (
    AvailabilityBasis,
    ConflictingSemanticIdentityError,
    DataQualityAssessment,
    InvalidCorrectionGraphError,
    MarketEventTime,
    NormalizedMarketEventIdentity,
    PointInTimeOptionQuote,
    PointInTimeQuery,
    QuoteQualityDisposition,
    RawMarketObservationIdentity,
    reconstruct_option_chain,
)


T0 = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def contract(side: OptionSide = OptionSide.CALL, strike: str = "24000") -> OptionContractIdentity:
    underlying = UnderlyingInstrumentIdentity("NSE", "NIFTY50", InstrumentType.INDEX, "INR")
    return OptionContractIdentity(
        exchange="NSE",
        underlying_instrument_id=underlying.instrument_id,
        expiry=date(2026, 8, 27),
        strike=Decimal(strike),
        option_side=side,
        exercise_style=ExerciseStyle.EUROPEAN,
        settlement_type=SettlementType.CASH,
        multiplier=Decimal("75"),
        currency="INR",
    )


def contract_version(option: OptionContractIdentity, **changes) -> OptionContractVersion:
    values = {
        "contract_id": option.contract_id,
        "valid_from": T0,
        "valid_until": None,
        "lot_size": 75,
        "tick_size": Decimal("0.05"),
        "display_symbol": f"NIFTY-{option.strike}-{option.option_side.value}",
        "trading_status": TradingStatus.ACTIVE,
        "catalogue_version_id": "catalogue-v1",
        "recorded_at": T0,
    }
    values.update(changes)
    return OptionContractVersion(**values)


def provider_mapping(version: OptionContractVersion, **changes) -> ProviderContractMapping:
    values = {
        "provider": "upstox",
        "provider_contract_key": f"key-{version.contract_id[-8:]}",
        "contract_version_id": version.version_id,
        "provider_payload_hash": "sha256:" + "a" * 64,
        "source_row_identity": "row-1",
        "effective_from": T0,
        "effective_until": None,
        "recorded_at": T0,
    }
    values.update(changes)
    return ProviderContractMapping(**values)


def quote(
    option: OptionContractIdentity,
    version: OptionContractVersion,
    mapping: ProviderContractMapping,
    sequence: int,
    exchange_at: datetime,
    available_at: datetime,
    *,
    basis: AvailabilityBasis = AvailabilityBasis.RECEIVED,
    supersedes: str | None = None,
) -> PointInTimeOptionQuote:
    raw = RawMarketObservationIdentity(
        provider="upstox",
        content_hash="sha256:" + "b" * 64,
        provider_sequence_scope_id="connection-1",
        provider_sequence=sequence,
    )
    identity = NormalizedMarketEventIdentity(raw.raw_event_id, "option_quote", option.contract_id, 1)
    received_at = available_at if basis is AvailabilityBasis.RECEIVED else None
    return PointInTimeOptionQuote(
        identity=identity,
        contract=option,
        contract_version_id=version.version_id,
        provider_mapping_id=mapping.mapping_id,
        event_time=MarketEventTime(
            exchange_timestamp=exchange_at,
            available_at=available_at,
            recorded_at=available_at,
            received_at=received_at,
            availability_basis=basis,
        ),
        bid_price=Decimal("99"),
        bid_size_contracts=10,
        ask_price=Decimal("101"),
        ask_size_contracts=12,
        provider_sequence=sequence,
        event_order=sequence,
        supersedes_event_id=supersedes,
    )


def assessment(
    event_id: str,
    at: datetime,
    disposition: QuoteQualityDisposition = QuoteQualityDisposition.ACCEPTED,
    run_id: str = "quality-run-1",
) -> DataQualityAssessment:
    return DataQualityAssessment(
        assessment_run_id=run_id,
        event_id=event_id,
        quality_policy_id="quote-policy",
        quality_policy_version=1,
        disposition=disposition,
        reason_codes=(),
        assessed_at=at,
        recorded_at=at,
    )


def query(at: datetime, *, require_defensible: bool = True) -> PointInTimeQuery:
    return PointInTimeQuery(at, at, "quote-policy", 1, require_defensible)


def chain(quotes, versions, mappings, assessments, at, *, require_defensible=True):
    return reconstruct_option_chain(
        quotes,
        versions,
        mappings,
        assessments,
        query(at, require_defensible=require_defensible),
    )


def test_market_event_time_rejects_naive_and_impossible_availability() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketEventTime(
            datetime(2026, 8, 4, 9, 15),
            T0,
            T0,
            T0,
            AvailabilityBasis.RECEIVED,
        )
    with pytest.raises(ValueError, match="available_at cannot precede received_at"):
        MarketEventTime(T0, T0, T0 + timedelta(seconds=1), T0 + timedelta(seconds=1), AvailabilityBasis.RECEIVED)


def test_market_event_time_normalizes_to_utc() -> None:
    india = timezone(timedelta(hours=5, minutes=30))
    event_time = MarketEventTime(
        T0.astimezone(india),
        T0.astimezone(india),
        T0.astimezone(india),
        T0.astimezone(india),
        AvailabilityBasis.RECEIVED,
    )
    assert event_time.exchange_timestamp == T0
    assert event_time.exchange_timestamp.tzinfo is UTC


def test_source_row_reimport_is_idempotent() -> None:
    values = {
        "provider": "archive",
        "content_hash": "sha256:" + "c" * 64,
        "source_file_id": "file-sha256",
        "source_row_id": "42",
    }
    assert RawMarketObservationIdentity(**values).raw_event_id == RawMarketObservationIdentity(**values).raw_event_id


def test_provider_sequence_requires_explicit_scope() -> None:
    with pytest.raises(ValueError, match="explicit provider_sequence_scope_id"):
        RawMarketObservationIdentity("upstox", "same-content", provider_sequence=10)


def test_provider_sequence_identity_includes_explicit_scope() -> None:
    first = RawMarketObservationIdentity("upstox", "same-content", "session-a", provider_sequence=10)
    repeated = RawMarketObservationIdentity("upstox", "different-content", "session-a", provider_sequence=10)
    other_scope = RawMarketObservationIdentity("upstox", "same-content", "session-b", provider_sequence=10)
    assert first.raw_event_id == repeated.raw_event_id
    assert first.raw_event_id != other_scope.raw_event_id


def test_identical_content_transmissions_remain_distinct() -> None:
    first = RawMarketObservationIdentity("upstox", "same-content", "c", provider_sequence=10)
    second = RawMarketObservationIdentity("upstox", "same-content", "c", provider_sequence=11)
    assert first.raw_event_id != second.raw_event_id


def test_content_hash_alone_is_not_a_deduplication_identity() -> None:
    with pytest.raises(ValueError, match="explicit provider, batch, or ingestion"):
        RawMarketObservationIdentity("archive", "same-content")
    first = RawMarketObservationIdentity("archive", "same-content", ingestion_event_id="transmission-1")
    second = RawMarketObservationIdentity("archive", "same-content", ingestion_event_id="transmission-2")
    assert first.raw_event_id != second.raw_event_id


def test_future_contract_and_not_yet_known_mapping_do_not_leak() -> None:
    option = contract()
    later = T0 + timedelta(hours=2)
    version = contract_version(option, valid_from=later, recorded_at=later)
    mapping = provider_mapping(version, effective_from=later, recorded_at=later)
    event = quote(option, version, mapping, 1, later, later)
    assessments = [assessment(event.event_id, later)]
    assert chain([event], [version], [mapping], assessments, T0 + timedelta(hours=1)) == ()
    assert chain([event], [version], [mapping], assessments, later) == (event,)


def test_later_provider_mapping_correction_is_not_visible_early() -> None:
    option = contract()
    first_version = contract_version(option, superseded_at=T0 + timedelta(hours=3))
    first_mapping = provider_mapping(first_version, effective_until=T0 + timedelta(hours=3), superseded_at=T0 + timedelta(hours=3))
    first = quote(option, first_version, first_mapping, 1, T0 + timedelta(hours=1), T0 + timedelta(hours=1))
    corrected_version = contract_version(option, display_symbol="CORRECTED", recorded_at=T0 + timedelta(hours=3))
    corrected_mapping = provider_mapping(
        corrected_version,
        provider_contract_key="corrected-key",
        effective_from=T0,
        recorded_at=T0 + timedelta(hours=3),
    )
    corrected = quote(option, corrected_version, corrected_mapping, 2, T0 + timedelta(hours=1), T0 + timedelta(hours=3))
    assessments = [assessment(first.event_id, T0 + timedelta(hours=1)), assessment(corrected.event_id, T0 + timedelta(hours=3), run_id="quality-run-2")]
    assert chain([first, corrected], [first_version, corrected_version], [first_mapping, corrected_mapping], assessments, T0 + timedelta(hours=2)) == (first,)
    assert chain([first, corrected], [first_version, corrected_version], [first_mapping, corrected_mapping], assessments, T0 + timedelta(hours=4)) == (corrected,)


def test_backfill_requires_explicit_non_defensible_replay_mode() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    imported = quote(
        option,
        version,
        mapping,
        1,
        T0 + timedelta(minutes=5),
        T0 + timedelta(hours=4),
        basis=AvailabilityBasis.HISTORICAL_IMPORT,
    )
    assessments = [assessment(imported.event_id, T0 + timedelta(hours=4))]
    assert chain([imported], [version], [mapping], assessments, T0 + timedelta(hours=3)) == ()
    assert chain([imported], [version], [mapping], assessments, T0 + timedelta(hours=5)) == ()
    assert chain([imported], [version], [mapping], assessments, T0 + timedelta(hours=5), require_defensible=False) == (imported,)


def test_later_correction_supersedes_only_after_it_is_known() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    original = quote(option, version, mapping, 1, T0 + timedelta(minutes=5), T0 + timedelta(minutes=5))
    corrected = quote(
        option,
        version,
        mapping,
        2,
        T0 + timedelta(minutes=5),
        T0 + timedelta(hours=2),
        supersedes=original.event_id,
    )
    assessments = [
        assessment(original.event_id, T0 + timedelta(minutes=5)),
        assessment(corrected.event_id, T0 + timedelta(hours=2), run_id="quality-run-2"),
    ]
    assert chain([original, corrected], [version], [mapping], assessments, T0 + timedelta(hours=1)) == (original,)
    assert chain([original, corrected], [version], [mapping], assessments, T0 + timedelta(hours=3)) == (corrected,)


def test_cross_contract_correction_fails_closed() -> None:
    call = contract()
    put = contract(OptionSide.PUT)
    call_version = contract_version(call)
    put_version = contract_version(put)
    call_mapping = provider_mapping(call_version)
    put_mapping = provider_mapping(put_version)
    call_quote = quote(call, call_version, call_mapping, 1, T0, T0)
    put_quote = quote(put, put_version, put_mapping, 2, T0, T0)
    corrupt = replace(call_quote, supersedes_event_id=put_quote.event_id)
    assessments = [assessment(call_quote.event_id, T0), assessment(put_quote.event_id, T0, run_id="quality-2")]
    with pytest.raises(InvalidCorrectionGraphError, match="different economic contract"):
        chain([put_quote, corrupt], [call_version, put_version], [call_mapping, put_mapping], assessments, T0)


def test_self_supersession_fails_closed() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    original = quote(option, version, mapping, 1, T0, T0)
    corrupt = replace(original, supersedes_event_id=original.event_id)
    with pytest.raises(InvalidCorrectionGraphError, match="cannot supersede itself"):
        chain([corrupt], [version], [mapping], [assessment(original.event_id, T0)], T0)


def test_missing_correction_target_fails_closed() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    source = quote(option, version, mapping, 1, T0, T0, supersedes="sha256:" + "f" * 64)
    with pytest.raises(InvalidCorrectionGraphError, match="no eligible target"):
        chain([source], [version], [mapping], [assessment(source.event_id, T0)], T0)


def test_cross_event_type_correction_fails_closed() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    target = quote(option, version, mapping, 1, T0, T0)
    trade_identity = replace(target.identity, event_type="option_trade")
    target = replace(target, identity=trade_identity)
    source = quote(option, version, mapping, 2, T0, T0, supersedes=target.event_id)
    assessments = [assessment(target.event_id, T0), assessment(source.event_id, T0, run_id="quality-2")]
    with pytest.raises(InvalidCorrectionGraphError, match="different event type"):
        chain([source, target], [version], [mapping], assessments, T0)


def test_correction_cycle_fails_closed() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    first = quote(option, version, mapping, 1, T0, T0)
    second = quote(option, version, mapping, 2, T0, T0)
    first = replace(first, supersedes_event_id=second.event_id)
    second = replace(second, supersedes_event_id=first.event_id)
    assessments = [assessment(first.event_id, T0), assessment(second.event_id, T0, run_id="quality-2")]
    with pytest.raises(InvalidCorrectionGraphError, match="cycle"):
        chain([first, second], [version], [mapping], assessments, T0)


def test_ambiguous_correction_branch_fails_closed_for_every_permutation() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    original = quote(option, version, mapping, 1, T0, T0)
    first = replace(quote(option, version, mapping, 2, T0, T0), supersedes_event_id=original.event_id)
    second = replace(quote(option, version, mapping, 3, T0, T0), supersedes_event_id=original.event_id)
    quotes = (original, first, second)
    assessments = [assessment(item.event_id, T0, run_id=f"quality-{index}") for index, item in enumerate(quotes)]
    messages = set()
    for ordered in permutations(quotes):
        with pytest.raises(InvalidCorrectionGraphError) as error:
            chain(ordered, [version], [mapping], assessments, T0)
        messages.add(str(error.value))
    assert len(messages) == 1


def test_valid_correction_result_is_input_order_invariant() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    original = quote(option, version, mapping, 1, T0, T0)
    corrected = replace(quote(option, version, mapping, 2, T0, T0), supersedes_event_id=original.event_id)
    assessments = [assessment(original.event_id, T0), assessment(corrected.event_id, T0, run_id="quality-2")]
    results = {
        chain(ordered, [version], [mapping], assessments, T0)
        for ordered in permutations((original, corrected))
    }
    assert results == {(corrected,)}


def test_identical_duplicate_records_do_not_change_result() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    event = quote(option, version, mapping, 1, T0, T0)
    assessments = [assessment(event.event_id, T0)]
    assert chain([event], [version, version], [mapping, mapping], assessments, T0) == (event,)


def test_conflicting_contract_versions_fail_independent_of_input_order() -> None:
    option = contract()
    version = contract_version(option)
    conflict = replace(version, recorded_at=T0 + timedelta(seconds=1))
    mapping = provider_mapping(version)
    event = quote(option, version, mapping, 1, T0, T0)
    messages = set()
    for ordered in ((version, conflict), (conflict, version)):
        with pytest.raises(ConflictingSemanticIdentityError) as error:
            chain([event], ordered, [mapping], [assessment(event.event_id, T0)], T0)
        messages.add(str(error.value))
    assert len(messages) == 1


def test_conflicting_provider_mappings_fail_independent_of_input_order() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    conflict = replace(mapping, recorded_at=T0 + timedelta(seconds=1))
    event = quote(option, version, mapping, 1, T0, T0)
    messages = set()
    for ordered in ((mapping, conflict), (conflict, mapping)):
        with pytest.raises(ConflictingSemanticIdentityError) as error:
            chain([event], [version], ordered, [assessment(event.event_id, T0)], T0)
        messages.add(str(error.value))
    assert len(messages) == 1


def test_zero_prices_are_preserved_and_quality_controls_eligibility() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    zero = replace(
        quote(option, version, mapping, 1, T0, T0),
        bid_price=Decimal("0"),
        ask_price=Decimal("0.00"),
        last_price=Decimal("0E-2"),
    )
    accepted = assessment(zero.event_id, T0)
    rejected = assessment(zero.event_id, T0, QuoteQualityDisposition.REJECTED)
    assert zero.bid_price == zero.ask_price == zero.last_price == Decimal("0")
    assert chain([zero], [version], [mapping], [accepted], T0) == (zero,)
    assert chain([zero], [version], [mapping], [rejected], T0) == ()


def test_negative_prices_fail_and_none_remains_distinct_from_zero() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    event = quote(option, version, mapping, 1, T0, T0)
    absent = replace(event, bid_price=None, ask_price=None, last_price=None)
    assert absent.bid_price is None
    assert replace(event, bid_price=Decimal("0")).bid_price == Decimal("0")
    for field_name in ("bid_price", "ask_price", "last_price"):
        with pytest.raises(ValueError, match="non-negative and finite"):
            replace(event, **{field_name: Decimal("-0.01")})


def test_later_quality_reassessment_does_not_rewrite_earlier_result() -> None:
    option = contract()
    version = contract_version(option)
    mapping = provider_mapping(version)
    event = quote(option, version, mapping, 1, T0 + timedelta(minutes=5), T0 + timedelta(minutes=5))
    assessments = [
        assessment(event.event_id, T0 + timedelta(minutes=5)),
        assessment(event.event_id, T0 + timedelta(hours=2), QuoteQualityDisposition.REJECTED, "quality-run-2"),
    ]
    assert chain([event], [version], [mapping], assessments, T0 + timedelta(hours=1)) == (event,)
    assert chain([event], [version], [mapping], assessments, T0 + timedelta(hours=3)) == ()


def test_quote_selection_and_chain_sort_are_deterministic() -> None:
    call = contract(OptionSide.CALL, "24100")
    put = contract(OptionSide.PUT, "24000")
    call_version = contract_version(call)
    put_version = contract_version(put)
    call_mapping = provider_mapping(call_version)
    put_mapping = provider_mapping(put_version)
    call_old = quote(call, call_version, call_mapping, 1, T0 + timedelta(minutes=5), T0 + timedelta(minutes=5))
    call_new = quote(call, call_version, call_mapping, 2, T0 + timedelta(minutes=5), T0 + timedelta(minutes=6))
    put_quote = quote(put, put_version, put_mapping, 3, T0 + timedelta(minutes=4), T0 + timedelta(minutes=4))
    quotes = [call_old, put_quote, call_new]
    assessments = [assessment(item.event_id, item.event_time.available_at, run_id=f"quality-{index}") for index, item in enumerate(quotes)]
    result = chain(quotes, [call_version, put_version], [call_mapping, put_mapping], assessments, T0 + timedelta(hours=1))
    assert result == (put_quote, call_new)


def test_market_as_of_mode_does_not_apply_knowledge_cutoff() -> None:
    point = PointInTimeQuery(T0, None, "quote-policy", 1)
    assert point.mode == "market_as_of"
    assert replace(point, known_as_of=T0).mode == "known_as_of"
