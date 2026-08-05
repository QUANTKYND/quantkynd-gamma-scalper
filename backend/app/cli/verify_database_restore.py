from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.database_config import DatabaseConfigurationError, DatabaseSettings, database_name
from app.instruments.providers.upstox_catalogue import PROFILE_VERSION, PROVIDER
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    DestructiveDatabaseSafetyError,
    assert_distinct_database_servers,
    destructive_database_lease,
)
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import (
    deterministic_temporal_fixture,
    seed_temporal_fixture,
)
from app.persistence.postgres.migrations import upgrade_to_head
from app.persistence.postgres.models import (
    CatalogueIngestionRunRow,
    CatalogueMembershipRow,
    CatalogueRowOutcomeRow,
    CatalogueSourceArtifactRow,
    CatalogueVersionRecordRow,
    InstrumentVersionRecordRow,
    ProviderMappingRecordRow,
)
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.persistence.postgres.verification import database_revision, durable_snapshot
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)


class RestoreVerificationError(RuntimeError):
    pass


DATA_1_2_TABLES = {
    "catalogue_source_artifacts",
    "catalogue_ingestion_runs",
    "catalogue_row_outcomes",
    "catalogue_memberships",
}
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "upstox" / "NSE.json.gz"
FIXTURE_EFFECTIVE_FROM = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
FIXTURE_SECOND_EFFECTIVE_FROM = datetime(2026, 8, 5, 3, 45, tzinfo=UTC)
FIXTURE_HISTORICAL_EFFECTIVE_FROM = datetime(2026, 8, 1, 3, 45, tzinfo=UTC)
FIXTURE_HISTORICAL_EFFECTIVE_UNTIL = datetime(2026, 8, 3, 3, 45, tzinfo=UTC)
FIXTURE_IDEMPOTENCY_KEYS = (
    "DATA-1.2-restore-verifier-fixture-a",
    "DATA-1.2-restore-verifier-fixture-b",
    "DATA-1.2-restore-verifier-fixture-h",
)


def main() -> int:
    try:
        settings = DatabaseSettings()
        urls = settings.require_restore_urls()
        _require_postgres_tools()
        result = asyncio.run(_verify(settings, urls.source, urls.restore))
    except (
        DatabaseConfigurationError,
        DestructiveDatabaseSafetyError,
        RestoreVerificationError,
    ) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    except ValueError:
        print(json.dumps({"status": "failed", "error": "restore configuration is invalid"}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "error": "restore verification failed"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


async def _verify(
    settings: DatabaseSettings,
    source_url: str,
    restore_url: str,
) -> dict[str, object]:
    source_engine = create_database_engine(
        settings.model_copy(update={"database_url": SecretStr(source_url)})
    )
    restore_engine = create_database_engine(
        settings.model_copy(update={"database_url": SecretStr(restore_url)})
    )
    dump_removed = False
    try:
        async with destructive_database_lease(
            source_engine,
            source_url,
            settings,
            DestructiveDatabasePurpose.INTEGRATION,
        ) as source_lease:
            async with destructive_database_lease(
                restore_engine,
                restore_url,
                settings,
                DestructiveDatabasePurpose.RESTORE,
            ) as restore_lease:
                assert_distinct_database_servers(source_lease, restore_lease)
                await source_lease.drop_and_recreate_public()
                await asyncio.to_thread(upgrade_to_head, source_url)
                fixture = deterministic_temporal_fixture()
                await seed_temporal_fixture(
                    PostgresUnitOfWork(create_session_factory(source_engine)),
                    fixture,
                )
                await _seed_catalogue_fixture(settings, source_url)
                artifact_before_dump = await _verified_artifact_reference(source_engine, settings)
                with tempfile.TemporaryDirectory(prefix="quantkynd-restore-") as directory:
                    dump_path = Path(directory) / "catalogue.dump"
                    await asyncio.to_thread(_run_pg_dump, source_url, dump_path)
                    await restore_lease.drop_public_for_restore()
                    await asyncio.to_thread(_run_pg_restore, restore_url, dump_path)
                dump_removed = not dump_path.exists()
                result = await _compare(
                    source_engine,
                    restore_engine,
                    fixture,
                    settings,
                    artifact_before_dump,
                )
                await restore_lease.recheck_sentinel()
                await restore_lease.connection.commit()
    finally:
        await dispose_database_engine(source_engine)
        await dispose_database_engine(restore_engine)
    if not dump_removed:
        raise RestoreVerificationError("temporary PostgreSQL dump was not removed")
    return {
        **result,
        "dump_removed": True,
        "target_safety_rechecked": True,
    }


async def _seed_catalogue_fixture(settings: DatabaseSettings, source_url: str) -> None:
    first = await ingest_provider_catalogue(
        CatalogueIngestionCommand(
            profile=PROFILE_VERSION,
            file=FIXTURE_PATH,
            effective_from=FIXTURE_EFFECTIVE_FROM,
            effective_until=None,
            idempotency_key=FIXTURE_IDEMPOTENCY_KEYS[0],
            expected_compressed_sha256=None,
            supersedes_catalogue_record_id=None,
            mode="commit",
        ),
        settings.model_copy(update={"database_url": SecretStr(source_url)}),
    )
    rows = json.loads(gzip.decompress(FIXTURE_PATH.read_bytes()).decode("utf-8"))
    future = next(row for row in rows if row.get("instrument_type") == "FUT")
    future["trading_symbol"] = str(future["trading_symbol"]) + "-UPDATED"
    with tempfile.TemporaryDirectory(prefix="quantkynd-catalogue-b-") as directory:
        second_path = Path(directory) / "NSE-B.json.gz"
        second_path.write_bytes(
            gzip.compress(
                json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                mtime=0,
            )
        )
        command = CatalogueIngestionCommand(
            profile=PROFILE_VERSION,
            file=second_path,
            effective_from=FIXTURE_SECOND_EFFECTIVE_FROM,
            effective_until=None,
            idempotency_key=FIXTURE_IDEMPOTENCY_KEYS[1],
            expected_compressed_sha256=None,
            supersedes_catalogue_record_id=first.catalogue_record_id,
            mode="commit",
        )
        second = await ingest_provider_catalogue(
            command,
            settings.model_copy(update={"database_url": SecretStr(source_url)}),
        )
        future["trading_symbol"] = str(future["trading_symbol"]) + "-BACKFILL"
        historical_path = Path(directory) / "NSE-H.json.gz"
        historical_path.write_bytes(
            gzip.compress(
                json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                mtime=0,
            )
        )
        await ingest_provider_catalogue(
            CatalogueIngestionCommand(
                profile=PROFILE_VERSION,
                file=historical_path,
                effective_from=FIXTURE_HISTORICAL_EFFECTIVE_FROM,
                effective_until=FIXTURE_HISTORICAL_EFFECTIVE_UNTIL,
                idempotency_key=FIXTURE_IDEMPOTENCY_KEYS[2],
                expected_compressed_sha256=None,
                supersedes_catalogue_record_id=second.catalogue_record_id,
                mode="commit",
            ),
            settings.model_copy(update={"database_url": SecretStr(source_url)}),
        )


async def _compare(
    source_engine,
    restore_engine,
    fixture,
    settings: DatabaseSettings,
    artifact_before_dump: dict[str, object],
) -> dict[str, object]:
    source_revision = await database_revision(source_engine)
    restore_revision = await database_revision(restore_engine)
    source_counts, source_digest = await durable_snapshot(source_engine)
    restore_counts, restore_digest = await durable_snapshot(restore_engine)
    source_reads = await _representative_reads(source_engine, fixture)
    restore_reads = await _representative_reads(restore_engine, fixture)
    source_catalogue_reads = await _catalogue_representative_reads(source_engine)
    restore_catalogue_reads = await _catalogue_representative_reads(restore_engine)
    artifact_after_restore = await _verified_artifact_reference(restore_engine, settings)
    if source_revision != restore_revision:
        raise RestoreVerificationError("restored Alembic revision does not match source")
    if source_counts != restore_counts or source_digest != restore_digest:
        raise RestoreVerificationError("restored durable rows do not match source")
    if source_reads != restore_reads:
        raise RestoreVerificationError("restored representative reads do not match source")
    if source_catalogue_reads != restore_catalogue_reads:
        raise RestoreVerificationError("restored catalogue representative reads do not match source")
    if artifact_before_dump != artifact_after_restore:
        raise RestoreVerificationError("restored catalogue artifact reference does not match source")
    _require_nonzero_data_1_2_counts(source_counts)
    return {
        "source_revision": source_revision,
        "restored_revision": restore_revision,
        "row_counts": source_counts,
        "canonical_digest": source_digest,
        "digest_match": True,
        "semantic_and_record_ids_match": True,
        "representative_query_match": True,
        "catalogue_representative_query_match": True,
        "catalogue_representative_reads": source_catalogue_reads,
        "artifact_reference": artifact_after_restore,
        "artifact_reference_hash_valid": True,
        "artifact_bytes_external_to_database": True,
    }


async def _representative_reads(engine, fixture) -> dict[str, object]:
    base = fixture.base
    factory = create_session_factory(engine)
    async with PostgresUnitOfWork(factory) as unit_of_work:
        mapping_historical = await unit_of_work.instruments.resolve_provider_key(
            base.provider_mapping.provider,
            base.provider_mapping.provider_contract_key,
            base.provider_mapping.effective_from,
            base.provider_mapping.recorded_at,
        )
        mapping_current = await unit_of_work.instruments.resolve_provider_key(
            base.provider_mapping.provider,
            base.provider_mapping.provider_contract_key,
            base.provider_mapping.effective_from,
            None,
        )
        session_historical = await unit_of_work.trading_sessions.resolve(
            base.session.exchange,
            base.session.session_date,
            base.session.session_kind.value,
            base.session_version.recorded_at,
        )
        session_current = await unit_of_work.trading_sessions.resolve(
            base.session.exchange,
            base.session.session_date,
            base.session.session_kind.value,
            None,
        )
        catalogue_historical = await unit_of_work.catalogues.resolve(
            base.catalogue.provider,
            fixture.catalogue_successor.effective_from,
            base.catalogue.recorded_at,
        )
        catalogue_known_before_effective = await unit_of_work.catalogues.resolve(
            base.catalogue.provider,
            fixture.catalogue_successor.effective_from - timedelta(microseconds=1),
            fixture.catalogue_successor.recorded_at,
        )
        catalogue_current = await unit_of_work.catalogues.resolve(
            base.catalogue.provider,
            fixture.catalogue_successor.effective_from,
            None,
        )
    return {
        "mapping_historical": _identity(mapping_historical, "mapping_id"),
        "mapping_current": _identity(mapping_current, "mapping_id"),
        "session_historical": _identity(session_historical, "session_version_id"),
        "session_current": _identity(session_current, "session_version_id"),
        "catalogue_historical": _identity(catalogue_historical, "catalogue_version_id"),
        "catalogue_known_before_effective": _identity(
            catalogue_known_before_effective,
            "catalogue_version_id",
        ),
        "catalogue_current": _identity(catalogue_current, "catalogue_version_id"),
    }


async def _catalogue_representative_reads(engine) -> dict[str, object]:
    direct = await _direct_catalogue_reads(engine)
    first_run, second_run, historical_run = direct["ingestion_runs"]
    first_memberships, second_memberships, historical_memberships = direct["memberships"]
    provider_key = str(first_memberships[0]["provider_contract_key"])
    historical_market_time = FIXTURE_HISTORICAL_EFFECTIVE_FROM + timedelta(hours=1)
    factory = create_session_factory(engine)
    async with PostgresUnitOfWork(factory) as unit_of_work:
        catalogue_current = await unit_of_work.catalogues.resolve(
            f"{PROVIDER}:{PROFILE_VERSION}",
            FIXTURE_SECOND_EFFECTIVE_FROM,
            None,
        )
        catalogue_before_second_known = await unit_of_work.catalogues.resolve(
            f"{PROVIDER}:{PROFILE_VERSION}",
            FIXTURE_SECOND_EFFECTIVE_FROM,
            datetime.fromisoformat(str(first_run["recorded_at"])),
        )
        catalogue_known_before_effective = await unit_of_work.catalogues.resolve(
            f"{PROVIDER}:{PROFILE_VERSION}",
            FIXTURE_SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
            datetime.fromisoformat(str(second_run["recorded_at"])),
        )
        mapping_current = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            provider_key,
            FIXTURE_SECOND_EFFECTIVE_FROM,
            None,
        )
        mapping_before_second_known = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            provider_key,
            FIXTURE_SECOND_EFFECTIVE_FROM,
            datetime.fromisoformat(str(first_run["recorded_at"])),
        )
        mapping_known_before_effective = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            provider_key,
            FIXTURE_SECOND_EFFECTIVE_FROM - timedelta(microseconds=1),
            datetime.fromisoformat(str(second_run["recorded_at"])),
        )
        catalogue_historical_before_known = await unit_of_work.catalogues.resolve(
            f"{PROVIDER}:{PROFILE_VERSION}",
            historical_market_time,
            datetime.fromisoformat(str(second_run["recorded_at"])),
        )
        catalogue_historical_after_known = await unit_of_work.catalogues.resolve(
            f"{PROVIDER}:{PROFILE_VERSION}",
            historical_market_time,
            datetime.fromisoformat(str(historical_run["recorded_at"])),
        )
        mapping_historical_before_known = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            provider_key,
            historical_market_time,
            datetime.fromisoformat(str(second_run["recorded_at"])),
        )
        mapping_historical_after_known = await unit_of_work.instruments.resolve_provider_key(
            PROVIDER,
            provider_key,
            historical_market_time,
            datetime.fromisoformat(str(historical_run["recorded_at"])),
        )
    if catalogue_before_second_known is None or (
        catalogue_before_second_known.catalogue_version_id
        != first_run["catalogue_version_id"]
    ):
        raise RestoreVerificationError("catalogue A is not reproducible before B is known")
    if catalogue_known_before_effective is None or (
        catalogue_known_before_effective.catalogue_version_id
        != first_run["catalogue_version_id"]
    ):
        raise RestoreVerificationError("catalogue A is not active before B is market-effective")
    if catalogue_current is None or (
        catalogue_current.catalogue_version_id != second_run["catalogue_version_id"]
    ):
        raise RestoreVerificationError("catalogue B is not the current eligible catalogue")
    first_mapping_id = first_memberships[0]["mapping_id"]
    second_mapping_id = second_memberships[0]["mapping_id"]
    if mapping_before_second_known is None or mapping_before_second_known.mapping_id != first_mapping_id:
        raise RestoreVerificationError("mapping A is not reproducible before B is known")
    if mapping_known_before_effective is None or (
        mapping_known_before_effective.mapping_id != first_mapping_id
    ):
        raise RestoreVerificationError("mapping A is not active before B is market-effective")
    if mapping_current is None or mapping_current.mapping_id != second_mapping_id:
        raise RestoreVerificationError("mapping B is not the current eligible mapping")
    historical_mapping_id = historical_memberships[0]["mapping_id"]
    if catalogue_historical_before_known is not None or mapping_historical_before_known is not None:
        raise RestoreVerificationError("historical backfill is visible before it is known")
    if catalogue_historical_after_known is None or (
        catalogue_historical_after_known.catalogue_version_id
        != historical_run["catalogue_version_id"]
    ):
        raise RestoreVerificationError("historical catalogue is not reproducible after it is known")
    if mapping_historical_after_known is None or (
        mapping_historical_after_known.mapping_id != historical_mapping_id
    ):
        raise RestoreVerificationError("historical mapping is not reproducible after it is known")
    binding_continuity = all(
        first_membership["instrument_id"]
        == second_membership["instrument_id"]
        == historical_membership["instrument_id"]
        for first_membership, second_membership, historical_membership in zip(
            first_memberships,
            second_memberships,
            historical_memberships,
            strict=True,
        )
    )
    if not binding_continuity:
        raise RestoreVerificationError("provider binding changed economic instrument identity")
    return {
        **direct,
        "catalogue_current": _identity(catalogue_current, "catalogue_version_id"),
        "catalogue_before_second_known": _identity(
            catalogue_before_second_known,
            "catalogue_version_id",
        ),
        "catalogue_known_before_effective": _identity(
            catalogue_known_before_effective,
            "catalogue_version_id",
        ),
        "provider_mapping_current": _identity(mapping_current, "mapping_id"),
        "provider_mapping_before_second_known": _identity(
            mapping_before_second_known,
            "mapping_id",
        ),
        "provider_mapping_known_before_effective": _identity(
            mapping_known_before_effective,
            "mapping_id",
        ),
        "catalogue_historical_before_known": _identity(
            catalogue_historical_before_known,
            "catalogue_version_id",
        ),
        "catalogue_historical_after_known": _identity(
            catalogue_historical_after_known,
            "catalogue_version_id",
        ),
        "provider_mapping_historical_before_known": _identity(
            mapping_historical_before_known,
            "mapping_id",
        ),
        "provider_mapping_historical_after_known": _identity(
            mapping_historical_after_known,
            "mapping_id",
        ),
        "provider_binding_continuity": binding_continuity,
    }


async def _direct_catalogue_reads(engine) -> dict[str, object]:
    async with engine.connect() as connection:
        runs = (
            await connection.execute(
                select(*CatalogueIngestionRunRow.__table__.columns)
                .where(CatalogueIngestionRunRow.idempotency_key.in_(FIXTURE_IDEMPOTENCY_KEYS))
                .order_by(CatalogueIngestionRunRow.recorded_at)
            )
        ).mappings().all()
        if len(runs) != 3:
            raise RestoreVerificationError("expected three catalogue ingestion runs")
        artifacts = []
        outcomes_by_run = []
        memberships_by_catalogue = []
        for run in runs:
            artifacts.append(
                (
                    await connection.execute(
                        select(*CatalogueSourceArtifactRow.__table__.columns).where(
                            CatalogueSourceArtifactRow.source_artifact_id
                            == run["source_artifact_id"]
                        )
                    )
                ).mappings().one()
            )
            outcomes_by_run.append(
                (
                    await connection.execute(
                        select(
                            CatalogueRowOutcomeRow.row_outcome_id,
                            CatalogueRowOutcomeRow.disposition,
                            CatalogueRowOutcomeRow.provider_contract_key,
                            CatalogueRowOutcomeRow.instrument_id,
                            CatalogueRowOutcomeRow.version_id,
                            CatalogueRowOutcomeRow.mapping_id,
                        )
                        .where(
                            CatalogueRowOutcomeRow.ingestion_run_id
                            == run["ingestion_run_id"]
                        )
                        .order_by(CatalogueRowOutcomeRow.physical_row_number)
                    )
                ).mappings().all()
            )
            memberships_by_catalogue.append(
                (
                    await connection.execute(
                        select(
                            CatalogueMembershipRow.membership_id,
                            CatalogueMembershipRow.instrument_id,
                            CatalogueMembershipRow.version_id,
                            CatalogueMembershipRow.mapping_id,
                            CatalogueMembershipRow.provider_contract_key,
                        )
                        .where(
                            CatalogueMembershipRow.catalogue_version_id
                            == run["catalogue_version_id"]
                        )
                        .order_by(CatalogueMembershipRow.provider_contract_key)
                    )
                ).mappings().all()
            )
        successor_edges = []
        catalogue_successor_edges = []
        for transition_index in range(1, len(runs)):
            prior_run = runs[transition_index - 1]
            current_run = runs[transition_index]
            prior_memberships = memberships_by_catalogue[transition_index - 1]
            current_memberships = memberships_by_catalogue[transition_index]
            prior_by_key = {row["provider_contract_key"]: row for row in prior_memberships}
            current_by_key = {row["provider_contract_key"]: row for row in current_memberships}
            for provider_key in sorted(prior_by_key.keys() & current_by_key.keys()):
                prior_membership = prior_by_key[provider_key]
                current_membership = current_by_key[provider_key]
                prior_version_record = (
                    await connection.execute(
                        select(InstrumentVersionRecordRow.record_id).where(
                            InstrumentVersionRecordRow.version_id
                            == prior_membership["version_id"]
                        )
                    )
                ).scalar_one()
                current_version_record = (
                    await connection.execute(
                        select(
                            InstrumentVersionRecordRow.record_id,
                            InstrumentVersionRecordRow.supersedes_record_id,
                        ).where(
                            InstrumentVersionRecordRow.version_id
                            == current_membership["version_id"]
                        )
                    )
                ).mappings().one()
                prior_mapping_record = (
                    await connection.execute(
                        select(ProviderMappingRecordRow.record_id).where(
                            ProviderMappingRecordRow.mapping_id
                            == prior_membership["mapping_id"]
                        )
                    )
                ).scalar_one()
                current_mapping_record = (
                    await connection.execute(
                        select(
                            ProviderMappingRecordRow.record_id,
                            ProviderMappingRecordRow.supersedes_record_id,
                        ).where(
                            ProviderMappingRecordRow.mapping_id
                            == current_membership["mapping_id"]
                        )
                    )
                ).mappings().one()
                successor_edges.append(
                    {
                        "transition_index": transition_index,
                        "provider_contract_key": provider_key,
                        "instrument_id": current_membership["instrument_id"],
                        "prior_version_record_id": prior_version_record,
                        "current_version_record_id": current_version_record["record_id"],
                        "version_supersedes_record_id": current_version_record[
                            "supersedes_record_id"
                        ],
                        "prior_mapping_record_id": prior_mapping_record,
                        "current_mapping_record_id": current_mapping_record["record_id"],
                        "mapping_supersedes_record_id": current_mapping_record[
                            "supersedes_record_id"
                        ],
                    }
                )
            current_catalogue_record = (
                await connection.execute(
                    select(
                        CatalogueVersionRecordRow.record_id,
                        CatalogueVersionRecordRow.supersedes_record_id,
                    ).where(
                        CatalogueVersionRecordRow.record_id
                        == current_run["catalogue_record_id"]
                    )
                )
            ).mappings().one()
            catalogue_successor_edges.append(dict(current_catalogue_record))
            if (
                current_catalogue_record["supersedes_record_id"]
                != prior_run["catalogue_record_id"]
            ):
                raise RestoreVerificationError("catalogue knowledge successor edge is invalid")
    if any(
        edge["version_supersedes_record_id"] != edge["prior_version_record_id"]
        or edge["mapping_supersedes_record_id"] != edge["prior_mapping_record_id"]
        for edge in successor_edges
    ):
        raise RestoreVerificationError("catalogue version or mapping successor edge is invalid")
    return {
        "ingestion_runs": tuple(
            {
                "ingestion_run_id": run["ingestion_run_id"],
                "command_digest": run["command_digest"],
                "catalogue_version_id": run["catalogue_version_id"],
                "catalogue_record_id": run["catalogue_record_id"],
                "source_artifact_id": run["source_artifact_id"],
                "recorded_at": run["recorded_at"].isoformat(),
            }
            for run in runs
        ),
        "source_artifacts": tuple(
            {
                "source_artifact_id": artifact["source_artifact_id"],
                "artifact_object_key": artifact["artifact_object_key"],
                "compressed_sha256": artifact["compressed_sha256"],
                "decompressed_sha256": artifact["decompressed_sha256"],
            }
            for artifact in artifacts
        ),
        "row_outcomes": tuple(
            tuple(dict(row) for row in outcomes) for outcomes in outcomes_by_run
        ),
        "memberships": tuple(
            tuple(dict(row) for row in memberships)
            for memberships in memberships_by_catalogue
        ),
        "catalogue_successor_edges": tuple(catalogue_successor_edges),
        "version_and_mapping_successor_edges": tuple(successor_edges),
        "excluded_by_profile_counts": tuple(
            sum(1 for row in outcomes if row["disposition"] == "excluded_by_profile")
            for outcomes in outcomes_by_run
        ),
    }


async def _verified_artifact_reference(
    engine,
    settings: DatabaseSettings,
) -> dict[str, object]:
    root = Path(settings.require_catalogue_artifact_root())
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(
                    CatalogueSourceArtifactRow.source_artifact_id,
                    CatalogueSourceArtifactRow.artifact_object_key,
                    CatalogueSourceArtifactRow.compressed_sha256,
                ).order_by(CatalogueSourceArtifactRow.source_artifact_id)
            )
        ).mappings().all()
    if len(rows) != 3:
        raise RestoreVerificationError("expected exactly three catalogue source artifacts")
    references = []
    for row in rows:
        object_path = root / str(row["artifact_object_key"])
        if not object_path.is_file() or object_path.is_symlink():
            raise RestoreVerificationError("catalogue artifact reference is missing or unsafe")
        digest = hashlib.sha256(object_path.read_bytes()).hexdigest()
        if "sha256:" + digest != row["compressed_sha256"]:
            raise RestoreVerificationError("catalogue artifact reference hash is invalid")
        references.append(
            {
                "source_artifact_id": row["source_artifact_id"],
                "artifact_object_key": row["artifact_object_key"],
                "compressed_sha256": row["compressed_sha256"],
            }
        )
    return {"artifacts": tuple(references)}


def _require_nonzero_data_1_2_counts(counts: dict[str, int]) -> None:
    zero = sorted(table for table in DATA_1_2_TABLES if counts.get(table, 0) <= 0)
    if zero:
        raise RestoreVerificationError(
            "restored DATA-1.2 fixture has zero rows: " + ", ".join(zero)
        )


def _identity(value, attribute: str) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "semantic_id": getattr(value, attribute),
        "recorded_at": value.recorded_at.isoformat(),
    }


def _require_postgres_tools() -> None:
    missing = [name for name in ("pg_dump", "pg_restore") if shutil.which(name) is None]
    if missing:
        raise RestoreVerificationError(
            f"required PostgreSQL tools are unavailable: {', '.join(missing)}"
        )


def _run_pg_dump(database_url: str, dump_path: Path) -> None:
    _run_pg_tool(
        "pg_dump",
        database_url,
        [
            "--format=custom",
            "--schema=public",
            "--no-owner",
            "--no-privileges",
            f"--file={dump_path}",
        ],
    )


def _run_pg_restore(database_url: str, dump_path: Path) -> None:
    _run_pg_tool(
        "pg_restore",
        database_url,
        [
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            f"--dbname={database_name(database_url)}",
            str(dump_path),
        ],
        include_database=False,
    )


def _run_pg_tool(
    executable: str,
    database_url: str,
    arguments: list[str],
    *,
    include_database: bool = True,
) -> None:
    url = make_url(database_url)
    environment = os.environ.copy()
    if url.password is not None:
        environment["PGPASSWORD"] = url.password
    command = [
        executable,
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 5432),
        "--username",
        url.username or "",
    ]
    if include_database:
        command.extend(["--dbname", url.database or ""])
    command.extend(arguments)
    completed = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RestoreVerificationError(f"{executable} failed")


if __name__ == "__main__":
    raise SystemExit(main())
