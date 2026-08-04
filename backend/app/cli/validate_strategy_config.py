from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.strategy.config import load_strategy_config
from app.strategy.hashing import strategy_config_hash


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a versioned strategy contract")
    parser.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = load_strategy_config(args.config)
    except Exception as exc:
        print(f"validation status: invalid\nerror: {exc}", file=sys.stderr)
        return 1
    rows = (
        ("strategy ID", contract.strategy_id),
        ("strategy version", contract.strategy_version),
        ("schema version", contract.schema_version),
        ("configuration hash", strategy_config_hash(contract)),
        ("underlying", contract.underlying.name),
        ("structure", contract.position.structure),
        ("forecast horizon", f"{contract.signal.forecast_horizon_sessions} sessions"),
        ("holding horizon", f"{contract.expiry.holding_horizon_sessions} sessions"),
        ("default hedge policy", contract.hedging.default_policy),
        ("validation status", "valid"),
    )
    print("\n".join(f"{label}: {value}" for label, value in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
