from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import gzip
import hashlib
import json
import stat

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database_config import DatabaseSettings
from app.instruments.provider_catalogue import (
    CatalogueArtifactError,
    CatalogueConflictError,
    CatalogueIdempotencyConflictError,
    CatalogueNormalizationError,
)
from app.instruments.ports import PersistenceIntegrityError, SemanticCollisionError
from app.instruments.providers.upstox_catalogue import PROFILE_VERSION
from app.instruments.temporal_records import TemporalSupersessionConflictError
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.models import (
    CatalogueIngestionRunRow,
    CatalogueMembershipRow,
    CatalogueRowOutcomeRow,
    CatalogueSourceArtifactRow,
    CatalogueVersionRecordRow,
    CatalogueVersionRow,
    InstrumentVersionRow,
    MarketInstrumentRow,
    ProviderContractMappingRow,
    ProviderMappingRecordRow,
    InstrumentVersionRecordRow,
)
from app.persistence.postgres.repositories import (
    PostgresCatalogueIngestionRepository,
    PostgresInstrumentRepository,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)


EFFECTIVE_FROM = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
SECOND_EFFECTIVE_FROM = datetime(2026, 8, 5, 3, 45, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "upstox"
NSE_JSON_GZ = FIXTURE_ROOT / "NSE.json.gz"
CANONICAL_JSON = FIXTURE_ROOT / "NSE.canonical.json"
DATA12_MODELS = (
    CatalogueSourceArtifactRow,
    CatalogueIngestionRunRow,
    CatalogueRowOutcomeRow,
    CatalogueMembershipRow,
)
INGESTION_MODELS = (
    CatalogueVersionRow,
    CatalogueVersionRecordRow,
    MarketInstrumentRow,
    InstrumentVersionRow,
    ProviderContractMappingRow,
    *DATA12_MODELS,
)


@pytest.mark.anyio
async def test_validate_only_and_dry_run_retain_no_artifacts_or_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    validate_settings = DatabaseSettings(_env_file=None)

    validate_result = await ingest_provider_catalogue(
        _command(mode="validate-only", idempotency_key=None),
        validate_settings,
    )
    dry_run_result = await ingest_provider_catalogue(
        _command(mode="dry-run", idempotency_key=None),
        settings,
    )

    assert validate_result.status == "accepted"
    assert dry_run_result.status == "accepted"
    assert dry_run_result.semantic_diff is not None
    assert dry_run_result.semantic_diff.as_dict() == {
        "added": 4,
        "unchanged": 0,
        "metadata_changed": 0,
        "provider_mapping_changed": 0,
        "disappeared": 0,
        "excluded": 1,
        "exact_duplicates": 0,
    }
    assert not (tmp_path / "artifacts").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


@pytest.mark.anyio
async def test_sequential_catalogues_preserve_temporal_history_and_binding(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-sequential-a"),
        settings,
    )
    second_file = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace(
            '"trading_symbol": "NIFTY26AUGFUT"',
            '"trading_symbol": "NIFTY26AUGFUT-UPDATED"',
        ),
        "sequential-b.json.gz",
    )
    second_command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-sequential-b",
        file=second_file,
        effective_from=SECOND_EFFECTIVE_FROM,
        supersedes_catalogue_record_id=first.catalogue_record_id,
    )
    dry_run = await ingest_provider_catalogue(
        replace(second_command, mode="dry-run", idempotency_key=None),
        settings,
    )
    second = await ingest_provider_catalogue(second_command, settings)
    state = await _sequential_state(settings, first, second)

    assert dry_run.semantic_diff is not None
    assert dry_run.semantic_diff.as_dict() == {
        "added": 0,
        "unchanged": 3,
        "metadata_changed": 1,
        "provider_mapping_changed": 0,
        "disappeared": 0,
        "excluded": 1,
        "exact_duplicates": 0,
    }
    assert state["catalogue_before_second_known"] == first.catalogue_version_id
    assert state["catalogue_known_before_effective"] == first.catalogue_version_id
    assert state["catalogue_current"] == second.catalogue_version_id
    assert state["mapping_before_second_known"] == state["first_mapping_id"]
    assert state["mapping_known_before_effective"] == state["first_mapping_id"]
    assert state["mapping_current"] == state["second_mapping_id"]
    assert state["first_instrument_id"] == state["second_instrument_id"]
    assert state["catalogue_successor_target"] == first.catalogue_record_id
    assert state["version_successor_target"] == state["first_version_record_id"]
    assert state["mapping_successor_target"] == state["first_mapping_record_id"]
    assert state["version_root_count"] == 4
    assert state["mapping_root_count"] == 4
    assert state["version_successor_count"] == 4
    assert state["mapping_successor_count"] == 4


@pytest.mark.anyio
async def test_disappearance_is_informational_and_does_not_close_temporal_state(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-disappearance-a"),
        settings,
    )
    rows = json.loads(CANONICAL_JSON.read_text())
    disappeared_key = rows[3]["instrument_key"]
    second_file = _fixture_variant(
        tmp_path,
        json.dumps(rows[:3] + rows[4:]),
        "disappearance-b.json.gz",
    )
    second_command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-disappearance-b",
        file=second_file,
        effective_from=SECOND_EFFECTIVE_FROM,
        supersedes_catalogue_record_id=first.catalogue_record_id,
    )
    dry_run = await ingest_provider_catalogue(
        replace(second_command, mode="dry-run", idempotency_key=None),
        settings,
    )
    await ingest_provider_catalogue(second_command, settings)
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with PostgresUnitOfWork(factory) as unit_of_work:
            mapping = await unit_of_work.instruments.resolve_provider_key_state(
                "upstox",
                disappeared_key,
                SECOND_EFFECTIVE_FROM,
                None,
            )
    finally:
        await dispose_database_engine(engine)

    assert dry_run.disappeared_provider_contract_keys == (disappeared_key,)
    assert dry_run.semantic_diff is not None
    assert dry_run.semantic_diff.disappeared == 1
    assert mapping is not None
    assert mapping.value.effective_until is None


@pytest.mark.anyio
async def test_provider_key_economic_reassignment_is_rejected_in_dry_run_and_commit(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-reassignment-a"),
        settings,
    )
    reassigned = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace('"strike_price": 24500.0', '"strike_price": 24600.0', 1),
        "reassignment-b.json.gz",
    )
    for mode, idempotency_key in (("dry-run", None), ("commit", "DATA-1.2-reassignment-b")):
        with pytest.raises(CatalogueConflictError, match="economic instrument"):
            await ingest_provider_catalogue(
                _command(
                    mode=mode,
                    idempotency_key=idempotency_key,
                    file=reassigned,
                    effective_from=SECOND_EFFECTIVE_FROM,
                    supersedes_catalogue_record_id=first.catalogue_record_id,
                ),
                settings,
            )


@pytest.mark.anyio
async def test_concurrent_catalogue_transitions_serialize_and_exact_replay_is_idempotent(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    first_commands = (
        _command(mode="commit", idempotency_key="DATA-1.2-concurrent-root-a"),
        _command(mode="commit", idempotency_key="DATA-1.2-concurrent-root-b"),
    )
    first_results = await asyncio.gather(
        *(ingest_provider_catalogue(command, settings) for command in first_commands),
        return_exceptions=True,
    )
    roots = [result for result in first_results if not isinstance(result, Exception)]
    root_errors = [result for result in first_results if isinstance(result, Exception)]

    assert len(roots) == 1
    assert len(root_errors) == 1
    first = roots[0]
    successors = (
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-concurrent-successor-a",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
        _command(
            mode="commit",
            idempotency_key="DATA-1.2-concurrent-successor-b",
            effective_from=SECOND_EFFECTIVE_FROM,
            supersedes_catalogue_record_id=first.catalogue_record_id,
        ),
    )
    successor_results = await asyncio.gather(
        *(ingest_provider_catalogue(command, settings) for command in successors),
        return_exceptions=True,
    )
    committed = [result for result in successor_results if not isinstance(result, Exception)]
    rejected = [result for result in successor_results if isinstance(result, Exception)]

    assert len(committed) == 1
    assert len(rejected) == 1
    committed_command = next(
        command
        for command, result in zip(successors, successor_results, strict=True)
        if not isinstance(result, Exception)
    )
    replay_results = await asyncio.gather(
        ingest_provider_catalogue(committed_command, settings),
        ingest_provider_catalogue(committed_command, settings),
    )
    assert replay_results[0].ingestion_run_id == replay_results[1].ingestion_run_id
    assert replay_results[0].catalogue_record_id == replay_results[1].catalogue_record_id


@pytest.mark.anyio
async def test_concurrent_exact_command_returns_commit_and_verified_idempotent_success(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )
    command = _command(
        mode="commit",
        idempotency_key="DATA-1.2-concurrent-exact-command",
    )

    results = await asyncio.gather(
        ingest_provider_catalogue(command, settings),
        ingest_provider_catalogue(command, settings),
    )

    assert results[0].ingestion_run_id == results[1].ingestion_run_id
    assert results[0].catalogue_record_id == results[1].catalogue_record_id
    counts = await _counts(settings, INGESTION_MODELS)
    assert counts["catalogue_ingestion_runs"] == 1
    assert counts["catalogue_version_records"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "error"),
    [
        ("add_source_artifact", SemanticCollisionError("semantic collision")),
        ("add_source_artifact", PersistenceIntegrityError("integrity failure")),
        (
            "add_source_artifact",
            IntegrityError("insert", {}, Exception("unrelated constraint")),
        ),
        ("add_version", TemporalSupersessionConflictError("temporal conflict")),
    ],
)
async def test_non_idempotency_persistence_errors_preserve_their_category(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
    monkeypatch,
    method_name: str,
    error: Exception,
) -> None:
    settings = postgres_settings.model_copy(
        update={"catalogue_artifact_root": str(tmp_path / "artifacts")}
    )

    async def fail(*args, **kwargs):
        raise error

    owner = (
        PostgresInstrumentRepository
        if method_name == "add_version"
        else PostgresCatalogueIngestionRepository
    )
    monkeypatch.setattr(owner, method_name, fail)

    with pytest.raises(type(error)):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key=f"DATA-1.2-{method_name}"),
            settings,
        )


@pytest.mark.anyio
async def test_commit_retains_artifact_atomically_and_replay_is_idempotent(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    command = _command(mode="commit", idempotency_key="DATA-1.2-persistence-commit")

    first = await ingest_provider_catalogue(command, settings)
    counts_after_first = await _counts(settings, INGESTION_MODELS)
    second = await ingest_provider_catalogue(command, settings)
    counts_after_second = await _counts(settings, INGESTION_MODELS)
    retained_path = tmp_path / "artifacts" / str(first.artifact_object_key)

    assert first.ingestion_run_id == second.ingestion_run_id
    assert first.catalogue_record_id == second.catalogue_record_id
    assert counts_after_first == counts_after_second
    assert counts_after_first["catalogue_ingestion_runs"] == 1
    assert counts_after_first["catalogue_source_artifacts"] == 1
    assert counts_after_first["catalogue_row_outcomes"] == 5
    assert counts_after_first["catalogue_memberships"] == 4
    assert retained_path.read_bytes() == NSE_JSON_GZ.read_bytes()
    assert stat.S_IMODE(retained_path.stat().st_mode) == 0o600
    assert not list(retained_path.parent.glob(".tmp-*"))
    assert first.artifact_object_key == _expected_object_key(retained_path)


@pytest.mark.anyio
async def test_commit_requires_postgres_artifact_root_and_idempotency_key(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    no_database = DatabaseSettings(
        _env_file=None,
        database_url=None,
        catalogue_artifact_root=str(tmp_path / "artifacts"),
    )
    no_artifact_root = postgres_settings.model_copy(update={"catalogue_artifact_root": None})
    with pytest.raises(CatalogueConflictError, match="idempotency key"):
        await ingest_provider_catalogue(_command(mode="commit", idempotency_key=None), no_artifact_root)
    with pytest.raises(Exception, match="DATABASE_URL"):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-no-database"),
            no_database,
        )
    with pytest.raises(Exception, match="CATALOGUE_ARTIFACT_ROOT"):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-no-root"),
            no_artifact_root,
        )
    assert await _counts(postgres_settings, INGESTION_MODELS) == {
        model.__tablename__: 0 for model in INGESTION_MODELS
    }


@pytest.mark.anyio
async def test_idempotency_conflict_fails_without_extra_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-conflict"),
        settings,
    )
    counts = await _counts(settings, INGESTION_MODELS)

    with pytest.raises(CatalogueIdempotencyConflictError):
        await ingest_provider_catalogue(
            _command(
                mode="commit",
                idempotency_key="DATA-1.2-conflict",
                effective_from=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
            ),
            settings,
        )

    assert await _counts(settings, INGESTION_MODELS) == counts


@pytest.mark.anyio
async def test_malformed_in_profile_row_rejects_without_any_catalogue_writes(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    malformed = _fixture_variant(
        tmp_path,
        CANONICAL_JSON.read_text().replace('"underlying_symbol": "NIFTY"', '"underlying_symbol": "BANKNIFTY"', 1),
    )

    with pytest.raises(CatalogueNormalizationError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-rejected", file=malformed),
            settings,
        )

    assert not (tmp_path / "artifacts").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


@pytest.mark.anyio
async def test_excluded_valid_nse_rows_are_persisted_without_rejection(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})

    result = await ingest_provider_catalogue(
        _command(mode="commit", idempotency_key="DATA-1.2-exclusion"),
        settings,
    )
    dispositions = await _dispositions(settings)

    assert result.excluded_count == 1
    assert dispositions == {"accepted": 4, "excluded_by_profile": 1}


@pytest.mark.anyio
async def test_retained_artifact_mismatch_and_symlink_paths_fail_closed(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(tmp_path / "artifacts")})
    command = _command(mode="commit", idempotency_key="DATA-1.2-artifact-mismatch")
    result = await ingest_provider_catalogue(command, settings)
    retained_path = tmp_path / "artifacts" / str(result.artifact_object_key)
    counts = await _counts(settings, INGESTION_MODELS)
    retained_path.write_bytes(b"corrupted")

    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(command, settings)

    symlink_source = tmp_path / "NSE-symlink.json.gz"
    symlink_source.symlink_to(NSE_JSON_GZ)
    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-source-symlink", file=symlink_source),
            settings,
        )

    assert await _counts(settings, INGESTION_MODELS) == counts


@pytest.mark.anyio
async def test_artifact_store_parent_symlink_is_rejected(
    reset_postgres_url: str,
    postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "sha256").symlink_to(tmp_path / "outside")
    settings = postgres_settings.model_copy(update={"catalogue_artifact_root": str(artifact_root)})

    with pytest.raises(CatalogueArtifactError):
        await ingest_provider_catalogue(
            _command(mode="commit", idempotency_key="DATA-1.2-store-symlink"),
            settings,
        )

    assert not (tmp_path / "outside").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


def _command(
    *,
    mode: str,
    idempotency_key: str | None,
    file: Path = NSE_JSON_GZ,
    effective_from: datetime = EFFECTIVE_FROM,
    supersedes_catalogue_record_id: str | None = None,
) -> CatalogueIngestionCommand:
    return CatalogueIngestionCommand(
        profile=PROFILE_VERSION,
        file=file,
        effective_from=effective_from,
        effective_until=None,
        idempotency_key=idempotency_key,
        expected_compressed_sha256=None,
        supersedes_catalogue_record_id=supersedes_catalogue_record_id,
        mode=mode,
    )


async def _counts(settings: DatabaseSettings, models: tuple[type, ...]) -> dict[str, int]:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            return {
                model.__tablename__: int(await session.scalar(select(func.count()).select_from(model)))
                for model in models
            }
    finally:
        await dispose_database_engine(engine)


async def _dispositions(settings: DatabaseSettings) -> dict[str, int]:
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(CatalogueRowOutcomeRow.disposition, func.count())
                    .group_by(CatalogueRowOutcomeRow.disposition)
                    .order_by(CatalogueRowOutcomeRow.disposition)
                )
            ).all()
            return {str(disposition): int(count) for disposition, count in rows}
    finally:
        await dispose_database_engine(engine)


async def _sequential_state(settings: DatabaseSettings, first, second) -> dict[str, object]:
    provider_key = "NSE_FO|SANITIZED_NIFTY_FUT"
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            first_run = await session.get(CatalogueIngestionRunRow, first.ingestion_run_id)
            second_run = await session.get(CatalogueIngestionRunRow, second.ingestion_run_id)
            first_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == first.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key == provider_key,
                    )
                )
            ).one()
            second_membership = (
                await session.scalars(
                    select(CatalogueMembershipRow).where(
                        CatalogueMembershipRow.catalogue_version_id
                        == second.catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key == provider_key,
                    )
                )
            ).one()
            first_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == first_membership.version_id
                    )
                )
            ).one()
            second_version_record = (
                await session.scalars(
                    select(InstrumentVersionRecordRow).where(
                        InstrumentVersionRecordRow.version_id == second_membership.version_id
                    )
                )
            ).one()
            first_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == first_membership.mapping_id
                    )
                )
            ).one()
            second_mapping_record = (
                await session.scalars(
                    select(ProviderMappingRecordRow).where(
                        ProviderMappingRecordRow.mapping_id == second_membership.mapping_id
                    )
                )
            ).one()
            second_catalogue_record = await session.get(
                CatalogueVersionRecordRow,
                second.catalogue_record_id,
            )
            version_root_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InstrumentVersionRecordRow)
                    .where(InstrumentVersionRecordRow.supersedes_record_id.is_(None))
                )
            )
            mapping_root_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderMappingRecordRow)
                    .where(ProviderMappingRecordRow.supersedes_record_id.is_(None))
                )
            )
            version_successor_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InstrumentVersionRecordRow)
                    .where(InstrumentVersionRecordRow.supersedes_record_id.is_not(None))
                )
            )
            mapping_successor_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProviderMappingRecordRow)
                    .where(ProviderMappingRecordRow.supersedes_record_id.is_not(None))
                )
            )
        assert first_run is not None
        assert second_run is not None
        assert second_catalogue_record is not None
        async with PostgresUnitOfWork(factory) as unit_of_work:
            catalogue_before_second_known = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM,
                first_run.recorded_at,
            )
            catalogue_known_before_effective = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
                second_run.recorded_at,
            )
            catalogue_current = await unit_of_work.catalogues.resolve(
                "upstox:upstox-nse-nifty-index-derivatives-v1",
                SECOND_EFFECTIVE_FROM,
                None,
            )
            mapping_before_second_known = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM,
                first_run.recorded_at,
            )
            mapping_known_before_effective = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
                second_run.recorded_at,
            )
            mapping_current = await unit_of_work.instruments.resolve_provider_key(
                "upstox",
                provider_key,
                SECOND_EFFECTIVE_FROM,
                None,
            )
        return {
            "catalogue_before_second_known": catalogue_before_second_known.catalogue_version_id,
            "catalogue_known_before_effective": catalogue_known_before_effective.catalogue_version_id,
            "catalogue_current": catalogue_current.catalogue_version_id,
            "mapping_before_second_known": mapping_before_second_known.mapping_id,
            "mapping_known_before_effective": mapping_known_before_effective.mapping_id,
            "mapping_current": mapping_current.mapping_id,
            "first_mapping_id": first_membership.mapping_id,
            "second_mapping_id": second_membership.mapping_id,
            "first_instrument_id": first_membership.instrument_id,
            "second_instrument_id": second_membership.instrument_id,
            "catalogue_successor_target": second_catalogue_record.supersedes_record_id,
            "version_successor_target": second_version_record.supersedes_record_id,
            "mapping_successor_target": second_mapping_record.supersedes_record_id,
            "first_version_record_id": first_version_record.record_id,
            "first_mapping_record_id": first_mapping_record.record_id,
            "version_root_count": version_root_count,
            "mapping_root_count": mapping_root_count,
            "version_successor_count": version_successor_count,
            "mapping_successor_count": mapping_successor_count,
        }
    finally:
        await dispose_database_engine(engine)


def _fixture_variant(tmp_path: Path, payload: str, name: str = "variant.json.gz") -> Path:
    path = tmp_path / name
    path.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    return path


def _expected_object_key(retained_path: Path) -> str:
    compressed_sha256 = hashlib.sha256(retained_path.read_bytes()).hexdigest()
    return f"sha256/{compressed_sha256[:2]}/{compressed_sha256}.json.gz"
