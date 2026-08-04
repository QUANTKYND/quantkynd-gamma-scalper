from __future__ import annotations

import gzip
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "NSE.canonical.json"
TARGET = ROOT / "NSE.json.gz"


def main() -> int:
    payload = SOURCE.read_bytes()
    with TARGET.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as gzip_file:
            gzip_file.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
