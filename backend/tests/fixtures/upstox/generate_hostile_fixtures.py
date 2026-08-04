from __future__ import annotations

import argparse
import gzip
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    arguments = parser.parse_args()
    source = Path(__file__).with_name("NSE.canonical.json").read_text(encoding="utf-8")
    output_dir = Path(arguments.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(
        output_dir / "malformed-underlying-symbol.json.gz",
        source.replace('"underlying_symbol": "NIFTY"', '"underlying_symbol": "BANKNIFTY"', 1),
    )
    _write(
        output_dir / "conflicting-provider-key.json.gz",
        source.replace('"strike_price": 24500.0', '"strike_price": 24600.0', 1),
    )
    _write(
        output_dir / "invalid-tick-size.json.gz",
        source.replace('"tick_size": 5', '"tick_size": 0', 1),
    )
    return 0


def _write(path: Path, payload: str) -> None:
    path.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))


if __name__ == "__main__":
    raise SystemExit(main())
