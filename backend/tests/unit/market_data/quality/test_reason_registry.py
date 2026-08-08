from app.market_data.quality.contracts import QualitySeverity, TargetKind
from app.market_data.quality.reason_registry import (
    REASON_REGISTRY,
    REASONS_BY_CODE,
    validate_reason_registry,
)


def test_registry_is_exactly_contiguous_and_unique() -> None:
    validate_reason_registry()
    assert len(REASON_REGISTRY) == 69
    assert [item.ordinal for item in REASON_REGISTRY] == list(range(1, 70))
    assert len(REASONS_BY_CODE) == 69


def test_warning_and_error_boundary() -> None:
    assert REASON_REGISTRY[8].severity is QualitySeverity.WARNING
    assert REASON_REGISTRY[9].severity is QualitySeverity.ERROR


def test_selected_frozen_definitions() -> None:
    future = REASONS_BY_CODE["provider_timestamp_in_future"]
    assert future.ordinal == 13
    assert future.subject_keys == ("observation",)
    assert future.evidence_profile == "future_offset"

    ambiguous = REASONS_BY_CODE["ambiguous_active_subscription"]
    assert ambiguous.ordinal == 69
    assert ambiguous.applicable_target_kinds == {
        TargetKind.UNDERLYING_QUOTE,
        TargetKind.FUTURES_QUOTE,
        TargetKind.OPTION_QUOTE,
    }


def test_reason_payload_hash_is_stable() -> None:
    assert REASONS_BY_CODE["market_locked"].canonical_payload_hash.startswith("sha256:")
    assert len(REASONS_BY_CODE["market_locked"].canonical_payload_hash) == 71
