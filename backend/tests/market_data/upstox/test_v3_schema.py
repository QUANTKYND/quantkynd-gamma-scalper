import hashlib
import json
from pathlib import Path

from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.market_data.upstox.v3_schema import UPSTOX_V3_PROTO_PATH, UPSTOX_V3_SCHEMA_SHA256
from tools.generate_upstox_market_feed_v3 import validate_generation_environment
from tools.verify_upstox_market_feed_v3_schema import validate_manifest_ownership
import pytest


def test_owned_proto_and_descriptor_are_frozen() -> None:
    assert len(UPSTOX_V3_PROTO_PATH.read_bytes()) == 2070
    assert hashlib.sha256(UPSTOX_V3_PROTO_PATH.read_bytes()).hexdigest() == UPSTOX_V3_SCHEMA_SHA256
    assert MarketDataFeed_pb2.DESCRIPTOR.package == "com.upstox.marketdatafeederv3udapi.rpc.proto"
    assert MarketDataFeed_pb2.FeedResponse.DESCRIPTOR.name == "FeedResponse"
    assert MarketDataFeed_pb2.FeedResponse.DESCRIPTOR.fields_by_name["currentTs"].number == 3
    assert MarketDataFeed_pb2.Feed.DESCRIPTOR.oneofs_by_name["FeedUnion"].fields[2].number == 3


def test_schema_manifest_matches_generated_files() -> None:
    directory = Path(MarketDataFeed_pb2.__file__).parent
    manifest = json.loads((directory / "schema-manifest.json").read_text())
    assert manifest["proto_sha256"] == UPSTOX_V3_SCHEMA_SHA256
    assert manifest["generated_python_sha256"] == hashlib.sha256((directory / "MarketDataFeed_pb2.py").read_bytes()).hexdigest()
    assert manifest["generated_stub_sha256"] == hashlib.sha256((directory / "MarketDataFeed_pb2.pyi").read_bytes()).hexdigest()
    assert manifest["descriptor_sha256"] == hashlib.sha256(MarketDataFeed_pb2.DESCRIPTOR.serialized_pb).hexdigest()
    validate_manifest_ownership(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_id", "other"),
        ("source_url", "https://example.invalid/schema.proto"),
        ("downloaded_at", "not-a-time"),
        ("downloaded_at", "2026-08-05T05:30:00+05:30"),
        ("protobuf_runtime_range", ">=7,<9"),
        ("protobuf_runtime_resolved", "7.35.0"),
        ("generator_package", "other"),
        ("generator_version", "1.82.0"),
    ],
)
def test_schema_manifest_ownership_drift_fails(field, value) -> None:
    directory = Path(MarketDataFeed_pb2.__file__).parent
    manifest = json.loads((directory / "schema-manifest.json").read_text())
    manifest[field] = value
    with pytest.raises(ValueError, match="ownership drift"):
        validate_manifest_ownership(manifest)


def test_generation_environment_requires_pinned_versions() -> None:
    validate_generation_environment("1.82.1", "7.35.1")
    with pytest.raises(ValueError, match="grpcio-tools"):
        validate_generation_environment("1.82.0", "7.35.1")
    with pytest.raises(ValueError, match="protobuf"):
        validate_generation_environment("1.82.1", "8.0.0")
