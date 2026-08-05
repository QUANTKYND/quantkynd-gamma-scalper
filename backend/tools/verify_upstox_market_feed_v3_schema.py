from __future__ import annotations

import hashlib
import json
import sys
from datetime import timedelta, datetime
from pathlib import Path

import google.protobuf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.market_data.upstox.proto import MarketDataFeed_pb2


PROTO_DIR = ROOT / "app" / "market_data" / "upstox" / "proto"
EXPECTED_OWNERSHIP = {
    "schema_id": "upstox-market-data-feed-v3",
    "source_url": "https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto",
    "protobuf_runtime_range": ">=7.35,<8",
    "protobuf_runtime_resolved": "7.35.1",
    "generator_package": "grpcio-tools",
    "generator_version": "1.82.1",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    if mismatches:
        raise ValueError(f"Upstox V3 schema ownership drift: {', '.join(sorted(set(mismatches)))}")
    if manifest["protobuf_runtime_resolved"] != google.protobuf.__version__:
        raise ValueError("Upstox V3 schema ownership drift: active protobuf runtime")


def main() -> int:
    manifest = json.loads((PROTO_DIR / "schema-manifest.json").read_text(encoding="utf-8"))
    try:
        validate_manifest_ownership(manifest)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    proto = (PROTO_DIR / "MarketDataFeed.proto").read_bytes()
    generated = (PROTO_DIR / "MarketDataFeed_pb2.py").read_bytes()
    stub = (PROTO_DIR / "MarketDataFeed_pb2.pyi").read_bytes()
    actual = {
        "proto_byte_count": len(proto),
        "proto_sha256": _sha256_bytes(proto),
        "generated_python_sha256": _sha256_bytes(generated),
        "generated_stub_sha256": _sha256_bytes(stub),
        "descriptor_sha256": _sha256_bytes(MarketDataFeed_pb2.DESCRIPTOR.serialized_pb),
        "package": MarketDataFeed_pb2.DESCRIPTOR.package,
        "root_message": MarketDataFeed_pb2.FeedResponse.DESCRIPTOR.name,
    }
    mismatches = [key for key, value in actual.items() if manifest.get(key) != value]
    if mismatches:
        raise SystemExit(f"Upstox V3 schema verification failed: {', '.join(sorted(mismatches))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
