from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import asyncio
import gzip
from pathlib import Path

import pytest

from app.instruments.catalogue_parser import parse_json_array_rows, validate_gzip_json_array
from app.instruments.provider_catalogue import CatalogueNormalizationError, CatalogueSourceArtifact
from app.instruments.providers.upstox_catalogue import (
    COMPRESSION,
    MEDIA_TYPE,
    PROFILE_VERSION,
    PROVIDER,
    SOURCE_SCHEMA_VERSION,
    build_upstox_nifty_catalogue_plan,
)
from app.services.catalogue_ingestion_service import (
    CatalogueIngestionCommand,
    ingest_provider_catalogue,
)
from app.core.database_config import DatabaseSettings


EFFECTIVE_FROM = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "upstox"
NSE_JSON_GZ = FIXTURE_ROOT / "NSE.json.gz"


def test_upstox_bod_profile_converts_expiry_and_tick_size(tmp_path: Path) -> None:
    with validate_gzip_json_array(NSE_JSON_GZ) as artifact:
        plan = build_upstox_nifty_catalogue_plan(
            artifact=artifact,
            source_artifact_id="sha256:" + "a" * 64,
            effective_from=EFFECTIVE_FROM,
            effective_until=None,
            recorded_at=EFFECTIVE_FROM,
            ingestion_run_id="sha256:" + "b" * 64,
        )

    option = next(item for item in plan.items if item.provider_contract_key.endswith("24500_CE"))

    assert option.projection["expiry"].isoformat() == "2026-08-27"
    assert option.projection["tick_size"] == Decimal("0.05")
    assert {item.projection["kind"] for item in plan.items} == {"underlying", "future", "option"}
    assert {item.projection.get("option_side") for item in plan.items if item.projection["kind"] == "option"} == {"call", "put"}
    assert plan.accepted_unique_count == 4
    assert plan.exact_duplicate_count == 0
    assert plan.excluded_count == 1


def test_row_permutation_preserves_normalized_catalogue_identity(tmp_path: Path) -> None:
    first = _gzip(tmp_path, _catalogue_json(), "first.json.gz")
    second = _gzip(tmp_path, _catalogue_json(reversed_rows=True), "second.json.gz")
    plans = []
    for index, path in enumerate((first, second), start=1):
        with validate_gzip_json_array(path) as artifact:
            plans.append(
                build_upstox_nifty_catalogue_plan(
                    artifact=artifact,
                    source_artifact_id="sha256:" + str(index) * 64,
                    effective_from=EFFECTIVE_FROM,
                    effective_until=None,
                    recorded_at=EFFECTIVE_FROM,
                    ingestion_run_id="sha256:" + str(index + 2) * 64,
                )
            )

    assert plans[0].normalized_catalogue_hash == plans[1].normalized_catalogue_hash
    assert plans[0].catalogue.catalogue_version_id == plans[1].catalogue.catalogue_version_id
    assert {item.version_id for item in plans[0].items} == {item.version_id for item in plans[1].items}
    assert {item.mapping_id for item in plans[0].items} == {item.mapping_id for item in plans[1].items}
    assert {outcome.source_row_occurrence_id for outcome in plans[0].outcomes} != {
        outcome.source_row_occurrence_id for outcome in plans[1].outcomes
    }
    assert {outcome.source_row_semantic_id for outcome in plans[0].outcomes} == {
        outcome.source_row_semantic_id for outcome in plans[1].outcomes
    }


def test_duplicate_count_and_object_key_order_do_not_change_catalogue_identity(tmp_path: Path) -> None:
    baseline = _gzip(tmp_path, _catalogue_json(), "baseline.json.gz")
    duplicate = _gzip(tmp_path, b"[" + b",".join([*_rows(), _rows()[2]]) + b"]", "duplicate.json.gz")
    reordered_keys = _gzip(
        tmp_path,
        b'['
        b'{"trading_symbol":"NIFTY 50","tick_size":5,"segment":"NSE_INDEX","name":"Nifty 50","minimum_lot":1,"lot_size":1,"instrument_type":"INDEX","instrument_key":"NSE_INDEX|Nifty 50","freeze_quantity":0,"exchange_token":"SANITIZED_INDEX_TOKEN","exchange":"NSE","weekly":false},'
        + b",".join(_rows()[1:])
        + b"]",
        "reordered-keys.json.gz",
    )
    plans = []
    for index, path in enumerate((baseline, duplicate, reordered_keys), start=1):
        with validate_gzip_json_array(path) as artifact:
            plans.append(
                build_upstox_nifty_catalogue_plan(
                    artifact=artifact,
                    source_artifact_id="sha256:" + str(index) * 64,
                    effective_from=EFFECTIVE_FROM,
                    effective_until=None,
                    recorded_at=EFFECTIVE_FROM,
                    ingestion_run_id="sha256:" + str(index + 4) * 64,
                )
    )

    assert {plan.catalogue.catalogue_version_id for plan in plans} == {plans[0].catalogue.catalogue_version_id}
    assert plans[1].exact_duplicate_count == plans[0].exact_duplicate_count + 1


def test_duplicate_object_keys_and_bom_are_rejected(tmp_path: Path) -> None:
    duplicate = _gzip(tmp_path, b'[{"instrument_key":"a","instrument_key":"b"}]', "duplicate.json.gz")
    bom = _gzip(tmp_path, b"\xef\xbb\xbf[]", "bom.json.gz")

    with validate_gzip_json_array(duplicate) as artifact:
        with pytest.raises(Exception, match="duplicate"):
            tuple(parse_json_array_rows(artifact.decompressed_path))
    with validate_gzip_json_array(bom) as artifact:
        with pytest.raises(Exception, match="BOM"):
            tuple(parse_json_array_rows(artifact.decompressed_path))


def test_multi_member_gzip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "multi.json.gz"
    path.write_bytes(gzip.compress(b"[]") + gzip.compress(b"[]"))

    with pytest.raises(Exception, match="one member"):
        validate_gzip_json_array(path)


def test_underlying_symbol_mismatch_rejects_in_profile_derivative(tmp_path: Path) -> None:
    rows = _rows()
    rows[2] = rows[2].replace(b'"underlying_symbol":"NIFTY"', b'"underlying_symbol":"BANKNIFTY"')
    path = _gzip(tmp_path, b"[" + b",".join(rows) + b"]")

    with validate_gzip_json_array(path) as artifact:
        with pytest.raises(CatalogueNormalizationError, match="underlying_symbol"):
            build_upstox_nifty_catalogue_plan(
                artifact=artifact,
                source_artifact_id="sha256:" + "a" * 64,
                effective_from=EFFECTIVE_FROM,
                effective_until=None,
                recorded_at=EFFECTIVE_FROM,
                ingestion_run_id="sha256:" + "b" * 64,
            )


def test_validate_only_needs_no_database(tmp_path: Path) -> None:
    command = CatalogueIngestionCommand(
        profile=PROFILE_VERSION,
        file=NSE_JSON_GZ,
        effective_from=EFFECTIVE_FROM,
        effective_until=None,
        idempotency_key=None,
        expected_compressed_sha256=None,
        supersedes_catalogue_record_id=None,
        mode="validate-only",
    )

    result = asyncio.run(ingest_provider_catalogue(command, DatabaseSettings(_env_file=None)))

    assert result.status == "accepted"
    assert result.accepted_unique_count == 4


def test_artifact_identity_tracks_exact_gzip_bytes_and_decompressed_content(tmp_path: Path) -> None:
    same_name = _gzip(tmp_path, _catalogue_json(), "same-name.json.gz", mtime=0)
    other_name = tmp_path / "other-name.json.gz"
    other_name.write_bytes(same_name.read_bytes())
    different_gzip = _gzip(tmp_path, _catalogue_json(), "different-gzip.json.gz", mtime=1)

    artifacts = []
    for path in (same_name, other_name, different_gzip):
        with validate_gzip_json_array(path) as artifact:
            artifacts.append(
                CatalogueSourceArtifact(
                    provider=PROVIDER,
                    profile_version=PROFILE_VERSION,
                    media_type=MEDIA_TYPE,
                    compression=COMPRESSION,
                    compressed_sha256=artifact.compressed_sha256,
                    decompressed_sha256=artifact.decompressed_sha256,
                    compressed_byte_count=artifact.compressed_byte_count,
                    decompressed_byte_count=artifact.decompressed_byte_count,
                    source_schema_version=SOURCE_SCHEMA_VERSION,
                    artifact_object_key="fixture",
                )
            )

    assert artifacts[0].source_artifact_id == artifacts[1].source_artifact_id
    assert artifacts[0].source_artifact_id != artifacts[2].source_artifact_id
    assert artifacts[0].decompressed_sha256 == artifacts[2].decompressed_sha256


def _rows() -> list[bytes]:
    expiry_ms = b"1787769000000"
    return [
        b'{"instrument_key":"NSE_INDEX|Nifty 50","segment":"NSE_INDEX","exchange":"NSE","instrument_type":"INDEX","trading_symbol":"NIFTY 50","lot_size":1,"tick_size":5,"name":"Nifty 50"}',
        b'{"instrument_key":"NSE_FO|FUT","segment":"NSE_FO","exchange":"NSE","instrument_type":"FUT","underlying_key":"NSE_INDEX|Nifty 50","underlying_type":"INDEX","underlying_symbol":"NIFTY","expiry":' + expiry_ms + b',"trading_symbol":"NIFTY26AUGFUT","lot_size":75,"tick_size":5}',
        b'{"instrument_key":"NSE_FO|OPT","segment":"NSE_FO","exchange":"NSE","instrument_type":"CE","underlying_key":"NSE_INDEX|Nifty 50","underlying_type":"INDEX","underlying_symbol":"NIFTY","expiry":' + expiry_ms + b',"strike_price":24500.00,"trading_symbol":"NIFTY26AUG24500CE","lot_size":75,"tick_size":5}',
        b'{"instrument_key":"NSE_FO|OPT","segment":"NSE_FO","exchange":"NSE","instrument_type":"CE","underlying_key":"NSE_INDEX|Nifty 50","underlying_type":"INDEX","underlying_symbol":"NIFTY","expiry":' + expiry_ms + b',"strike_price":24500.00,"trading_symbol":"NIFTY26AUG24500CE","lot_size":75,"tick_size":5}',
        b'{"instrument_key":"NSE_EQ|INE002A01018","segment":"NSE_EQ","exchange":"NSE","instrument_type":"EQ","trading_symbol":"RELIANCE","lot_size":1,"tick_size":5}',
    ]


def _catalogue_json(reversed_rows: bool = False) -> bytes:
    rows = _rows()
    if reversed_rows:
        rows = list(reversed(rows))
    return b"[" + b",".join(rows) + b"]"


def _gzip(tmp_path: Path, payload: bytes, name: str = "NSE.json.gz", mtime: int = 0) -> Path:
    path = tmp_path / name
    path.write_bytes(gzip.compress(payload, mtime=mtime))
    return path
