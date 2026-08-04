from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.instruments.catalogue import CatalogueVersion
from app.instruments.identity import (
    ExerciseStyle,
    FuturesContractIdentity,
    FuturesContractVersion,
    InstrumentType,
    OptionContractIdentity,
    OptionContractVersion,
    OptionSide,
    ProviderContractMapping,
    SettlementType,
    TradingStatus,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.instruments.sessions import (
    SessionKind,
    SessionStatus,
    TradingSessionIdentity,
    TradingSessionVersion,
)
from app.instruments.ports import UnitOfWork


@dataclass(frozen=True)
class DataFoundationFixture:
    catalogue: CatalogueVersion
    underlying: UnderlyingInstrumentIdentity
    future: FuturesContractIdentity
    option: OptionContractIdentity
    underlying_version: UnderlyingInstrumentVersion
    future_version: FuturesContractVersion
    option_version: OptionContractVersion
    provider_mapping: ProviderContractMapping
    session: TradingSessionIdentity
    session_version: TradingSessionVersion


def deterministic_fixture() -> DataFoundationFixture:
    recorded_at = datetime(2026, 8, 4, 3, 30, tzinfo=UTC)
    effective_from = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
    catalogue = CatalogueVersion(
        provider="fixture",
        source_content_hash="sha256:" + "a" * 64,
        catalogue_schema_version=1,
        effective_from=effective_from,
        effective_until=None,
        published_at=recorded_at,
        recorded_at=recorded_at,
        row_count=3,
    )
    underlying = UnderlyingInstrumentIdentity("NSE", "NIFTY50", InstrumentType.INDEX, "INR")
    future = FuturesContractIdentity(
        exchange="NSE",
        underlying_instrument_id=underlying.instrument_id,
        expiry=date(2026, 8, 27),
        settlement_type=SettlementType.CASH,
        multiplier=Decimal("75"),
        currency="INR",
    )
    option = OptionContractIdentity(
        exchange="NSE",
        underlying_instrument_id=underlying.instrument_id,
        expiry=date(2026, 8, 27),
        strike=Decimal("24000.125000000000000001"),
        option_side=OptionSide.CALL,
        exercise_style=ExerciseStyle.EUROPEAN,
        settlement_type=SettlementType.CASH,
        multiplier=Decimal("75"),
        currency="INR",
    )
    common = {
        "valid_from": effective_from,
        "valid_until": None,
        "lot_size": 75,
        "tick_size": Decimal("0.050000000000000001"),
        "trading_status": TradingStatus.ACTIVE,
        "catalogue_version_id": catalogue.catalogue_version_id,
        "recorded_at": recorded_at,
    }
    underlying_version = UnderlyingInstrumentVersion(
        instrument_id=underlying.instrument_id,
        display_symbol="NIFTY 50",
        **common,
    )
    future_version = FuturesContractVersion(
        contract_id=future.contract_id,
        display_symbol="NIFTY26AUGFUT",
        **common,
    )
    option_version = OptionContractVersion(
        contract_id=option.contract_id,
        display_symbol="NIFTY26AUG24000CE",
        **common,
    )
    provider_mapping = ProviderContractMapping(
        provider="fixture",
        provider_contract_key="NSE_FO|fixture-option",
        contract_version_id=option_version.version_id,
        provider_payload_hash="sha256:" + "b" * 64,
        source_row_identity="source-row-3",
        effective_from=effective_from,
        effective_until=None,
        recorded_at=recorded_at,
    )
    session = TradingSessionIdentity("NSE", date(2026, 8, 4), SessionKind.REGULAR)
    session_version = TradingSessionVersion(
        session_id=session.session_id,
        pre_open_at=datetime(2026, 8, 4, 3, 30, tzinfo=UTC),
        open_at=datetime(2026, 8, 4, 3, 45, tzinfo=UTC),
        close_at=datetime(2026, 8, 4, 10, 0, tzinfo=UTC),
        post_close_at=datetime(2026, 8, 4, 10, 15, tzinfo=UTC),
        timezone="Asia/Kolkata",
        status=SessionStatus.CLOSED,
        recorded_at=recorded_at,
    )
    return DataFoundationFixture(
        catalogue,
        underlying,
        future,
        option,
        underlying_version,
        future_version,
        option_version,
        provider_mapping,
        session,
        session_version,
    )


async def seed_fixture(unit_of_work: UnitOfWork, fixture: DataFoundationFixture) -> None:
    async with unit_of_work:
        await unit_of_work.catalogues.add(fixture.catalogue)
        await unit_of_work.instruments.add_underlying(fixture.underlying)
        await unit_of_work.instruments.add_future(fixture.future)
        await unit_of_work.instruments.add_option(fixture.option)
        await unit_of_work.instruments.add_version(fixture.underlying_version)
        await unit_of_work.instruments.add_version(fixture.future_version)
        await unit_of_work.instruments.add_version(fixture.option_version)
        await unit_of_work.instruments.add_provider_mapping(fixture.provider_mapping)
        await unit_of_work.trading_sessions.add_identity(fixture.session)
        await unit_of_work.trading_sessions.add_version(fixture.session_version)
        await unit_of_work.commit()
