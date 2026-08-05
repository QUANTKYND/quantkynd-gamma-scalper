from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.core.hashing import stable_hash


class CatalogueIngestionDisposition(StrEnum):
    ACCEPTED = "accepted"
    EXACT_DUPLICATE = "exact_duplicate"
    EXCLUDED_BY_PROFILE = "excluded_by_profile"


class CatalogueInstrumentKind(StrEnum):
    UNDERLYING = "underlying"
    FUTURE = "future"
    OPTION = "option"


class CatalogueDiffCategory(StrEnum):
    ADDED = "added"
    UNCHANGED = "unchanged"
    METADATA_CHANGED = "metadata_changed"
    PROVIDER_MAPPING_CHANGED = "provider_mapping_changed"


@dataclass(frozen=True)
class CatalogueSourceArtifact:
    provider: str
    profile_version: str
    media_type: str
    compression: str
    compressed_sha256: str
    decompressed_sha256: str
    compressed_byte_count: int
    decompressed_byte_count: int
    source_schema_version: str
    artifact_object_key: str

    def __post_init__(self) -> None:
        _require_text(
            self.provider,
            self.profile_version,
            self.media_type,
            self.compression,
            self.compressed_sha256,
            self.decompressed_sha256,
            self.source_schema_version,
            self.artifact_object_key,
        )
        _require_non_negative_int(self.compressed_byte_count, "compressed_byte_count")
        _require_non_negative_int(self.decompressed_byte_count, "decompressed_byte_count")

    @property
    def source_artifact_id(self) -> str:
        return stable_hash(
            {
                "entity": "catalogue_source_artifact",
                "provider": self.provider,
                "profile_version": self.profile_version,
                "compression": self.compression,
                "media_type": self.media_type,
                "compressed_sha256": self.compressed_sha256,
                "decompressed_sha256": self.decompressed_sha256,
                "source_schema_version": self.source_schema_version,
            }
        )


@dataclass(frozen=True)
class CatalogueIngestionRun:
    idempotency_key: str
    command_digest: str
    source_artifact_id: str
    catalogue_version_id: str
    catalogue_record_id: str
    profile_version: str
    original_file_name: str
    effective_from: datetime
    effective_until: datetime | None
    started_at: datetime
    recorded_at: datetime
    completed_at: datetime
    normalized_catalogue_hash: str
    physical_row_count: int
    accepted_unique_count: int
    exact_duplicate_count: int
    excluded_count: int
    database_revision: str

    def __post_init__(self) -> None:
        _require_text(
            self.idempotency_key,
            self.command_digest,
            self.source_artifact_id,
            self.catalogue_version_id,
            self.catalogue_record_id,
            self.profile_version,
            self.original_file_name,
            self.normalized_catalogue_hash,
            self.database_revision,
        )
        object.__setattr__(self, "effective_from", _utc(self.effective_from, "effective_from"))
        if self.effective_until is not None:
            effective_until = _utc(self.effective_until, "effective_until")
            if effective_until <= self.effective_from:
                raise ValueError("effective_until must be after effective_from")
            object.__setattr__(self, "effective_until", effective_until)
        for field_name in ("started_at", "recorded_at", "completed_at"):
            object.__setattr__(self, field_name, _utc(getattr(self, field_name), field_name))
        for field_name in (
            "physical_row_count",
            "accepted_unique_count",
            "exact_duplicate_count",
            "excluded_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)

    @property
    def ingestion_run_id(self) -> str:
        return stable_hash(
            {
                "entity": "catalogue_ingestion_run",
                "idempotency_key": self.idempotency_key,
            }
        )


@dataclass(frozen=True)
class CatalogueRowOutcome:
    ingestion_run_id: str
    source_row_occurrence_id: str
    source_row_semantic_id: str
    physical_row_number: int
    raw_row_hash: str
    normalized_row_hash: str | None
    provider_contract_key: str | None
    disposition: CatalogueIngestionDisposition
    reason_codes: tuple[str, ...]
    instrument_id: str | None = None
    version_id: str | None = None
    mapping_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(
            self.ingestion_run_id,
            self.source_row_occurrence_id,
            self.source_row_semantic_id,
            self.raw_row_hash,
        )
        if self.normalized_row_hash is not None:
            _require_text(self.normalized_row_hash)
        if self.provider_contract_key is not None:
            _require_text(self.provider_contract_key)
        object.__setattr__(self, "disposition", CatalogueIngestionDisposition(self.disposition))
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        _require_positive_int(self.physical_row_number, "physical_row_number")

    @property
    def row_outcome_id(self) -> str:
        return stable_hash(
            {
                "entity": "catalogue_row_outcome",
                "ingestion_run_id": self.ingestion_run_id,
                "source_row_occurrence_id": self.source_row_occurrence_id,
                "source_row_semantic_id": self.source_row_semantic_id,
                "physical_row_number": self.physical_row_number,
                "raw_row_hash": self.raw_row_hash,
                "normalized_row_hash": self.normalized_row_hash,
                "provider_contract_key": self.provider_contract_key,
                "disposition": self.disposition.value,
                "reason_codes": self.reason_codes,
                "instrument_id": self.instrument_id,
                "version_id": self.version_id,
                "mapping_id": self.mapping_id,
            }
        )


@dataclass(frozen=True)
class CatalogueMembership:
    catalogue_version_id: str
    row_outcome_id: str
    source_row_occurrence_id: str
    source_row_semantic_id: str
    instrument_id: str
    version_id: str
    mapping_id: str
    provider_contract_key: str
    raw_row_hash: str
    normalized_row_hash: str

    def __post_init__(self) -> None:
        _require_text(
            self.catalogue_version_id,
            self.row_outcome_id,
            self.source_row_occurrence_id,
            self.source_row_semantic_id,
            self.instrument_id,
            self.version_id,
            self.mapping_id,
            self.provider_contract_key,
            self.raw_row_hash,
            self.normalized_row_hash,
        )

    @property
    def membership_id(self) -> str:
        return stable_hash(
            {
                "entity": "catalogue_membership",
                "catalogue_version_id": self.catalogue_version_id,
                "source_row_semantic_id": self.source_row_semantic_id,
                "instrument_id": self.instrument_id,
                "version_id": self.version_id,
                "mapping_id": self.mapping_id,
                "provider_contract_key": self.provider_contract_key,
                "normalized_row_hash": self.normalized_row_hash,
            }
        )


@dataclass(frozen=True)
class NormalizedCatalogueItem:
    kind: CatalogueInstrumentKind
    provider_contract_key: str
    instrument_id: str
    version_id: str
    mapping_id: str
    normalized_row_hash: str
    raw_row_hash: str
    source_row_semantic_id: str
    source_row_occurrence_id: str
    physical_row_number: int
    projection: dict[str, object]
    instrument: object
    version: object
    mapping: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", CatalogueInstrumentKind(self.kind))


@dataclass(frozen=True)
class CatalogueSemanticDiff:
    added: int
    unchanged: int
    metadata_changed: int
    provider_mapping_changed: int
    disappeared: int
    excluded: int
    exact_duplicates: int

    def __post_init__(self) -> None:
        for field_name in (
            "added",
            "unchanged",
            "metadata_changed",
            "provider_mapping_changed",
            "disappeared",
            "excluded",
            "exact_duplicates",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)

    def as_dict(self) -> dict[str, int]:
        return {
            "added": self.added,
            "unchanged": self.unchanged,
            "metadata_changed": self.metadata_changed,
            "provider_mapping_changed": self.provider_mapping_changed,
            "disappeared": self.disappeared,
            "excluded": self.excluded,
            "exact_duplicates": self.exact_duplicates,
        }


@dataclass(frozen=True)
class CatalogueItemTransition:
    item: NormalizedCatalogueItem
    economic_instrument_id: str
    prior_version_record_id: str | None
    prior_mapping_record_id: str | None
    diff_category: CatalogueDiffCategory


@dataclass(frozen=True)
class CatalogueTransitionPlan:
    catalogue_predecessor_record_id: str | None
    catalogue_predecessor_version_id: str | None
    item_transitions: tuple[CatalogueItemTransition, ...]
    disappeared_provider_contract_keys: tuple[str, ...]
    semantic_diff: CatalogueSemanticDiff


class CatalogueIngestionError(ValueError):
    code = "catalogue_ingestion_error"


class CatalogueArtifactError(CatalogueIngestionError):
    code = "catalogue_artifact_error"


class CatalogueParseError(CatalogueIngestionError):
    code = "catalogue_parse_error"


class CatalogueNormalizationError(CatalogueIngestionError):
    code = "catalogue_normalization_error"


class CatalogueConflictError(CatalogueIngestionError):
    code = "catalogue_conflict"


class CatalogueIdempotencyConflictError(CatalogueConflictError):
    code = "catalogue_idempotency_conflict"


def source_row_semantic_id(provider: str, profile_version: str, raw_row_hash: str) -> str:
    return stable_hash(
        {
            "entity": "catalogue_source_row_semantic",
            "provider": provider,
            "profile_version": profile_version,
            "raw_row_hash": raw_row_hash,
        }
    )


def source_row_occurrence_id(
    source_artifact_id: str,
    physical_row_number: int,
    raw_row_hash: str,
) -> str:
    return stable_hash(
        {
            "entity": "catalogue_source_row_occurrence",
            "source_artifact_id": source_artifact_id,
            "physical_row_number": physical_row_number,
            "raw_row_hash": raw_row_hash,
        }
    )


def normalized_catalogue_hash(projections: tuple[dict[str, object], ...]) -> str:
    return stable_hash(
        {
            "entity": "normalized_provider_catalogue",
            "items": tuple(sorted(projections, key=lambda item: stable_hash(item))),
        }
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("text fields must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
