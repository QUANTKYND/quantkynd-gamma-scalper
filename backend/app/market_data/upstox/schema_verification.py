from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import google.protobuf

from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.market_data.upstox.v3_schema import UPSTOX_V3_PROTO_PATH


EXPECTED_OWNERSHIP = {
    "schema_id": "upstox-market-data-feed-v3",
    "source_url": "https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto",
    "protobuf_runtime_range": ">=7.35,<8",
    "protobuf_runtime_resolved": "7.35.1",
    "generator_package": "grpcio-tools",
    "generator_version": "1.82.1",
}


def verify_upstox_v3_schema() -> None:
    proto_dir = UPSTOX_V3_PROTO_PATH.parent
    manifest = json.loads((proto_dir / "schema-manifest.json").read_text(encoding="utf-8"))
    validate_manifest_ownership(manifest)
    mismatches = []


    proto = UPSTOX_V3_PROTO_PATH.read_bytes()
    generated = (proto_dir / "MarketDataFeed_pb2.py").read_bytes()
    stub = (proto_dir / "MarketDataFeed_pb2.pyi").read_bytes()
    actual = {
        "proto_byte_count": len(proto),
        "proto_sha256": _sha256(proto),
        "generated_python_sha256": _sha256(generated),
        "generated_stub_sha256": _sha256(stub),
        "descriptor_sha256": _sha256(MarketDataFeed_pb2.DESCRIPTOR.serialized_pb),
        "package": MarketDataFeed_pb2.DESCRIPTOR.package,
        "root_message": MarketDataFeed_pb2.FeedResponse.DESCRIPTOR.name,
    }
    mismatches.extend(key for key, value in actual.items() if manifest.get(key) != value)
    if mismatches:
        raise ValueError(f"Upstox V3 schema verification failed: {', '.join(sorted(set(mismatches)))}")


def validate_manifest_ownership(manifest: dict[str, object]) -> None:
    mismatches = [key for key, value in EXPECTED_OWNERSHIP.items() if manifest.get(key) != value]
    downloaded_at = manifest.get("downloaded_at")
    try:
        parsed = datetime.fromisoformat(str(downloaded_at).replace("Z", "+00:00"))
    except ValueError:
        mismatches.append("downloaded_at")
    else:
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            mismatches.append("downloaded_at")
    if manifest.get("protobuf_runtime_resolved") != google.protobuf.__version__:
        mismatches.append("active protobuf runtime")
    if mismatches:
        raise ValueError(f"Upstox V3 schema ownership drift: {', '.join(sorted(set(mismatches)))}")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
