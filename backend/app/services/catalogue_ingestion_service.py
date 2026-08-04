from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from sqlalchemy.exc import IntegrityError

from app.core.database_config import DatabaseSettings
from app.core.hashing import stable_hash
from app.instruments.catalogue_parser import ParsedCatalogueArtifact, validate_gzip_json_array
from app.instruments.identity import (
    FuturesContractIdentity,
    OptionContractIdentity,
    UnderlyingInstrumentIdentity,
)
from app.instruments.provider_catalogue import (
    CatalogueArtifactError,
    CatalogueConflictError,
    CatalogueIdempotencyConflictError,
    CatalogueSourceArtifact,
)
from app.instruments.providers.upstox_catalogue import (
    COMPRESSION,
    MEDIA_TYPE,
    NORMALIZER_VERSION,
    PROFILE_VERSION,
    PROVIDER,
    SOURCE_SCHEMA_VERSION,
    build_upstox_nifty_catalogue_plan,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.instruments.ports import PersistenceIntegrityError, SemanticCollisionError
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.persistence.postgres.verification import database_revision


@dataclass(frozen=True)
class CatalogueIngestionCommand:
    profile: str
    file: Path
    effective_from: datetime
    effective_until: datetime | None
    idempotency_key: str | None
    expected_compressed_sha256: str | None
    supersedes_catalogue_record_id: str | None
    mode: str


@dataclass(frozen=True)
class CatalogueIngestionResult:
    status: str
    mode: str
    source_artifact_id: str
    catalogue_version_id: str
    normalized_catalogue_hash: str
    physical_row_count: int
    accepted_unique_count: int
    exact_duplicate_count: int
    excluded_count: int
    command_digest: str
    ingestion_run_id: str | None = None
    catalogue_record_id: str | None = None
    artifact_object_key: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": self.mode,
            "source_artifact_id": self.source_artifact_id,
            "catalogue_version_id": self.catalogue_version_id,
            "catalogue_record_id": self.catalogue_record_id,
            "normalized_catalogue_hash": self.normalized_catalogue_hash,
            "physical_row_count": self.physical_row_count,
            "accepted_unique_count": self.accepted_unique_count,
            "exact_duplicate_count": self.exact_duplicate_count,
            "excluded_count": self.excluded_count,
            "command_digest": self.command_digest,
            "ingestion_run_id": self.ingestion_run_id,
            "artifact_object_key": self.artifact_object_key,
        }


async def ingest_provider_catalogue(
    command: CatalogueIngestionCommand,
    settings: DatabaseSettings,
) -> CatalogueIngestionResult:
    if command.profile != PROFILE_VERSION:
        raise CatalogueConflictError("unsupported catalogue ingestion profile")
    started_at = datetime.now(UTC)
    with validate_gzip_json_array(command.file) as artifact:
        _verify_expected_hash(artifact, command.expected_compressed_sha256)
        object_key = _artifact_object_key(artifact.compressed_sha256)
        source_artifact = CatalogueSourceArtifact(
            provider=PROVIDER,
            profile_version=PROFILE_VERSION,
            media_type=MEDIA_TYPE,
            compression=COMPRESSION,
            compressed_sha256=artifact.compressed_sha256,
            decompressed_sha256=artifact.decompressed_sha256,
            compressed_byte_count=artifact.compressed_byte_count,
            decompressed_byte_count=artifact.decompressed_byte_count,
            source_schema_version=SOURCE_SCHEMA_VERSION,
            artifact_object_key=object_key,
        )
        command_digest = _command_digest(command, source_artifact.source_artifact_id)
        plan = build_upstox_nifty_catalogue_plan(
            artifact=artifact,
            source_artifact_id=source_artifact.source_artifact_id,
            effective_from=command.effective_from,
            effective_until=command.effective_until,
            recorded_at=started_at,
            ingestion_run_id=_ingestion_run_id(command.idempotency_key, command_digest),
        )
        if command.mode == "validate-only":
            return _result(command, source_artifact, plan, command_digest, None, None, None)
        if command.mode == "dry-run":
            await _dry_run(command, settings)
            return _result(command, source_artifact, plan, command_digest, None, None, None)
        if command.idempotency_key is None:
            raise CatalogueConflictError("commit mode requires an explicit idempotency key")
        artifact_root = Path(settings.require_catalogue_artifact_root())
        retained_key = _retain_artifact(command.file, artifact, artifact_root, object_key)
        return await _commit(
            command,
            settings,
            source_artifact,
            plan,
            command_digest,
            retained_key,
            started_at,
        )


async def _dry_run(command: CatalogueIngestionCommand, settings: DatabaseSettings) -> None:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            await unit_of_work.catalogue_ingestions.lock_provider_profile(PROVIDER, PROFILE_VERSION)
            predecessor = await unit_of_work.catalogues.resolve(
                _catalogue_scope(),
                command.effective_from,
                None,
            )
            if predecessor is not None and command.supersedes_catalogue_record_id is None:
                raise CatalogueConflictError("dry-run requires an explicit catalogue predecessor")
    finally:
        await dispose_database_engine(engine)


async def _commit(
    command: CatalogueIngestionCommand,
    settings: DatabaseSettings,
    source_artifact: CatalogueSourceArtifact,
    plan,
    command_digest: str,
    retained_key: str,
    started_at: datetime,
) -> CatalogueIngestionResult:
    engine = create_database_engine(settings)
    try:
        revision = await database_revision(engine)
        if revision != "20260804_03":
            raise CatalogueConflictError("database must be migrated to 20260804_03")
        factory = create_session_factory(engine)
        try:
            async with PostgresUnitOfWork(factory) as unit_of_work:
                await unit_of_work.catalogue_ingestions.lock_provider_profile(PROVIDER, PROFILE_VERSION)
                existing_run = await unit_of_work.catalogue_ingestions.get_ingestion_run_by_idempotency_key(
                    command.idempotency_key
                )
                if existing_run is not None:
                    if existing_run.command_digest != command_digest:
                        raise CatalogueIdempotencyConflictError(
                            "idempotency key conflicts with another command"
                        )
                    return _result(
                        command,
                        source_artifact,
                        plan,
                        command_digest,
                        existing_run.ingestion_run_id,
                        existing_run.catalogue_record_id,
                        retained_key,
                    )
                existing = await unit_of_work.catalogues.resolve(
                    _catalogue_scope(),
                    command.effective_from,
                    None,
                )
                if existing is not None and command.supersedes_catalogue_record_id is None:
                    raise CatalogueConflictError("commit requires an explicit catalogue predecessor")
                await _reject_provider_reassignment(unit_of_work, plan.items, command.effective_from)
                await unit_of_work.catalogue_ingestions.add_source_artifact(source_artifact)
                catalogue_record_id = await unit_of_work.catalogues.add(
                    plan.catalogue,
                    command.supersedes_catalogue_record_id,
                )
                await _add_instruments(unit_of_work, plan.items)
                for item in plan.items:
                    await unit_of_work.instruments.add_version(item.version)
                for item in plan.items:
                    await unit_of_work.instruments.add_provider_mapping(item.mapping)
                run = _run(
                    command,
                    source_artifact,
                    plan,
                    command_digest,
                    catalogue_record_id,
                    revision,
                    started_at,
                )
                await unit_of_work.catalogue_ingestions.add_ingestion_run(run)
                await unit_of_work.catalogue_ingestions.add_row_outcomes(plan.outcomes)
                await unit_of_work.catalogue_ingestions.add_memberships(plan.memberships)
                await unit_of_work.commit()
                return _result(command, source_artifact, plan, command_digest, run.ingestion_run_id, catalogue_record_id, retained_key)
        except (IntegrityError, PersistenceIntegrityError, SemanticCollisionError):
            existing = await _load_idempotent(settings, command, command_digest)
            return _result(command, source_artifact, plan, command_digest, existing.ingestion_run_id, existing.catalogue_record_id, retained_key)
    finally:
        await dispose_database_engine(engine)


async def _load_idempotent(
    settings: DatabaseSettings,
    command: CatalogueIngestionCommand,
    command_digest: str,
):
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            if command.idempotency_key is None:
                raise CatalogueIdempotencyConflictError("missing idempotency key")
            existing = await unit_of_work.catalogue_ingestions.get_ingestion_run_by_idempotency_key(
                command.idempotency_key
            )
            if existing is None or existing.command_digest != command_digest:
                raise CatalogueIdempotencyConflictError("idempotency key conflicts with another command")
            return existing
    finally:
        await dispose_database_engine(engine)


async def _add_instruments(unit_of_work, items) -> None:
    seen: set[str] = set()
    order = {"underlying": 0, "future": 1, "option": 2}
    for item in sorted(items, key=lambda value: (order[value.kind.value], value.instrument_id)):
        if item.instrument_id in seen:
            continue
        seen.add(item.instrument_id)
        if isinstance(item.instrument, UnderlyingInstrumentIdentity):
            await unit_of_work.instruments.add_underlying(item.instrument)
        elif isinstance(item.instrument, FuturesContractIdentity):
            await unit_of_work.instruments.add_future(item.instrument)
        elif isinstance(item.instrument, OptionContractIdentity):
            await unit_of_work.instruments.add_option(item.instrument)


async def _reject_provider_reassignment(unit_of_work, items, effective_from: datetime) -> None:
    for item in sorted(items, key=lambda value: value.provider_contract_key):
        existing = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            item.provider_contract_key,
            effective_from,
            None,
        )
        if existing is not None and existing.contract_version_id != item.version_id:
            raise CatalogueConflictError("provider key reassignment is not allowed for this profile")


def _run(
    command: CatalogueIngestionCommand,
    source_artifact: CatalogueSourceArtifact,
    plan,
    command_digest: str,
    catalogue_record_id: str,
    revision: str,
    started_at: datetime,
):
    from app.instruments.provider_catalogue import CatalogueIngestionRun

    completed_at = datetime.now(UTC)
    return CatalogueIngestionRun(
        idempotency_key=command.idempotency_key or command_digest,
        command_digest=command_digest,
        source_artifact_id=source_artifact.source_artifact_id,
        catalogue_version_id=plan.catalogue.catalogue_version_id,
        catalogue_record_id=catalogue_record_id,
        profile_version=PROFILE_VERSION,
        original_file_name=command.file.name,
        effective_from=command.effective_from,
        effective_until=command.effective_until,
        started_at=started_at,
        recorded_at=started_at,
        completed_at=completed_at,
        normalized_catalogue_hash=plan.normalized_catalogue_hash,
        physical_row_count=plan.physical_row_count,
        accepted_unique_count=plan.accepted_unique_count,
        exact_duplicate_count=plan.exact_duplicate_count,
        excluded_count=plan.excluded_count,
        database_revision=revision,
    )


def _result(
    command: CatalogueIngestionCommand,
    source_artifact: CatalogueSourceArtifact,
    plan,
    command_digest: str,
    ingestion_run_id: str | None,
    catalogue_record_id: str | None,
    artifact_object_key: str | None,
) -> CatalogueIngestionResult:
    return CatalogueIngestionResult(
        status="accepted",
        mode=command.mode,
        source_artifact_id=source_artifact.source_artifact_id,
        catalogue_version_id=plan.catalogue.catalogue_version_id,
        normalized_catalogue_hash=plan.normalized_catalogue_hash,
        physical_row_count=plan.physical_row_count,
        accepted_unique_count=plan.accepted_unique_count,
        exact_duplicate_count=plan.exact_duplicate_count,
        excluded_count=plan.excluded_count,
        command_digest=command_digest,
        ingestion_run_id=ingestion_run_id,
        catalogue_record_id=catalogue_record_id,
        artifact_object_key=artifact_object_key,
    )


def _command_digest(command: CatalogueIngestionCommand, source_artifact_id: str) -> str:
    return stable_hash(
        {
            "entity": "catalogue_ingestion_command",
            "profile": command.profile,
            "source_artifact_id": source_artifact_id,
            "effective_from": command.effective_from,
            "effective_until": command.effective_until,
            "idempotency_key": command.idempotency_key,
            "supersedes_catalogue_record_id": command.supersedes_catalogue_record_id,
            "normalizer_version": NORMALIZER_VERSION,
        }
    )


def _ingestion_run_id(idempotency_key: str | None, command_digest: str) -> str:
    return stable_hash(
        {
            "entity": "catalogue_ingestion_run",
            "idempotency_key": idempotency_key or command_digest,
        }
    )


def _artifact_object_key(compressed_sha256: str) -> str:
    digest = compressed_sha256.removeprefix("sha256:")
    return f"sha256/{digest[:2]}/{digest}.json.gz"


def _retain_artifact(
    source_path: Path,
    artifact: ParsedCatalogueArtifact,
    root: Path,
    object_key: str,
) -> str:
    if source_path.is_symlink():
        raise CatalogueArtifactError("catalogue artifact path must not be a symlink")
    destination = _artifact_destination(root, object_key)
    _harden_artifact_path(root, destination)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise CatalogueArtifactError("catalogue artifact destination must not be a symlink")
        _verify_retained_artifact(destination, artifact.compressed_sha256)
        return object_key
    temporary = tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".tmp-", delete=False)
    temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, 0o600)
        with source_path.open("rb") as source, temporary:
            shutil.copyfileobj(source, temporary)
        _verify_retained_artifact(temporary_path, artifact.compressed_sha256)
        os.replace(temporary_path, destination)
        os.chmod(destination, 0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return object_key


def _artifact_destination(root: Path, object_key: str) -> Path:
    if any(part in {"", ".", ".."} for part in Path(object_key).parts) or Path(object_key).is_absolute():
        raise CatalogueArtifactError("catalogue artifact object key is invalid")
    destination = root / object_key
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise CatalogueArtifactError("catalogue artifact destination escapes artifact root") from exc
    return destination


def _harden_artifact_path(root: Path, destination: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise CatalogueArtifactError("catalogue artifact root must not be a symlink")
    root.chmod(0o700)
    current = root
    for part in destination.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise CatalogueArtifactError("catalogue artifact path must not traverse a symlink")
        current.mkdir(exist_ok=True)
        current.chmod(0o700)


def _verify_retained_artifact(path: Path, expected_hash: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    actual = "sha256:" + digest.hexdigest()
    if actual != expected_hash:
        raise CatalogueArtifactError("retained catalogue artifact hash mismatch")


def _verify_expected_hash(
    artifact: ParsedCatalogueArtifact,
    expected_compressed_sha256: str | None,
) -> None:
    if expected_compressed_sha256 is not None and expected_compressed_sha256 != artifact.compressed_sha256:
        raise CatalogueArtifactError("catalogue artifact does not match expected compressed hash")


def _catalogue_scope() -> str:
    return f"{PROVIDER}:{PROFILE_VERSION}"
