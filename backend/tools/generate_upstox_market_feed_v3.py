from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import subprocess
import sys
import tempfile
from pathlib import Path

import google.protobuf


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "app" / "market_data" / "upstox" / "proto"
PROTO_PATH = PROTO_DIR / "MarketDataFeed.proto"
PROTO_SHA256 = "ded335a0c7d2054011c2c0e06f276007a3186d1e212268d85d665788e42916c4"
GENERATED_FILES = ("MarketDataFeed_pb2.py", "MarketDataFeed_pb2.pyi")
GENERATOR_VERSION = "1.82.1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_generation_environment(generator_version: str, protobuf_version: str) -> None:
    if generator_version != GENERATOR_VERSION:
        raise ValueError(f"grpcio-tools=={GENERATOR_VERSION} is required, found {generator_version}")
    runtime_parts = tuple(int(part) for part in protobuf_version.split(".")[:2])
    if runtime_parts < (7, 35) or runtime_parts >= (8, 0):
        raise ValueError(f"protobuf>=7.35,<8 is required, found {protobuf_version}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        validate_generation_environment(
            importlib.metadata.version("grpcio-tools"),
            google.protobuf.__version__,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
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
