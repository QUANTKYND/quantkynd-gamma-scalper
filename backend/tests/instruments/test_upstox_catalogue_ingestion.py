from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import asyncio
import gzip
from pathlib import Path

import pytest

from app.instruments.catalogue_parser import parse_json_array_rows, validate_gzip_json_array
from app.instruments.provider_catalogue import (
    CatalogueConflictError,
    CatalogueNormalizationError,
    CatalogueSemanticDiff,
    CatalogueSourceArtifact,
)
from app.instruments.providers.upstox_catalogue import (
    COMPRESSION,
    MEDIA_TYPE,
    PROFILE_VERSION,
    PROVIDER,
    SOURCE_SCHEMA_VERSION,
    bind_upstox_catalogue_plan_recorded_at,
    build_upstox_nifty_catalogue_plan,
)
from app.instruments.temporal_records import (
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
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


def test_runtime_time_binding_preserves_semantic_ids_and_changes_temporal_ids() -> None:
    with validate_gzip_json_array(NSE_JSON_GZ) as artifact:
        plan = build_upstox_nifty_catalogue_plan(
            artifact=artifact,
            source_artifact_id="sha256:" + "a" * 64,
            effective_from=EFFECTIVE_FROM,
            effective_until=None,
            recorded_at=EFFECTIVE_FROM,
            ingestion_run_id="sha256:" + "b" * 64,
        )
    accepted_at = EFFECTIVE_FROM + timedelta(hours=1)
    rebound = bind_upstox_catalogue_plan_recorded_at(plan, accepted_at)

    assert rebound.catalogue.catalogue_version_id == plan.catalogue.catalogue_version_id
    assert {item.version_id for item in rebound.items} == {item.version_id for item in plan.items}
    assert {item.mapping_id for item in rebound.items} == {item.mapping_id for item in plan.items}
    assert rebound.catalogue.recorded_at == accepted_at
    assert {item.version.recorded_at for item in rebound.items} == {accepted_at}
    assert {item.mapping.recorded_at for item in rebound.items} == {accepted_at}
    assert catalogue_temporal_record(rebound.catalogue).record_id != catalogue_temporal_record(
        plan.catalogue
    ).record_id
    assert {
        instrument_version_temporal_record(item.version).record_id for item in rebound.items
    } != {instrument_version_temporal_record(item.version).record_id for item in plan.items}
    assert {
        provider_mapping_temporal_record(item.mapping).record_id for item in rebound.items
    } != {provider_mapping_temporal_record(item.mapping).record_id for item in plan.items}


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


@pytest.mark.parametrize(
    ("row_index", "old", "new", "message"),
    [
        (2, b'"instrument_type":"CE",', b"", "instrument_type"),
        (2, b'"instrument_type":"CE"', b'"instrument_type":"EQ"', "instrument_type"),
        (2, b'"underlying_type":"INDEX",', b"", "underlying_type"),
        (2, b'"underlying_type":"INDEX"', b'"underlying_type":"EQUITY"', "underlying_type"),
        (2, b'"exchange":"NSE"', b'"exchange":"BSE"', "exchange"),
        (2, b'"segment":"NSE_FO"', b'"segment":"NSE_EQ"', "segment"),
        (0, b'"instrument_type":"INDEX",', b"", "instrument_type"),
        (0, b'"instrument_type":"INDEX"', b'"instrument_type":"EQ"', "instrument_type"),
    ],
)
def test_malformed_profile_candidates_reject(
    tmp_path: Path,
    row_index: int,
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    rows = _rows()
    rows[row_index] = rows[row_index].replace(old, new)

    with pytest.raises(CatalogueNormalizationError, match=message):
        _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]"))


def test_other_index_and_stock_derivatives_are_excluded(tmp_path: Path) -> None:
    baseline = _build_plan(_gzip(tmp_path, _catalogue_json(), "baseline.json.gz"))
    rows = _rows()
    rows[2] = rows[2].replace(b"NSE_INDEX|Nifty 50", b"NSE_INDEX|Nifty Bank")
    rows[3] = rows[3].replace(b"NSE_INDEX|Nifty 50", b"NSE_INDEX|Nifty Bank")
    rows.append(
        b'{"instrument_key":"NSE_FO|STOCK_FUT","segment":"NSE_FO","exchange":"NSE","instrument_type":"FUT","underlying_key":"NSE_EQ|INE002A01018","underlying_type":"EQUITY","underlying_symbol":"RELIANCE","expiry":1787769000000,"trading_symbol":"RELIANCE26AUGFUT","lot_size":500,"tick_size":5}'
    )

    plan = _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]", "excluded.json.gz"))

    assert plan.accepted_unique_count == baseline.accepted_unique_count - 1
    assert plan.excluded_count == baseline.excluded_count + 3


def test_exact_raw_duplicate_is_recorded_without_duplicate_membership(tmp_path: Path) -> None:
    plan = _build_plan(_gzip(tmp_path, _catalogue_json()))

    assert plan.exact_duplicate_count == 1
    assert len(plan.memberships) == plan.accepted_unique_count
    assert len({membership.provider_contract_key for membership in plan.memberships}) == len(plan.memberships)


def test_exact_underlying_duplicate_is_recorded_without_duplicate_membership(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows.insert(1, rows[0])

    plan = _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]"))

    assert plan.exact_duplicate_count == 2
    assert len(plan.memberships) == plan.accepted_unique_count
    assert len({membership.provider_contract_key for membership in plan.memberships}) == len(
        plan.memberships
    )


@pytest.mark.parametrize(
    "replacement",
    [
        b'"tick_size":5,"name":"Equivalent projection"',
        b'"tick_size":10',
    ],
)
def test_non_identical_duplicate_provider_key_rejects(tmp_path: Path, replacement: bytes) -> None:
    rows = _rows()
    rows[3] = rows[3].replace(b'"tick_size":5', replacement)

    with pytest.raises(CatalogueConflictError, match="duplicate provider key"):
        _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]"))


def test_distinct_provider_keys_may_bind_the_same_economic_contract(tmp_path: Path) -> None:
    rows = _rows()
    rows[3] = rows[3].replace(b"NSE_FO|OPT", b"NSE_FO|OPT_ALIAS")

    plan = _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]"))
    option_items = [item for item in plan.items if item.projection["kind"] == "option"]

    assert len(option_items) == 2
    assert len({item.instrument_id for item in option_items}) == 1
    assert len({item.mapping_id for item in option_items}) == 2


def test_expiry_conversion_uses_exchange_local_midnight_boundary(tmp_path: Path) -> None:
    midnight_milliseconds = 1_777_573_800_000
    before_rows = _rows()
    at_rows = _rows()
    for index in (1, 2, 3):
        before_rows[index] = before_rows[index].replace(b"1787769000000", str(midnight_milliseconds - 1).encode())
        at_rows[index] = at_rows[index].replace(b"1787769000000", str(midnight_milliseconds).encode())

    before = _build_plan(_gzip(tmp_path, b"[" + b",".join(before_rows) + b"]", "before.json.gz"))
    at = _build_plan(_gzip(tmp_path, b"[" + b",".join(at_rows) + b"]", "at.json.gz"))

    assert _future_expiry(before).isoformat() == "2026-04-30"
    assert _future_expiry(at).isoformat() == "2026-05-01"


@pytest.mark.parametrize("replacement", [b"true", b"1787769000000.5", b"-1"])
def test_invalid_expiry_numeric_forms_reject(tmp_path: Path, replacement: bytes) -> None:
    rows = _rows()
    rows[1] = rows[1].replace(b"1787769000000", replacement)

    with pytest.raises(CatalogueNormalizationError, match="expiry"):
        _build_plan(_gzip(tmp_path, b"[" + b",".join(rows) + b"]"))


def test_catalogue_semantic_diff_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError, match="added"):
        CatalogueSemanticDiff(
            added=-1,
            unchanged=0,
            metadata_changed=0,
            provider_mapping_changed=0,
            disappeared=0,
            excluded=0,
            exact_duplicates=0,
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


def test_validate_only_does_not_create_database_engine(monkeypatch) -> None:
    def fail_engine(*args, **kwargs):
        raise AssertionError("database engine must not be created")

    monkeypatch.setattr("app.services.catalogue_ingestion_service.create_database_engine", fail_engine)
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
    assert result.artifact_object_key is None


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


def _build_plan(path: Path):
    with validate_gzip_json_array(path) as artifact:
        return build_upstox_nifty_catalogue_plan(
            artifact=artifact,
            source_artifact_id="sha256:" + "a" * 64,
            effective_from=EFFECTIVE_FROM,
            effective_until=None,
            recorded_at=EFFECTIVE_FROM,
            ingestion_run_id="sha256:" + "b" * 64,
        )


def _future_expiry(plan):
    return next(item.projection["expiry"] for item in plan.items if item.projection["kind"] == "future")


def _gzip(tmp_path: Path, payload: bytes, name: str = "NSE.json.gz", mtime: int = 0) -> Path:
    path = tmp_path / name
    path.write_bytes(gzip.compress(payload, mtime=mtime))
    return path
