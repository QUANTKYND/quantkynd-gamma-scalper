from __future__ import annotations

from typing import Any

from app.instruments.catalogue import CatalogueVersion
from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    FuturesContractVersion,
    OptionContractIdentity,
    OptionContractVersion,
    ProviderContractMapping,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.instruments.sessions import (
    TradingSessionIdentity,
    TradingSessionVersion,
)


class MalformedPersistenceRecordError(ValueError):
    pass


def catalogue_values(value: CatalogueVersion) -> dict[str, Any]:
    return {
        "catalogue_version_id": value.catalogue_version_id,
        "provider": value.provider,
        "source_content_hash": value.source_content_hash,
        "catalogue_schema_version": value.catalogue_schema_version,
        "effective_from": value.effective_from,
        "effective_until": value.effective_until,
        "published_at": value.published_at,
        "recorded_at": value.recorded_at,
        "row_count": value.row_count,
    }


def catalogue_from_row(row: Any) -> CatalogueVersion:
    return _construct_with_id(
        CatalogueVersion,
        "catalogue_version_id",
        row.catalogue_version_id,
        provider=row.provider,
        source_content_hash=row.source_content_hash,
        catalogue_schema_version=row.catalogue_schema_version,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        published_at=row.published_at,
        recorded_at=row.recorded_at,
        row_count=row.row_count,
    )


def market_instrument_values(
    value: UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity,
) -> dict[str, Any]:
    if isinstance(value, UnderlyingInstrumentIdentity):
        instrument_id = value.instrument_id
        instrument_kind = "underlying"
    elif isinstance(value, FuturesContractIdentity):
        instrument_id = value.contract_id
        instrument_kind = "future"
    else:
        instrument_id = value.contract_id
        instrument_kind = "option"
    return {
        "instrument_id": instrument_id,
        "instrument_kind": instrument_kind,
        "exchange": value.exchange,
        "currency": value.currency,
    }


def underlying_values(value: UnderlyingInstrumentIdentity) -> dict[str, Any]:
    return {
        "instrument_id": value.instrument_id,
        "instrument_kind": "underlying",
        "canonical_symbol": value.canonical_symbol,
        "instrument_type": value.instrument_type.value,
    }


def future_values(value: FuturesContractIdentity) -> dict[str, Any]:
    return {
        "contract_id": value.contract_id,
        "instrument_kind": "future",
        "underlying_instrument_id": value.underlying_instrument_id,
        "expiry": value.expiry,
        "settlement_type": value.settlement_type.value,
        "multiplier": value.multiplier,
    }


def option_values(value: OptionContractIdentity) -> dict[str, Any]:
    return {
        "contract_id": value.contract_id,
        "instrument_kind": "option",
        "underlying_instrument_id": value.underlying_instrument_id,
        "expiry": value.expiry,
        "strike": value.strike,
        "option_side": value.option_side.value,
        "exercise_style": value.exercise_style.value,
        "settlement_type": value.settlement_type.value,
        "multiplier": value.multiplier,
    }


def underlying_from_rows(registry: Any, row: Any) -> UnderlyingInstrumentIdentity:
    _matching_registry_id(registry.instrument_id, row.instrument_id)
    return _construct_with_id(
        UnderlyingInstrumentIdentity,
        "instrument_id",
        registry.instrument_id,
        exchange=registry.exchange,
        canonical_symbol=row.canonical_symbol,
        instrument_type=row.instrument_type,
        currency=registry.currency,
    )


def future_from_rows(registry: Any, row: Any) -> FuturesContractIdentity:
    _matching_registry_id(registry.instrument_id, row.contract_id)
    return _construct_with_id(
        FuturesContractIdentity,
        "contract_id",
        registry.instrument_id,
        exchange=registry.exchange,
        underlying_instrument_id=row.underlying_instrument_id,
        expiry=row.expiry,
        settlement_type=row.settlement_type,
        multiplier=row.multiplier,
        currency=registry.currency,
    )


def option_from_rows(registry: Any, row: Any) -> OptionContractIdentity:
    _matching_registry_id(registry.instrument_id, row.contract_id)
    return _construct_with_id(
        OptionContractIdentity,
        "contract_id",
        registry.instrument_id,
        exchange=registry.exchange,
        underlying_instrument_id=row.underlying_instrument_id,
        expiry=row.expiry,
        strike=row.strike,
        option_side=row.option_side,
        exercise_style=row.exercise_style,
        settlement_type=row.settlement_type,
        multiplier=row.multiplier,
        currency=registry.currency,
    )


def version_values(value: ContractVersion) -> dict[str, Any]:
    instrument_id = (
        value.instrument_id
        if isinstance(value, UnderlyingInstrumentVersion)
        else value.contract_id
    )
    return {
        "version_id": value.version_id,
        "instrument_id": instrument_id,
        "valid_from": value.valid_from,
        "valid_until": value.valid_until,
        "lot_size": value.lot_size,
        "tick_size": value.tick_size,
        "display_symbol": value.display_symbol,
        "trading_status": value.trading_status.value,
        "catalogue_version_id": value.catalogue_version_id,
        "recorded_at": value.recorded_at,
        "superseded_at": value.superseded_at,
    }


def version_from_row(row: Any, instrument_kind: str) -> ContractVersion:
    fields = {
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "lot_size": row.lot_size,
        "tick_size": row.tick_size,
        "display_symbol": row.display_symbol,
        "trading_status": row.trading_status,
        "catalogue_version_id": row.catalogue_version_id,
        "recorded_at": row.recorded_at,
        "superseded_at": row.superseded_at,
    }
    if instrument_kind == "underlying":
        return _construct_with_id(
            UnderlyingInstrumentVersion,
            "version_id",
            row.version_id,
            instrument_id=row.instrument_id,
            **fields,
        )
    if instrument_kind == "future":
        return _construct_with_id(
            FuturesContractVersion,
            "version_id",
            row.version_id,
            contract_id=row.instrument_id,
            **fields,
        )
    if instrument_kind == "option":
        return _construct_with_id(
            OptionContractVersion,
            "version_id",
            row.version_id,
            contract_id=row.instrument_id,
            **fields,
        )
    raise MalformedPersistenceRecordError("unsupported durable instrument kind")


def provider_mapping_values(value: ProviderContractMapping) -> dict[str, Any]:
    return {
        "mapping_id": value.mapping_id,
        "provider": value.provider,
        "provider_contract_key": value.provider_contract_key,
        "contract_version_id": value.contract_version_id,
        "provider_payload_hash": value.provider_payload_hash,
        "source_row_identity": value.source_row_identity,
        "effective_from": value.effective_from,
        "effective_until": value.effective_until,
        "recorded_at": value.recorded_at,
        "superseded_at": value.superseded_at,
    }


def provider_mapping_from_row(row: Any) -> ProviderContractMapping:
    return _construct_with_id(
        ProviderContractMapping,
        "mapping_id",
        row.mapping_id,
        provider=row.provider,
        provider_contract_key=row.provider_contract_key,
        contract_version_id=row.contract_version_id,
        provider_payload_hash=row.provider_payload_hash,
        source_row_identity=row.source_row_identity,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        recorded_at=row.recorded_at,
        superseded_at=row.superseded_at,
    )


def trading_session_values(value: TradingSessionIdentity) -> dict[str, Any]:
    return {
        "session_id": value.session_id,
        "exchange": value.exchange,
        "session_date": value.session_date,
        "session_kind": value.session_kind.value,
    }


def trading_session_from_row(row: Any) -> TradingSessionIdentity:
    return _construct_with_id(
        TradingSessionIdentity,
        "session_id",
        row.session_id,
        exchange=row.exchange,
        session_date=row.session_date,
        session_kind=row.session_kind,
    )


def trading_session_version_values(value: TradingSessionVersion) -> dict[str, Any]:
    return {
        "session_version_id": value.session_version_id,
        "session_id": value.session_id,
        "pre_open_at": value.pre_open_at,
        "open_at": value.open_at,
        "close_at": value.close_at,
        "post_close_at": value.post_close_at,
        "timezone": value.timezone,
        "status": value.status.value,
        "recorded_at": value.recorded_at,
        "superseded_at": value.superseded_at,
    }


def trading_session_version_from_row(row: Any) -> TradingSessionVersion:
    return _construct_with_id(
        TradingSessionVersion,
        "session_version_id",
        row.session_version_id,
        session_id=row.session_id,
        pre_open_at=row.pre_open_at,
        open_at=row.open_at,
        close_at=row.close_at,
        post_close_at=row.post_close_at,
        timezone=row.timezone,
        status=row.status,
        recorded_at=row.recorded_at,
        superseded_at=row.superseded_at,
    )


def _construct(model, **values):
    try:
        return model(**values)
    except (TypeError, ValueError) as exc:
        raise MalformedPersistenceRecordError(
            f"malformed durable {model.__name__} record"
        ) from exc


def _construct_with_id(model, id_attribute: str, expected_id: str, **values):
    result = _construct(model, **values)
    if getattr(result, id_attribute) != expected_id:
        raise MalformedPersistenceRecordError(
            f"durable {model.__name__} identity does not match its content"
        )
    return result


def _matching_registry_id(registry_id: str, subtype_id: str) -> None:
    if registry_id != subtype_id:
        raise MalformedPersistenceRecordError(
            "durable instrument registry and subtype identities do not match"
        )
