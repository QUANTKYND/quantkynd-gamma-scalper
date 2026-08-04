from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import gzip
import hashlib
import stat

import pytest
from sqlalchemy import func, select

from app.core.database_config import DatabaseSettings
from app.instruments.provider_catalogue import (
    CatalogueArtifactError,
    CatalogueConflictError,
    CatalogueIdempotencyConflictError,
    CatalogueNormalizationError,
)
from app.instruments.providers.upstox_catalogue import PROFILE_VERSION
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
)
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)


EFFECTIVE_FROM = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
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
    assert not (tmp_path / "artifacts").exists()
    assert await _counts(settings, INGESTION_MODELS) == {model.__tablename__: 0 for model in INGESTION_MODELS}


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
) -> CatalogueIngestionCommand:
    return CatalogueIngestionCommand(
        profile=PROFILE_VERSION,
        file=file,
        effective_from=effective_from,
        effective_until=None,
        idempotency_key=idempotency_key,
        expected_compressed_sha256=None,
        supersedes_catalogue_record_id=None,
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


def _fixture_variant(tmp_path: Path, payload: str) -> Path:
    path = tmp_path / "variant.json.gz"
    path.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    return path


def _expected_object_key(retained_path: Path) -> str:
    compressed_sha256 = hashlib.sha256(retained_path.read_bytes()).hexdigest()
    return f"sha256/{compressed_sha256[:2]}/{compressed_sha256}.json.gz"
