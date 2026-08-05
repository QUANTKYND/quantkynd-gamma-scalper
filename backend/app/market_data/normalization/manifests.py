from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
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
from app.market_data.normalization.models import ResolvedMarketSubjectV1
from app.market_data.normalization.ports import StaticSubjectManifestResolver


def load_capture_manifest(path: Path, frame_bytes: bytes) -> tuple[RawMarketFrameV1, datetime, datetime, dict]:
    payload = _load_json(path)
    if payload.get("fixture_schema_version") != "data-1.3-fixture-v1":
        raise ValueError("unsupported fixture capture manifest")
    frame_hash = f"sha256:{hashlib.sha256(frame_bytes).hexdigest()}"
    if payload.get("frame_sha256") != frame_hash:
        raise ValueError("fixture frame hash mismatch")
    received = _optional_datetime(payload.get("received_at"))
    frame = RawMarketFrameV1(
        provider="upstox",
        provider_schema_id=_text(payload, "provider_schema_id"),
        provider_schema_sha256=_text(payload, "provider_schema_sha256"),
        connection_session_id=_text(payload, "connection_session_id"),
        source_order_scope_id=_text(payload, "source_order_scope_id"),
        source_order=int(payload["source_order"]),
        frame_bytes=frame_bytes,
        frame_content_hash=frame_hash,
        received_at=received,
        available_at=_datetime(payload["available_at"]),
        recorded_at=_datetime(payload["recorded_at"]),
        capture_basis=RawCaptureBasis(payload["capture_basis"]),
        source_file_id=payload.get("source_file_id"),
        source_record_id=payload.get("source_record_id"),
    )
    return (
        frame,
        _datetime(payload["resolution_market_as_of"]),
        _datetime(payload["resolution_known_as_of"]),
        payload,
    )


def load_subject_manifest(path: Path) -> StaticSubjectManifestResolver:
    payload = _load_json(path)
    if payload.get("fixture_schema_version") != "data-1.3-subject-manifest-v1":
        raise ValueError("unsupported fixture subject manifest")
    return StaticSubjectManifestResolver(tuple(_subject(item) for item in payload["subjects"]))


def subject_manifest_payload(subjects: tuple[ResolvedMarketSubjectV1, ...]) -> dict:
    return {
        "fixture_schema_version": "data-1.3-subject-manifest-v1",
        "subjects": tuple(_subject_payload(subject) for subject in sorted(subjects, key=lambda item: item.provider_contract_key)),
    }


def _subject(payload: dict) -> ResolvedMarketSubjectV1:
    kind = MarketSubjectKind(payload["instrument_kind"])
    identity_payload = payload["economic_identity"]
    version_payload = payload["contract_version"]
    if kind is MarketSubjectKind.UNDERLYING:
        identity = UnderlyingInstrumentIdentity(
            identity_payload["exchange"],
            identity_payload["canonical_symbol"],
            InstrumentType(identity_payload["instrument_type"]),
            identity_payload["currency"],
        )
        version = UnderlyingInstrumentVersion(
            instrument_id=identity.instrument_id,
            **_version_fields(version_payload),
        )
    elif kind is MarketSubjectKind.FUTURE:
        identity = FuturesContractIdentity(
            exchange=identity_payload["exchange"],
            underlying_instrument_id=identity_payload["underlying_instrument_id"],
            expiry=date.fromisoformat(identity_payload["expiry"]),
            settlement_type=SettlementType(identity_payload["settlement_type"]),
            multiplier=Decimal(identity_payload["multiplier"]),
            currency=identity_payload["currency"],
        )
        version = FuturesContractVersion(contract_id=identity.contract_id, **_version_fields(version_payload))
    else:
        identity = OptionContractIdentity(
            exchange=identity_payload["exchange"],
            underlying_instrument_id=identity_payload["underlying_instrument_id"],
            expiry=date.fromisoformat(identity_payload["expiry"]),
            strike=Decimal(identity_payload["strike"]),
            option_side=OptionSide(identity_payload["option_side"]),
            exercise_style=ExerciseStyle(identity_payload["exercise_style"]),
            settlement_type=SettlementType(identity_payload["settlement_type"]),
            multiplier=Decimal(identity_payload["multiplier"]),
            currency=identity_payload["currency"],
        )
        version = OptionContractVersion(contract_id=identity.contract_id, **_version_fields(version_payload))
    mapping_payload = payload["provider_mapping"]
    mapping = ProviderContractMapping(
        provider=mapping_payload["provider"],
        provider_contract_key=mapping_payload["provider_contract_key"],
        contract_version_id=version.version_id,
        provider_payload_hash=mapping_payload["provider_payload_hash"],
        source_row_identity=mapping_payload.get("source_row_identity"),
        effective_from=_datetime(mapping_payload["effective_from"]),
        effective_until=_optional_datetime(mapping_payload.get("effective_until")),
        recorded_at=_datetime(mapping_payload["recorded_at"]),
        superseded_at=_optional_datetime(mapping_payload.get("superseded_at")),
    )
    return ResolvedMarketSubjectV1(
        provider=payload["provider"],
        provider_contract_key=payload["provider_contract_key"],
        provider_mapping_id=mapping.mapping_id,
        provider_mapping=mapping,
        contract_version_id=version.version_id,
        economic_subject_id=getattr(identity, "instrument_id", None) or identity.contract_id,
        instrument_kind=kind,
        economic_identity=identity,
        contract_version=version,
        resolution_market_as_of=_datetime(payload["resolution_market_as_of"]),
        resolution_known_as_of=_datetime(payload["resolution_known_as_of"]),
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
        "valid_from": _datetime(payload["valid_from"]),
        "valid_until": _optional_datetime(payload.get("valid_until")),
        "lot_size": int(payload["lot_size"]),
        "tick_size": Decimal(payload["tick_size"]),
        "display_symbol": payload["display_symbol"],
        "trading_status": TradingStatus(payload["trading_status"]),
        "catalogue_version_id": payload["catalogue_version_id"],
        "recorded_at": _datetime(payload["recorded_at"]),
        "superseded_at": _optional_datetime(payload.get("superseded_at")),
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


def _datetime(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("fixture timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("fixture timestamp must be timezone-aware")
    return parsed


def _optional_datetime(value) -> datetime | None:
    return _datetime(value) if value is not None else None
