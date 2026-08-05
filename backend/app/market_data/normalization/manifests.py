from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

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
from app.market_data.normalization.enums import MarketSubjectKind, RawCaptureBasis
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.normalization.limits import validate_source_order
from app.market_data.normalization.models import ResolvedMarketSubjectV1
from app.market_data.normalization.ports import StaticSubjectManifestResolver
from app.market_data.upstox.v3_schema import UPSTOX_V3_SCHEMA_ID, UPSTOX_V3_SCHEMA_SHA256


class ManifestOwnershipError(ValueError):
    pass


def load_capture_manifest(path: Path, frame_bytes: bytes) -> tuple[RawMarketFrameV1, datetime, datetime, dict]:
    payload = _load_json(path)
    if _text(payload, "fixture_schema_version") != "data-1.3-fixture-v1":
        raise ManifestOwnershipError("unsupported fixture capture manifest")
    if _text(payload, "provider") != "upstox":
        raise ManifestOwnershipError("fixture provider mismatch")
    if _text(payload, "provider_schema_id") != UPSTOX_V3_SCHEMA_ID:
        raise ManifestOwnershipError("fixture provider schema mismatch")
    if _text(payload, "provider_schema_sha256") != UPSTOX_V3_SCHEMA_SHA256:
        raise ManifestOwnershipError("fixture provider schema hash mismatch")
    frame_hash = f"sha256:{hashlib.sha256(frame_bytes).hexdigest()}"
    if _text(payload, "frame_sha256") != frame_hash:
        raise ManifestOwnershipError("fixture frame hash mismatch")
    received = _optional_datetime(_required(payload, "received_at"))
    expected_event_ids = _array(payload, "expected_event_ids")
    if any(not isinstance(value, str) or not value.strip() for value in expected_event_ids):
        raise ValueError("expected_event_ids must contain non-empty text")
    _text(payload, "expected_full_result_sha256")
    _text(payload, "expected_adopted_semantics_sha256")
    frame = RawMarketFrameV1(
        provider="upstox",
        provider_schema_id=UPSTOX_V3_SCHEMA_ID,
        provider_schema_sha256=UPSTOX_V3_SCHEMA_SHA256,
        connection_session_id=_text(payload, "connection_session_id"),
        source_order_scope_id=_text(payload, "source_order_scope_id"),
        source_order=_integer(payload, "source_order"),
        frame_bytes=frame_bytes,
        frame_content_hash=frame_hash,
        received_at=received,
        available_at=_datetime(_required(payload, "available_at")),
        recorded_at=_datetime(_required(payload, "recorded_at")),
        capture_basis=RawCaptureBasis(_text(payload, "capture_basis")),
        source_file_id=_optional_text(payload, "source_file_id"),
        source_record_id=_optional_text(payload, "source_record_id"),
    )
    return (
        frame,
        _datetime(_required(payload, "resolution_market_as_of")),
        _datetime(_required(payload, "resolution_known_as_of")),
        payload,
    )


def load_subject_manifest(path: Path) -> StaticSubjectManifestResolver:
    payload = _load_json(path)
    if _text(payload, "fixture_schema_version") != "data-1.3-subject-manifest-v1":
        raise ValueError("unsupported fixture subject manifest")
    return StaticSubjectManifestResolver(tuple(_subject(_subject_object(item)) for item in _array(payload, "subjects")))


def subject_manifest_payload(subjects: tuple[ResolvedMarketSubjectV1, ...]) -> dict:
    return {
        "fixture_schema_version": "data-1.3-subject-manifest-v1",
        "subjects": tuple(_subject_payload(subject) for subject in sorted(subjects, key=lambda item: item.provider_contract_key)),
    }


def _subject(payload: dict) -> ResolvedMarketSubjectV1:
    kind = MarketSubjectKind(_text(payload, "instrument_kind"))
    identity_payload = _object(payload, "economic_identity")
    version_payload = _object(payload, "contract_version")
    if kind is MarketSubjectKind.UNDERLYING:
        identity = UnderlyingInstrumentIdentity(
            _text(identity_payload, "exchange"),
            _text(identity_payload, "canonical_symbol"),
            InstrumentType(_text(identity_payload, "instrument_type")),
            _text(identity_payload, "currency"),
        )
        version = UnderlyingInstrumentVersion(
            instrument_id=identity.instrument_id,
            **_version_fields(version_payload),
        )
    elif kind is MarketSubjectKind.FUTURE:
        identity = FuturesContractIdentity(
            exchange=_text(identity_payload, "exchange"),
            underlying_instrument_id=_text(identity_payload, "underlying_instrument_id"),
            expiry=_date(identity_payload, "expiry"),
            settlement_type=SettlementType(_text(identity_payload, "settlement_type")),
            multiplier=_decimal(identity_payload, "multiplier"),
            currency=_text(identity_payload, "currency"),
        )
        version = FuturesContractVersion(contract_id=identity.contract_id, **_version_fields(version_payload))
    else:
        identity = OptionContractIdentity(
            exchange=_text(identity_payload, "exchange"),
            underlying_instrument_id=_text(identity_payload, "underlying_instrument_id"),
            expiry=_date(identity_payload, "expiry"),
            strike=_decimal(identity_payload, "strike"),
            option_side=OptionSide(_text(identity_payload, "option_side")),
            exercise_style=ExerciseStyle(_text(identity_payload, "exercise_style")),
            settlement_type=SettlementType(_text(identity_payload, "settlement_type")),
            multiplier=_decimal(identity_payload, "multiplier"),
            currency=_text(identity_payload, "currency"),
        )
        version = OptionContractVersion(contract_id=identity.contract_id, **_version_fields(version_payload))
    mapping_payload = _object(payload, "provider_mapping")
    mapping = ProviderContractMapping(
        provider=_text(mapping_payload, "provider"),
        provider_contract_key=_text(mapping_payload, "provider_contract_key"),
        contract_version_id=version.version_id,
        provider_payload_hash=_text(mapping_payload, "provider_payload_hash"),
        source_row_identity=_optional_text(mapping_payload, "source_row_identity"),
        effective_from=_datetime(_required(mapping_payload, "effective_from")),
        effective_until=_optional_datetime(_required(mapping_payload, "effective_until")),
        recorded_at=_datetime(_required(mapping_payload, "recorded_at")),
        superseded_at=_optional_datetime(_required(mapping_payload, "superseded_at")),
    )
    return ResolvedMarketSubjectV1(
        provider=_text(payload, "provider"),
        provider_contract_key=_text(payload, "provider_contract_key"),
        provider_mapping_id=mapping.mapping_id,
        provider_mapping=mapping,
        contract_version_id=version.version_id,
        economic_subject_id=getattr(identity, "instrument_id", None) or identity.contract_id,
        instrument_kind=kind,
        economic_identity=identity,
        contract_version=version,
        resolution_market_as_of=_datetime(_required(payload, "resolution_market_as_of")),
        resolution_known_as_of=_datetime(_required(payload, "resolution_known_as_of")),
    )


def _subject_payload(subject: ResolvedMarketSubjectV1) -> dict:
    identity = subject.economic_identity
    version = subject.contract_version
    mapping = subject.provider_mapping
    if isinstance(identity, UnderlyingInstrumentIdentity):
        identity_payload = {
            "exchange": identity.exchange,
            "canonical_symbol": identity.canonical_symbol,
            "instrument_type": identity.instrument_type.value,
            "currency": identity.currency,
        }
    elif isinstance(identity, FuturesContractIdentity):
        identity_payload = {
            "exchange": identity.exchange,
            "underlying_instrument_id": identity.underlying_instrument_id,
            "expiry": identity.expiry,
            "settlement_type": identity.settlement_type.value,
            "multiplier": identity.multiplier,
            "currency": identity.currency,
        }
    else:
        identity_payload = {
            "exchange": identity.exchange,
            "underlying_instrument_id": identity.underlying_instrument_id,
            "expiry": identity.expiry,
            "strike": identity.strike,
            "option_side": identity.option_side.value,
            "exercise_style": identity.exercise_style.value,
            "settlement_type": identity.settlement_type.value,
            "multiplier": identity.multiplier,
            "currency": identity.currency,
        }
    return {
        "provider": subject.provider,
        "provider_contract_key": subject.provider_contract_key,
        "instrument_kind": subject.instrument_kind.value,
        "economic_identity": identity_payload,
        "contract_version": {
            "valid_from": version.valid_from,
            "valid_until": version.valid_until,
            "lot_size": version.lot_size,
            "tick_size": version.tick_size,
            "display_symbol": version.display_symbol,
            "trading_status": version.trading_status.value,
            "catalogue_version_id": version.catalogue_version_id,
            "recorded_at": version.recorded_at,
            "superseded_at": version.superseded_at,
        },
        "provider_mapping": {
            "provider": mapping.provider,
            "provider_contract_key": mapping.provider_contract_key,
            "provider_payload_hash": mapping.provider_payload_hash,
            "source_row_identity": mapping.source_row_identity,
            "effective_from": mapping.effective_from,
            "effective_until": mapping.effective_until,
            "recorded_at": mapping.recorded_at,
            "superseded_at": mapping.superseded_at,
        },
        "resolution_market_as_of": subject.resolution_market_as_of,
        "resolution_known_as_of": subject.resolution_known_as_of,
    }


def _version_fields(payload: dict) -> dict:
    return {
        "valid_from": _datetime(_required(payload, "valid_from")),
        "valid_until": _optional_datetime(_required(payload, "valid_until")),
        "lot_size": _integer(payload, "lot_size"),
        "tick_size": _decimal(payload, "tick_size"),
        "display_symbol": _text(payload, "display_symbol"),
        "trading_status": TradingStatus(_text(payload, "trading_status")),
        "catalogue_version_id": _text(payload, "catalogue_version_id"),
        "recorded_at": _datetime(_required(payload, "recorded_at")),
        "superseded_at": _optional_datetime(_required(payload, "superseded_at")),
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture manifest must be a JSON object")
    return payload


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _required(payload: dict, key: str):
    if key not in payload:
        raise ValueError(f"missing required field: {key}")
    return payload[key]


def _object(payload: dict, key: str) -> dict:
    value = _required(payload, key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _array(payload: dict, key: str) -> list:
    value = _required(payload, key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    return value


def _subject_object(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("each subject must be an object")
    return value


def _optional_text(payload: dict, key: str) -> str | None:
    value = _required(payload, key)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{key} must be null or non-empty text")
    return value


def _decimal(payload: dict, key: str) -> Decimal:
    value = _required(payload, key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{key} must be a canonical decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{key} must be finite")
    canonical = "0" if parsed.is_zero() else format(parsed.normalize(), "f")
    if value != canonical:
        raise ValueError(f"{key} must be a canonical decimal string")
    return parsed


def _date(payload: dict, key: str) -> date:
    value = _text(payload, key)
    return date.fromisoformat(value)


def _integer(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if key == "source_order":
        validate_source_order(value)
    return value


def _datetime(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("fixture timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("fixture timestamp must be timezone-aware")
    return parsed


def _optional_datetime(value) -> datetime | None:
    return _datetime(value) if value is not None else None
