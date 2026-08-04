from __future__ import annotations

import argparse
import asyncio
import json

from pydantic import SecretStr

from app.core.database_config import DatabaseSettings
from app.persistence.postgres.database_safety import (
    DestructiveDatabasePurpose,
    bootstrap_disposable_database_sentinel,
)
from app.persistence.postgres.engine import create_database_engine, dispose_database_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purpose", choices=[item.value for item in DestructiveDatabasePurpose], required=True)
    arguments = parser.parse_args()
    try:
        asyncio.run(_bootstrap(DestructiveDatabasePurpose(arguments.purpose)))
    except Exception:
        print(json.dumps({"status": "failed", "error": "sentinel bootstrap failed"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "purpose": arguments.purpose}, sort_keys=True))
    return 0


async def _bootstrap(purpose: DestructiveDatabasePurpose) -> None:
    settings = DatabaseSettings()
    if purpose == DestructiveDatabasePurpose.INTEGRATION:
        database_url = settings.require_database_url()
    else:
        urls = settings.require_restore_urls()
        database_url = urls.restore
    database_settings = settings.model_copy(update={"database_url": SecretStr(database_url)})
    engine = create_database_engine(database_settings)
    try:
        await bootstrap_disposable_database_sentinel(
            engine,
            database_url,
            settings,
            purpose,
        )
    finally:
        await dispose_database_engine(engine)


if __name__ == "__main__":
    raise SystemExit(main())
