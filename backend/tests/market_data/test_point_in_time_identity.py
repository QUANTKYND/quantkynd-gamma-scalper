from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.hashing import canonical_json, stable_hash
from app.instruments.identity import (
    ExerciseStyle,
    OptionContractIdentity,
    OptionContractVersion,
    OptionSide,
    ProviderContractMapping,
    SettlementType,
    TradingStatus,
    UnderlyingInstrumentIdentity,
    InstrumentType,
)


NOW = datetime(2026, 8, 4, 4, 0, tzinfo=UTC)


def underlying() -> UnderlyingInstrumentIdentity:
    return UnderlyingInstrumentIdentity("NSE", "NIFTY50", InstrumentType.INDEX, "INR")


def option(**changes) -> OptionContractIdentity:
    values = {
        "exchange": "NSE",
        "underlying_instrument_id": underlying().instrument_id,
        "expiry": date(2026, 8, 27),
        "strike": Decimal("24000"),
        "option_side": OptionSide.CALL,
        "exercise_style": ExerciseStyle.EUROPEAN,
        "settlement_type": SettlementType.CASH,
        "multiplier": Decimal("75"),
        "currency": "INR",
    }
    values.update(changes)
    return OptionContractIdentity(**values)


def version(contract: OptionContractIdentity, **changes) -> OptionContractVersion:
    values = {
        "contract_id": contract.contract_id,
        "valid_from": NOW,
        "valid_until": None,
        "lot_size": 75,
        "tick_size": Decimal("0.05"),
        "display_symbol": "NIFTY26AUG24000CE",
        "trading_status": TradingStatus.ACTIVE,
        "catalogue_version_id": "catalogue-2026-08-04",
        "recorded_at": NOW,
    }
    values.update(changes)
    return OptionContractVersion(**values)


def mapping(contract_version: OptionContractVersion, provider: str, key: str) -> ProviderContractMapping:
    return ProviderContractMapping(
        provider=provider,
        provider_contract_key=key,
        contract_version_id=contract_version.version_id,
        provider_payload_hash="sha256:" + "a" * 64,
        source_row_identity="row-1",
        effective_from=NOW,
        effective_until=None,
        recorded_at=NOW,
    )


def test_option_economic_identity_is_deterministic_and_canonical() -> None:
    first = option(strike=Decimal("24000.00"), multiplier=Decimal("75.0"))
    second = option(strike=Decimal("2.4000E+4"), multiplier=Decimal("75"))
    assert first.contract_id == second.contract_id
    assert first.contract_id == option().contract_id


def test_economic_identity_changes_for_side_expiry_and_strike() -> None:
    baseline = option()
    assert baseline.contract_id != option(option_side=OptionSide.PUT).contract_id
    assert baseline.contract_id != option(expiry=date(2026, 9, 3)).contract_id
    assert baseline.contract_id != option(strike=Decimal("24100")).contract_id


def test_provider_identity_does_not_change_economic_identity() -> None:
    contract = option()
    contract_version = version(contract)
    upstox = mapping(contract_version, "upstox", "NSE_FO|123")
    other = mapping(contract_version, "other", "OPT-456")
    changed_key = mapping(contract_version, "upstox", "NSE_FO|999")
    assert upstox.contract_version_id == other.contract_version_id == contract_version.version_id
    assert changed_key.contract_version_id == contract_version.version_id
    assert len({upstox.mapping_id, other.mapping_id, changed_key.mapping_id}) == 3


def test_trading_metadata_changes_version_not_economic_contract() -> None:
    contract = option()
    original = version(contract)
    changed = replace(original, tick_size=Decimal("0.10"))
    assert original.contract_id == changed.contract_id == contract.contract_id
    assert original.version_id != changed.version_id


def test_canonical_serialization_sorts_mappings_and_sets() -> None:
    left = {"providers": {"other", "upstox"}, "strike": Decimal("24000.00")}
    right = {"strike": Decimal("2.4E+4"), "providers": {"upstox", "other"}}
    assert canonical_json(left) == canonical_json(right)
    assert stable_hash(left) == stable_hash(right)
    assert stable_hash({"value": Decimal("-0.00")}) == stable_hash({"value": 0})


def test_canonical_timestamps_are_utc_normalized() -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    assert stable_hash({"at": NOW}) == stable_hash({"at": NOW.astimezone(offset)})


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), float("nan")])
def test_canonical_serialization_rejects_nonfinite_values(value) -> None:
    with pytest.raises(ValueError, match="finite"):
        stable_hash({"value": value})


def test_canonical_serialization_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        stable_hash({"at": datetime(2026, 8, 4, 4, 0)})


def test_domain_decimal_boundaries_reject_float() -> None:
    with pytest.raises(TypeError, match="strike must be Decimal"):
        option(strike=24000.0)


def test_invalid_validity_and_system_intervals_fail() -> None:
    contract = option()
    with pytest.raises(ValueError, match="valid_until"):
        version(contract, valid_until=NOW)
    with pytest.raises(ValueError, match="superseded_at"):
        version(contract, superseded_at=NOW)


def test_contract_version_effective_and_system_time_eligibility() -> None:
    contract_version = version(
        option(),
        valid_from=NOW + timedelta(hours=1),
        valid_until=NOW + timedelta(hours=3),
        recorded_at=NOW + timedelta(minutes=30),
        superseded_at=NOW + timedelta(hours=4),
    )
    assert not contract_version.effective_at(NOW, NOW + timedelta(hours=1))
    assert contract_version.effective_at(NOW + timedelta(hours=2), NOW + timedelta(hours=1))
    assert not contract_version.effective_at(NOW + timedelta(hours=3), NOW + timedelta(hours=3))
    assert not contract_version.effective_at(NOW + timedelta(hours=2), NOW + timedelta(hours=4))
