from __future__ import annotations

import json
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
from app.instruments.temporal_records import TemporalRecord, TemporalRecordKind
from app.instruments.provider_catalogue import (
    CatalogueIngestionRun,
    CatalogueMembership,
    CatalogueRowOutcome,
    CatalogueSourceArtifact,
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
        "row_count": value.row_count,
    }


def catalogue_from_row(row: Any, record_row: Any) -> CatalogueVersion:
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
        recorded_at=record_row.recorded_at,
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
    }


def version_from_row(row: Any, record_row: Any, instrument_kind: str) -> ContractVersion:
    fields = {
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "lot_size": row.lot_size,
        "tick_size": row.tick_size,
        "display_symbol": row.display_symbol,
        "trading_status": row.trading_status,
        "catalogue_version_id": row.catalogue_version_id,
        "recorded_at": record_row.recorded_at,
        "superseded_at": None,
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
    }


def provider_mapping_from_row(row: Any, record_row: Any) -> ProviderContractMapping:
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
        recorded_at=record_row.recorded_at,
        superseded_at=None,
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
    }


def trading_session_version_from_row(row: Any, record_row: Any) -> TradingSessionVersion:
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
        recorded_at=record_row.recorded_at,
        superseded_at=None,
    )


def temporal_record_values(value: TemporalRecord, semantic_column: str) -> dict[str, Any]:
    return {
        "record_id": value.record_id,
        semantic_column: value.semantic_id,
        "scope_id": value.scope_id,
        "recorded_at": value.recorded_at,
        "supersedes_record_id": value.supersedes_record_id,
        "source_provenance_id": value.source_provenance_id,
    }


def source_artifact_values(value: CatalogueSourceArtifact) -> dict[str, Any]:
    return {
        "source_artifact_id": value.source_artifact_id,
        "provider": value.provider,
        "profile_version": value.profile_version,
        "media_type": value.media_type,
        "compression": value.compression,
        "compressed_sha256": value.compressed_sha256,
        "decompressed_sha256": value.decompressed_sha256,
        "compressed_byte_count": value.compressed_byte_count,
        "decompressed_byte_count": value.decompressed_byte_count,
        "source_schema_version": value.source_schema_version,
        "artifact_object_key": value.artifact_object_key,
    }


def source_artifact_from_row(row: Any) -> CatalogueSourceArtifact:
    return _construct_with_id(
        CatalogueSourceArtifact,
        "source_artifact_id",
        row.source_artifact_id,
        provider=row.provider,
        profile_version=row.profile_version,
        media_type=row.media_type,
        compression=row.compression,
        compressed_sha256=row.compressed_sha256,
        decompressed_sha256=row.decompressed_sha256,
        compressed_byte_count=row.compressed_byte_count,
        decompressed_byte_count=row.decompressed_byte_count,
        source_schema_version=row.source_schema_version,
        artifact_object_key=row.artifact_object_key,
    )


def ingestion_run_values(value: CatalogueIngestionRun) -> dict[str, Any]:
    return {
        "ingestion_run_id": value.ingestion_run_id,
        "idempotency_key": value.idempotency_key,
        "command_digest": value.command_digest,
        "source_artifact_id": value.source_artifact_id,
        "catalogue_version_id": value.catalogue_version_id,
        "catalogue_record_id": value.catalogue_record_id,
        "profile_version": value.profile_version,
        "original_file_name": value.original_file_name,
        "effective_from": value.effective_from,
        "effective_until": value.effective_until,
        "started_at": value.started_at,
        "recorded_at": value.recorded_at,
        "completed_at": value.completed_at,
        "normalized_catalogue_hash": value.normalized_catalogue_hash,
        "physical_row_count": value.physical_row_count,
        "accepted_unique_count": value.accepted_unique_count,
        "exact_duplicate_count": value.exact_duplicate_count,
        "excluded_count": value.excluded_count,
        "database_revision": value.database_revision,
    }


def ingestion_run_from_row(row: Any) -> CatalogueIngestionRun:
    return _construct_with_id(
        CatalogueIngestionRun,
        "ingestion_run_id",
        row.ingestion_run_id,
        idempotency_key=row.idempotency_key,
        command_digest=row.command_digest,
        source_artifact_id=row.source_artifact_id,
        catalogue_version_id=row.catalogue_version_id,
        catalogue_record_id=row.catalogue_record_id,
        profile_version=row.profile_version,
        original_file_name=row.original_file_name,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        started_at=row.started_at,
        recorded_at=row.recorded_at,
        completed_at=row.completed_at,
        normalized_catalogue_hash=row.normalized_catalogue_hash,
        physical_row_count=row.physical_row_count,
        accepted_unique_count=row.accepted_unique_count,
        exact_duplicate_count=row.exact_duplicate_count,
        excluded_count=row.excluded_count,
        database_revision=row.database_revision,
    )


def row_outcome_values(value: CatalogueRowOutcome) -> dict[str, Any]:
    return {
        "row_outcome_id": value.row_outcome_id,
        "ingestion_run_id": value.ingestion_run_id,
        "source_row_occurrence_id": value.source_row_occurrence_id,
        "source_row_semantic_id": value.source_row_semantic_id,
        "physical_row_number": value.physical_row_number,
        "raw_row_hash": value.raw_row_hash,
        "normalized_row_hash": value.normalized_row_hash,
        "provider_contract_key": value.provider_contract_key,
        "disposition": value.disposition.value,
        "reason_codes": json.dumps(list(value.reason_codes), separators=(",", ":"), sort_keys=True),
        "instrument_id": value.instrument_id,
        "version_id": value.version_id,
        "mapping_id": value.mapping_id,
    }


def membership_values(value: CatalogueMembership) -> dict[str, Any]:
    return {
        "membership_id": value.membership_id,
        "catalogue_version_id": value.catalogue_version_id,
        "row_outcome_id": value.row_outcome_id,
        "source_row_occurrence_id": value.source_row_occurrence_id,
        "source_row_semantic_id": value.source_row_semantic_id,
        "instrument_id": value.instrument_id,
        "version_id": value.version_id,
        "mapping_id": value.mapping_id,
        "provider_contract_key": value.provider_contract_key,
        "raw_row_hash": value.raw_row_hash,
        "normalized_row_hash": value.normalized_row_hash,
    }


def temporal_record_from_row(row: Any, kind: TemporalRecordKind, semantic_column: str) -> TemporalRecord:
    return _construct_with_id(
        TemporalRecord,
        "record_id",
        row.record_id,
        kind=kind,
        semantic_id=getattr(row, semantic_column),
        scope_id=row.scope_id,
        recorded_at=row.recorded_at,
        supersedes_record_id=row.supersedes_record_id,
        source_provenance_id=row.source_provenance_id,
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
