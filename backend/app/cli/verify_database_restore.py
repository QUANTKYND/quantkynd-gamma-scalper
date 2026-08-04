from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy.engine import make_url

from app.core.database_config import DatabaseConfigurationError, DatabaseSettings, database_name
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
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.persistence.postgres.verification import database_revision, durable_snapshot


class RestoreVerificationError(RuntimeError):
    pass


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
                await asyncio.to_thread(upgrade_to_head, source_url)
                fixture = deterministic_temporal_fixture()
                await seed_temporal_fixture(
                    PostgresUnitOfWork(create_session_factory(source_engine)),
                    fixture,
                )
                with tempfile.TemporaryDirectory(prefix="quantkynd-data11-") as directory:
                    dump_path = Path(directory) / "data11.dump"
                    await asyncio.to_thread(_run_pg_dump, source_url, dump_path)
                    await restore_lease.drop_public_for_restore()
                    await asyncio.to_thread(_run_pg_restore, restore_url, dump_path)
                dump_removed = not dump_path.exists()
                result = await _compare(source_engine, restore_engine, fixture)
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


async def _compare(source_engine, restore_engine, fixture) -> dict[str, object]:
    source_revision = await database_revision(source_engine)
    restore_revision = await database_revision(restore_engine)
    source_counts, source_digest = await durable_snapshot(source_engine)
    restore_counts, restore_digest = await durable_snapshot(restore_engine)
    source_reads = await _representative_reads(source_engine, fixture)
    restore_reads = await _representative_reads(restore_engine, fixture)
    if source_revision != restore_revision:
        raise RestoreVerificationError("restored Alembic revision does not match source")
    if source_counts != restore_counts or source_digest != restore_digest:
        raise RestoreVerificationError("restored durable rows do not match source")
    if source_reads != restore_reads:
        raise RestoreVerificationError("restored representative reads do not match source")
    return {
        "source_revision": source_revision,
        "restored_revision": restore_revision,
        "row_counts": source_counts,
        "canonical_digest": source_digest,
        "digest_match": True,
        "semantic_and_record_ids_match": True,
        "representative_query_match": True,
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
