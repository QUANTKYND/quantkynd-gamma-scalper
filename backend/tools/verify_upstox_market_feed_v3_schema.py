from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.market_data.upstox.proto import MarketDataFeed_pb2


PROTO_DIR = ROOT / "app" / "market_data" / "upstox" / "proto"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    manifest = json.loads((PROTO_DIR / "schema-manifest.json").read_text(encoding="utf-8"))
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
