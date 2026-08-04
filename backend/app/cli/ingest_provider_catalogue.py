from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path

from app.core.database_config import DatabaseSettings
from app.instruments.provider_catalogue import (
    CatalogueIdempotencyConflictError,
    CatalogueIngestionError,
)
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--effective-from", required=True)
    parser.add_argument("--effective-until")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--expected-compressed-sha256")
    parser.add_argument("--supersedes-catalogue-record-id")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", choices=("json", "pretty-json"), default="json")
    arguments = parser.parse_args()
    mode = _mode(arguments.validate_only, arguments.dry_run)
    command = CatalogueIngestionCommand(
        profile=arguments.profile,
        file=Path(arguments.file),
        effective_from=_instant(arguments.effective_from, "effective_from"),
        effective_until=_optional_instant(arguments.effective_until, "effective_until"),
        idempotency_key=arguments.idempotency_key,
        expected_compressed_sha256=arguments.expected_compressed_sha256,
        supersedes_catalogue_record_id=arguments.supersedes_catalogue_record_id,
        mode=mode,
    )
    try:
        result = asyncio.run(ingest_provider_catalogue(command, DatabaseSettings()))
    except CatalogueIdempotencyConflictError as exc:
        _print({"status": "failed", "error": exc.code}, arguments.output)
        return 3
    except CatalogueIngestionError as exc:
        _print({"status": "failed", "error": exc.code}, arguments.output)
        return 1
    except Exception:
        _print({"status": "failed", "error": "catalogue_ingestion_failed"}, arguments.output)
        return 2
    _print(result.as_json(), arguments.output)
    return 0


def _mode(validate_only: bool, dry_run: bool) -> str:
    if validate_only and dry_run:
        raise SystemExit("--validate-only and --dry-run are mutually exclusive")
    if validate_only:
        return "validate-only"
    if dry_run:
        return "dry-run"
    return "commit"


def _instant(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _optional_instant(value: str | None, field_name: str) -> datetime | None:
    return _instant(value, field_name) if value is not None else None


def _print(payload: dict[str, object], output: str) -> None:
    indent = 2 if output == "pretty-json" else None
    print(json.dumps(payload, sort_keys=True, indent=indent))


if __name__ == "__main__":
    raise SystemExit(main())
