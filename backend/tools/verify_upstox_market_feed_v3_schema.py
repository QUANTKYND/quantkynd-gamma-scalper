from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.market_data.upstox.schema_verification import (
    validate_manifest_ownership,
    verify_upstox_v3_schema,
)


def main() -> int:
    try:
        verify_upstox_v3_schema()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
