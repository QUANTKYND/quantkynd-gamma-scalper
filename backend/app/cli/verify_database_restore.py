from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.database_config import DatabaseConfigurationError, DatabaseSettings, database_name
from app.persistence.postgres.engine import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from app.persistence.postgres.fixtures import deterministic_fixture, seed_fixture
from app.persistence.postgres.migrations import upgrade_to_head
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.persistence.postgres.verification import database_revision, durable_snapshot


class RestoreVerificationError(RuntimeError):
    pass


def main() -> int:
    try:
        settings = DatabaseSettings()
        urls = settings.require_restore_urls()
        _require_test_safe(urls.source)
        _require_test_safe(urls.restore)
        _require_postgres_tools()
        upgrade_to_head(urls.source)
        fixture = deterministic_fixture()
        asyncio.run(_seed(urls.source, settings, fixture))
        with tempfile.TemporaryDirectory(prefix="quantkynd-data11-") as directory:
            dump_path = Path(directory) / "data11.dump"
            _run_pg_dump(urls.source, dump_path)
            asyncio.run(_clean_restore_database(urls.restore, settings))
            _run_pg_restore(urls.restore, dump_path)
        result = asyncio.run(_compare(urls.source, urls.restore, settings, fixture))
    except (DatabaseConfigurationError, RestoreVerificationError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "error": "restore verification failed"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


async def _seed(source_url: str, settings: DatabaseSettings, fixture) -> None:
    source_settings = settings.model_copy(update={"database_url": SecretStr(source_url)})
    engine = create_database_engine(source_settings)
    try:
        await seed_fixture(PostgresUnitOfWork(create_session_factory(engine)), fixture)
    finally:
        await dispose_database_engine(engine)


async def _clean_restore_database(restore_url: str, settings: DatabaseSettings) -> None:
    restore_settings = settings.model_copy(update={"database_url": SecretStr(restore_url)})
    engine = create_database_engine(restore_settings)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await dispose_database_engine(engine)


async def _compare(source_url: str, restore_url: str, settings: DatabaseSettings, fixture) -> dict[str, object]:
    source_engine = create_database_engine(
        settings.model_copy(update={"database_url": SecretStr(source_url)})
    )
    restore_engine = create_database_engine(
        settings.model_copy(update={"database_url": SecretStr(restore_url)})
    )
    try:
        source_revision = await database_revision(source_engine)
        restore_revision = await database_revision(restore_engine)
        source_counts, source_digest = await durable_snapshot(source_engine)
        restore_counts, restore_digest = await durable_snapshot(restore_engine)
        source_reads = await _representative_reads(source_engine, fixture)
        restore_reads = await _representative_reads(restore_engine, fixture)
    finally:
        await dispose_database_engine(source_engine)
        await dispose_database_engine(restore_engine)
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
        "representative_query_match": True,
    }


async def _representative_reads(engine, fixture) -> tuple[str | None, str | None]:
    factory = create_session_factory(engine)
    async with PostgresUnitOfWork(factory) as unit_of_work:
        mapping = await unit_of_work.instruments.resolve_provider_key(
            fixture.provider_mapping.provider,
            fixture.provider_mapping.provider_contract_key,
            fixture.provider_mapping.effective_from,
            fixture.provider_mapping.recorded_at,
        )
        session = await unit_of_work.trading_sessions.resolve(
            fixture.session.exchange,
            fixture.session.session_date,
            fixture.session.session_kind.value,
            fixture.session_version.recorded_at,
        )
    return (
        mapping.mapping_id if mapping is not None else None,
        session.session_version_id if session is not None else None,
    )


def _require_postgres_tools() -> None:
    missing = [name for name in ("pg_dump", "pg_restore") if shutil.which(name) is None]
    if missing:
        raise RestoreVerificationError(
            f"required PostgreSQL tools are unavailable: {', '.join(missing)}"
        )


def _require_test_safe(database_url: str) -> None:
    name = database_name(database_url).lower()
    if not any(marker in name for marker in ("test", "restore", "dev", "local")):
        raise RestoreVerificationError(
            "restore verification requires explicitly test-safe database names"
        )


def _run_pg_dump(database_url: str, dump_path: Path) -> None:
    _run_pg_tool(
        "pg_dump",
        database_url,
        ["--format=custom", "--no-owner", "--no-privileges", f"--file={dump_path}"],
    )


def _run_pg_restore(database_url: str, dump_path: Path) -> None:
    _run_pg_tool(
        "pg_restore",
        database_url,
        ["--exit-on-error", "--no-owner", "--no-privileges", f"--dbname={database_name(database_url)}", str(dump_path)],
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
