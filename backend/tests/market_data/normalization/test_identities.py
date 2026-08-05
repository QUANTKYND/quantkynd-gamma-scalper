from dataclasses import replace
from datetime import timedelta

import pytest

from app.market_data.normalization.enums import RawCaptureBasis
from app.market_data.normalization.errors import ConflictingRawIdentityError, RawFrameValidationError
from app.market_data.normalization.identities import validate_raw_frame_identity_batch
from app.market_data.normalization.limits import MAX_SOURCE_ORDER
from tests.market_data.normalization.helpers import AT, raw_frame


def test_raw_frame_identity_excludes_content_hash() -> None:
    first = raw_frame(b"first")
    second = raw_frame(b"second")
    assert first.raw_event_id == second.raw_event_id
    with pytest.raises(ConflictingRawIdentityError):
        validate_raw_frame_identity_batch((first, second))


def test_raw_frame_batch_distinguishes_duplicate_and_independent_same_content() -> None:
    first = raw_frame(b"same", source_order=1)
    independent = raw_frame(b"same", source_order=2)
    result = validate_raw_frame_identity_batch((first, first, independent))
    assert result.exact_duplicate_raw_event_ids == (first.raw_event_id,)
    assert result.independent_same_content_hashes == (first.frame_content_hash,)
    assert len(result.unique_frames) == 2


def test_raw_frame_time_and_capture_invariants() -> None:
    frame = raw_frame(b"frame")
    with pytest.raises(RawFrameValidationError, match="recorded_at"):
        replace(frame, recorded_at=AT - timedelta(seconds=1))
    with pytest.raises(RawFrameValidationError, match="equal receipt"):
        replace(frame, available_at=AT + timedelta(seconds=1), recorded_at=AT + timedelta(seconds=1))
    with pytest.raises(RawFrameValidationError, match="historical_import"):
        replace(frame, capture_basis=RawCaptureBasis.HISTORICAL_IMPORT)
    with pytest.raises(RawFrameValidationError, match="timezone-aware"):
        replace(frame, available_at=AT.replace(tzinfo=None))


def test_source_file_and_record_identity_are_paired() -> None:
    with pytest.raises(RawFrameValidationError, match="appear together"):
        replace(raw_frame(b"frame"), source_file_id="file")


def test_all_capture_bases_enforce_receipt_semantics() -> None:
    live = raw_frame(b"frame")
    recorded = replace(live, capture_basis=RawCaptureBasis.RECORDED_WITH_ORIGINAL_RECEIPT)
    assert recorded.received_at == recorded.available_at
    historical = replace(
        live,
        capture_basis=RawCaptureBasis.HISTORICAL_IMPORT,
        received_at=None,
        source_file_id="file-1",
        source_record_id="row-1",
    )
    assert historical.received_at is None
    with pytest.raises(RawFrameValidationError, match="recorded_with_original_receipt"):
        replace(recorded, received_at=None)
    with pytest.raises(RawFrameValidationError, match="recorded_with_original_receipt"):
        replace(
            recorded,
            available_at=AT + timedelta(seconds=1),
            recorded_at=AT + timedelta(seconds=1),
        )
    with pytest.raises(RawFrameValidationError, match="historical_import"):
        replace(historical, received_at=AT)


def test_historical_source_identity_preserves_approved_optional_pair_rule() -> None:
    historical = replace(
        raw_frame(b"frame"),
        capture_basis=RawCaptureBasis.HISTORICAL_IMPORT,
        received_at=None,
    )
    assert historical.source_file_id is None
    assert historical.source_record_id is None


def test_raw_frame_source_order_uses_signed_bigint_boundary() -> None:
    assert replace(raw_frame(b"frame"), source_order=MAX_SOURCE_ORDER).source_order == MAX_SOURCE_ORDER
    with pytest.raises(RawFrameValidationError, match="signed 64-bit"):
        replace(raw_frame(b"frame"), source_order=MAX_SOURCE_ORDER + 1)


@pytest.mark.parametrize(
    "field",
    ("provider_schema_id", "connection_session_id", "source_order_scope_id"),
)
def test_raw_frame_identity_strings_use_utf8_byte_boundary(field) -> None:
    accepted = replace(raw_frame(b"frame"), **{field: "é" * 256})
    assert getattr(accepted, field) == "é" * 256
    with pytest.raises(RawFrameValidationError, match="UTF-8 byte limit"):
        replace(raw_frame(b"frame"), **{field: "é" * 257})


@pytest.mark.parametrize("field", ("source_file_id", "source_record_id"))
def test_historical_source_strings_use_utf8_byte_boundary(field) -> None:
    values = {"source_file_id": "file", "source_record_id": "record", field: "é" * 256}
    accepted = replace(
        raw_frame(b"frame"),
        capture_basis=RawCaptureBasis.HISTORICAL_IMPORT,
        received_at=None,
        **values,
    )
    assert getattr(accepted, field) == "é" * 256
    with pytest.raises(RawFrameValidationError, match="UTF-8 byte limit"):
        replace(accepted, **{field: "é" * 257})
