from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "app" / "market_data" / "upstox" / "proto"
PROTO_PATH = PROTO_DIR / "MarketDataFeed.proto"
PROTO_SHA256 = "ded335a0c7d2054011c2c0e06f276007a3186d1e212268d85d665788e42916c4"
GENERATED_FILES = ("MarketDataFeed_pb2.py", "MarketDataFeed_pb2.pyi")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if _sha256(PROTO_PATH) != PROTO_SHA256:
        raise SystemExit("official Upstox V3 Proto hash mismatch")
    with tempfile.TemporaryDirectory(prefix="quantkynd-upstox-v3-") as directory:
        output = Path(directory)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{PROTO_DIR}",
                f"--python_out={output}",
                f"--pyi_out={output}",
                str(PROTO_PATH),
            ],
            check=True,
        )
        drifted = [name for name in GENERATED_FILES if (output / name).read_bytes() != (PROTO_DIR / name).read_bytes()]
        if args.write:
            for name in GENERATED_FILES:
                (PROTO_DIR / name).write_bytes((output / name).read_bytes())
            return 0
        if drifted:
            raise SystemExit(f"generated Upstox V3 schema drift: {', '.join(drifted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
