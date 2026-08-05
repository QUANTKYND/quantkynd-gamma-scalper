from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

from app.instruments.identity import (
    ExerciseStyle,
    FuturesContractIdentity,
    FuturesContractVersion,
    InstrumentType,
    OptionContractIdentity,
    OptionContractVersion,
    OptionSide,
    SettlementType,
    TradingStatus,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.market_data.normalization.enums import MarketSubjectKind, RawCaptureBasis
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.normalization.models import ResolvedMarketSubjectV1
from app.market_data.upstox.v3_schema import UPSTOX_V3_SCHEMA_ID, UPSTOX_V3_SCHEMA_SHA256


AT = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)


def raw_frame(frame_bytes: bytes, *, source_order: int = 1) -> RawMarketFrameV1:
    return RawMarketFrameV1(
        provider="upstox",
        provider_schema_id=UPSTOX_V3_SCHEMA_ID,
        provider_schema_sha256=UPSTOX_V3_SCHEMA_SHA256,
        connection_session_id="connection-1",
        source_order_scope_id="capture-1",
        source_order=source_order,
        frame_bytes=frame_bytes,
        frame_content_hash=f"sha256:{hashlib.sha256(frame_bytes).hexdigest()}",
        received_at=AT,
        available_at=AT,
        recorded_at=AT,
        capture_basis=RawCaptureBasis.LIVE_RECEIVED,
    )


def subjects() -> tuple[ResolvedMarketSubjectV1, ...]:
    underlying = UnderlyingInstrumentIdentity("NSE", "NIFTY50", InstrumentType.INDEX, "INR")
    underlying_version = UnderlyingInstrumentVersion(
        instrument_id=underlying.instrument_id,
        valid_from=AT,
        valid_until=None,
        lot_size=1,
        tick_size=Decimal("0.05"),
        display_symbol="Nifty 50",
        trading_status=TradingStatus.ACTIVE,
        catalogue_version_id="catalogue-1",
        recorded_at=AT,
    )
    future = FuturesContractIdentity(
        exchange="NSE",
        underlying_instrument_id=underlying.instrument_id,
        expiry=date(2026, 8, 27),
        settlement_type=SettlementType.CASH,
        multiplier=Decimal("1"),
        currency="INR",
    )
    future_version = FuturesContractVersion(
        contract_id=future.contract_id,
        valid_from=AT,
        valid_until=None,
        lot_size=75,
        tick_size=Decimal("0.05"),
        display_symbol="NIFTY FUT",
        trading_status=TradingStatus.ACTIVE,
        catalogue_version_id="catalogue-1",
        recorded_at=AT,
    )
    option = OptionContractIdentity(
        exchange="NSE",
        underlying_instrument_id=underlying.instrument_id,
        expiry=date(2026, 8, 27),
        strike=Decimal("25000"),
        option_side=OptionSide.CALL,
        exercise_style=ExerciseStyle.EUROPEAN,
        settlement_type=SettlementType.CASH,
        multiplier=Decimal("1"),
        currency="INR",
    )
    option_version = OptionContractVersion(
        contract_id=option.contract_id,
        valid_from=AT,
        valid_until=None,
        lot_size=75,
        tick_size=Decimal("0.05"),
        display_symbol="NIFTY CE",
        trading_status=TradingStatus.ACTIVE,
        catalogue_version_id="catalogue-1",
        recorded_at=AT,
    )
    return (
        _resolved("NSE_INDEX|Nifty 50", MarketSubjectKind.UNDERLYING, underlying, underlying_version),
        _resolved("NSE_FO|future", MarketSubjectKind.FUTURE, future, future_version),
        _resolved("NSE_FO|option", MarketSubjectKind.OPTION, option, option_version),
    )


def _resolved(key, kind, identity, version):
    subject_id = getattr(identity, "instrument_id", None) or identity.contract_id
    return ResolvedMarketSubjectV1(
        provider="upstox",
        provider_contract_key=key,
        provider_mapping_id=f"mapping-{kind.value}",
        contract_version_id=version.version_id,
        economic_subject_id=subject_id,
        instrument_kind=kind,
        economic_identity=identity,
        contract_version=version,
        mapping_effective_from=AT,
        mapping_effective_until=None,
        version_effective_from=AT,
        version_effective_until=None,
        resolution_market_as_of=AT,
        resolution_known_as_of=AT,
    )
