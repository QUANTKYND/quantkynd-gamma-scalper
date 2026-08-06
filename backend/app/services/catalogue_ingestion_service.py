from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database_config import DatabaseSettings
from app.core.hashing import stable_hash
from app.instruments.catalogue_parser import ParsedCatalogueArtifact, validate_gzip_json_array
from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    OptionContractIdentity,
    UnderlyingInstrumentIdentity,
)
from app.instruments.provider_catalogue import (
    CatalogueArtifactError,
    CatalogueConflictError,
    CatalogueDiffCategory,
    CatalogueIdempotencyConflictError,
    CatalogueItemTransition,
    CatalogueSemanticDiff,
    CatalogueSourceArtifact,
    CatalogueTransitionPlan,
)
from app.instruments.providers.upstox_catalogue import (
    COMPRESSION,
    MEDIA_TYPE,
    NORMALIZER_VERSION,
    PROFILE_VERSION,
    PROVIDER,
    SOURCE_SCHEMA_VERSION,
    UpstoxCataloguePlan,
    bind_upstox_catalogue_plan_recorded_at,
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

REQUIRED_DATABASE_REVISION = "20260804_04"


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
    semantic_diff: CatalogueSemanticDiff | None = None
    disappeared_provider_contract_keys: tuple[str, ...] = ()

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
            "semantic_diff": self.semantic_diff.as_dict() if self.semantic_diff is not None else None,
            "disappeared_provider_contract_keys": self.disappeared_provider_contract_keys,
            "disappearance_is_informational": True,
        }


async def ingest_provider_catalogue(
    command: CatalogueIngestionCommand,
    settings: DatabaseSettings,
    *,
    clock: Callable[[], datetime] | None = None,
) -> CatalogueIngestionResult:
    if command.profile != PROFILE_VERSION:
        raise CatalogueConflictError("unsupported catalogue ingestion profile")
    time_source = clock or _utc_now
    started_at = _clock_value(time_source)
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
            return _result(command, source_artifact, plan, command_digest, None, None, None, None)
        if command.mode == "dry-run":
            transition = await _dry_run(command, settings, plan)
            return _result(
                command,
                source_artifact,
                plan,
                command_digest,
                None,
                None,
                None,
                transition,
            )
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
            time_source,
        )


async def _dry_run(
    command: CatalogueIngestionCommand,
    settings: DatabaseSettings,
    plan: UpstoxCataloguePlan,
) -> CatalogueTransitionPlan:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(
            factory,
            read_only_repeatable_read=True,
        ) as unit_of_work:
            await unit_of_work.catalogue_ingestions.lock_provider_profile(PROVIDER, PROFILE_VERSION)
            return await _build_transition_plan(unit_of_work, command, plan)
    finally:
        await dispose_database_engine(engine)


async def _commit(
    command: CatalogueIngestionCommand,
    settings: DatabaseSettings,
    source_artifact: CatalogueSourceArtifact,
    plan: UpstoxCataloguePlan,
    command_digest: str,
    retained_key: str,
    started_at: datetime,
    clock: Callable[[], datetime],
) -> CatalogueIngestionResult:
    engine = create_database_engine(settings)
    try:
        revision = await database_revision(engine)
        if revision != REQUIRED_DATABASE_REVISION:
            raise CatalogueConflictError(
                "database must be migrated to "
                f"{REQUIRED_DATABASE_REVISION}"
            )
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
                        None,
                    )
                recorded_at = _clock_value(clock)
                if recorded_at < started_at:
                    raise CatalogueConflictError(
                        "accepted write timestamp cannot precede invocation start"
                    )
                accepted_plan = bind_upstox_catalogue_plan_recorded_at(plan, recorded_at)
                transition = await _build_transition_plan(
                    unit_of_work,
                    command,
                    accepted_plan,
                )
                await unit_of_work.catalogue_ingestions.add_source_artifact(source_artifact)
                catalogue_record_id = await unit_of_work.catalogues.add(
                    accepted_plan.catalogue,
                    transition.catalogue_predecessor_record_id,
                )
                await _add_instruments(unit_of_work, accepted_plan.items)
                seen_versions: set[str] = set()
                for item_transition in transition.item_transitions:
                    if item_transition.item.version_id in seen_versions:
                        continue
                    seen_versions.add(item_transition.item.version_id)
                    await unit_of_work.instruments.add_version(
                        item_transition.item.version,
                        item_transition.prior_version_record_id,
                    )
                for item_transition in transition.item_transitions:
                    await unit_of_work.instruments.add_provider_mapping(
                        item_transition.item.mapping,
                        item_transition.prior_mapping_record_id,
                    )
                run = _run(
                    command,
                    source_artifact,
                    accepted_plan,
                    command_digest,
                    catalogue_record_id,
                    revision,
                    started_at,
                    recorded_at,
                    _clock_value(clock),
                )
                await unit_of_work.catalogue_ingestions.add_ingestion_run(run)
                await unit_of_work.catalogue_ingestions.add_row_outcomes(accepted_plan.outcomes)
                await unit_of_work.catalogue_ingestions.add_memberships(accepted_plan.memberships)
                await unit_of_work.commit()
                return _result(
                    command,
                    source_artifact,
                    accepted_plan,
                    command_digest,
                    run.ingestion_run_id,
                    catalogue_record_id,
                    retained_key,
                    transition,
                )
        except (DBAPIError, IntegrityError, PersistenceIntegrityError, SemanticCollisionError):
            existing = await _load_accepted_idempotent(settings, command, command_digest)
            if existing is None:
                raise
            return _result(
                command,
                source_artifact,
                plan,
                command_digest,
                existing.ingestion_run_id,
                existing.catalogue_record_id,
                retained_key,
                None,
            )
    finally:
        await dispose_database_engine(engine)


async def _load_accepted_idempotent(
    settings: DatabaseSettings,
    command: CatalogueIngestionCommand,
    command_digest: str,
):
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            if command.idempotency_key is None:
                return None
            existing = await unit_of_work.catalogue_ingestions.get_ingestion_run_by_idempotency_key(
                command.idempotency_key
            )
            if existing is None:
                return None
            if existing.command_digest != command_digest:
                raise CatalogueIdempotencyConflictError("idempotency key conflicts with another command")
            return existing
    finally:
        await dispose_database_engine(engine)


async def _build_transition_plan(
    unit_of_work,
    command: CatalogueIngestionCommand,
    plan: UpstoxCataloguePlan,
) -> CatalogueTransitionPlan:
    predecessor = await unit_of_work.catalogues.resolve_knowledge_leaf(_catalogue_scope())
    supplied_predecessor = command.supersedes_catalogue_record_id
    if predecessor is None and supplied_predecessor is not None:
        raise CatalogueConflictError("catalogue predecessor is not the current knowledge leaf")
    if predecessor is not None and supplied_predecessor != predecessor.record_id:
        if supplied_predecessor is None:
            raise CatalogueConflictError("an explicit catalogue predecessor is required")
        raise CatalogueConflictError("catalogue predecessor is not the current knowledge leaf")

    prior_memberships = (
        await unit_of_work.catalogue_ingestions.list_memberships_for_catalogue(
            predecessor.value.catalogue_version_id
        )
        if predecessor is not None
        else ()
    )
    current_keys = {item.provider_contract_key for item in plan.items}
    disappeared = tuple(
        sorted(
            membership.provider_contract_key
            for membership in prior_memberships
            if membership.provider_contract_key not in current_keys
        )
    )
    transitions: list[CatalogueItemTransition] = []
    category_counts = {category: 0 for category in CatalogueDiffCategory}
    planned_versions: dict[str, str] = {}
    for item in sorted(plan.items, key=lambda value: value.provider_contract_key):
        planned_version_id = planned_versions.get(item.instrument_id)
        if planned_version_id is not None and planned_version_id != item.version_id:
            raise CatalogueConflictError(
                "one economic instrument has conflicting version metadata in the catalogue"
            )
        planned_versions[item.instrument_id] = item.version_id
        bound_instrument_id = await unit_of_work.instruments.resolve_provider_key_instrument_id(
            PROVIDER,
            item.provider_contract_key,
        )
        if bound_instrument_id is not None and bound_instrument_id != item.instrument_id:
            raise CatalogueConflictError(
                "provider key reassignment to another economic instrument is not allowed"
            )
        version_state = await unit_of_work.instruments.resolve_version_knowledge_leaf(
            item.instrument_id
        )
        mapping_state = await unit_of_work.instruments.resolve_provider_key_knowledge_leaf(
            PROVIDER,
            item.provider_contract_key,
        )
        if mapping_state is not None and mapping_state.instrument_id != item.instrument_id:
            raise CatalogueConflictError(
                "provider key reassignment to another economic instrument is not allowed"
            )
        category = _diff_category(version_state, mapping_state, item.version)
        category_counts[category] += 1
        transitions.append(
            CatalogueItemTransition(
                item=item,
                economic_instrument_id=item.instrument_id,
                prior_version_record_id=(
                    version_state.record_id if version_state is not None else None
                ),
                prior_mapping_record_id=(
                    mapping_state.record_id if mapping_state is not None else None
                ),
                diff_category=category,
            )
        )
    semantic_diff = CatalogueSemanticDiff(
        added=category_counts[CatalogueDiffCategory.ADDED],
        unchanged=category_counts[CatalogueDiffCategory.UNCHANGED],
        metadata_changed=category_counts[CatalogueDiffCategory.METADATA_CHANGED],
        provider_mapping_changed=category_counts[CatalogueDiffCategory.PROVIDER_MAPPING_CHANGED],
        disappeared=len(disappeared),
        excluded=plan.excluded_count,
        exact_duplicates=plan.exact_duplicate_count,
    )
    return CatalogueTransitionPlan(
        catalogue_predecessor_record_id=(predecessor.record_id if predecessor is not None else None),
        catalogue_predecessor_version_id=(
            predecessor.value.catalogue_version_id if predecessor is not None else None
        ),
        item_transitions=tuple(transitions),
        disappeared_provider_contract_keys=disappeared,
        semantic_diff=semantic_diff,
    )


def _diff_category(version_state, mapping_state, version: ContractVersion) -> CatalogueDiffCategory:
    if version_state is None:
        return CatalogueDiffCategory.ADDED
    if _version_metadata(version_state.value) != _version_metadata(version):
        return CatalogueDiffCategory.METADATA_CHANGED
    if mapping_state is None:
        return CatalogueDiffCategory.PROVIDER_MAPPING_CHANGED
    return CatalogueDiffCategory.UNCHANGED


def _version_metadata(version: ContractVersion) -> tuple[object, ...]:
    return (
        type(version),
        version.valid_until,
        version.lot_size,
        version.tick_size,
        version.display_symbol,
        version.trading_status,
    )


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


def _run(
    command: CatalogueIngestionCommand,
    source_artifact: CatalogueSourceArtifact,
    plan,
    command_digest: str,
    catalogue_record_id: str,
    revision: str,
    started_at: datetime,
    recorded_at: datetime,
    completed_at: datetime,
):
    from app.instruments.provider_catalogue import CatalogueIngestionRun

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
        recorded_at=recorded_at,
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
    transition: CatalogueTransitionPlan | None,
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
        semantic_diff=transition.semantic_diff if transition is not None else None,
        disappeared_provider_contract_keys=(
            transition.disappeared_provider_contract_keys if transition is not None else ()
        ),
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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _clock_value(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise CatalogueConflictError("catalogue ingestion clock must return an aware timestamp")
    return value.astimezone(UTC)
