from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from app.simulation.metrics import summarize
from app.simulation.paths import GeneratedPath
from app.simulation.results import SimulationResult
from app.strategy.models import StrategyContractV1


REQUIRED_SIMULATION_ARTIFACTS = (
    "manifest.json",
    "strategy-config.json",
    "path-config.json",
    "path.csv",
    "market-states.csv",
    "option-valuations.csv",
    "hedge-decisions.csv",
    "risk-decisions.csv",
    "order-intents.csv",
    "fills.csv",
    "ledger.csv",
    "positions.csv",
    "pnl-attribution.csv",
    "summary.json",
)


class SimulationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: Literal["running", "complete", "failed"]
    strategy_id: str
    strategy_version: int
    strategy_config_hash: str
    simulator_version: str
    path_generator: str
    path_config_hash: str
    seed: int | None
    market_scenario_hash: str
    policy_id: str
    policy_parameters: dict[str, object]
    cost_model_hash: str
    git_commit: str | None
    artifact_directory: str
    failure_reason: str | None


def stable_payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_value).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def write_simulation_artifacts(
    run_dir: Path,
    manifest: SimulationManifest,
    strategy: StrategyContractV1,
    path: GeneratedPath,
    result: SimulationResult,
) -> None:
    _write_json(run_dir / "strategy-config.json", strategy.model_dump(mode="json"))
    _write_json(
        run_dir / "path-config.json",
        {
            "generator_id": path.generator_id,
            "generator_version": path.generator_version,
            "seed": path.seed,
            "canonical_parameters": path.canonical_parameters,
            "path_hash": path.path_hash,
        },
    )
    _write_csv(run_dir / "path.csv", [{"timestamp": state.timestamp, "spot": state.spot} for state in path.states])
    _write_csv(run_dir / "market-states.csv", [asdict(item) for item in result.market_states])
    _write_csv(run_dir / "option-valuations.csv", [asdict(item) for item in result.option_valuations])
    _write_csv(run_dir / "hedge-decisions.csv", [asdict(item) for item in result.hedge_decisions])
    _write_csv(run_dir / "risk-decisions.csv", [asdict(item) for item in result.risk_decisions])
    _write_csv(run_dir / "order-intents.csv", [asdict(item) for item in result.order_intents])
    _write_csv(run_dir / "fills.csv", [asdict(item) for item in result.fills])
    _write_csv(run_dir / "ledger.csv", [asdict(item) for item in result.ledger_entries])
    quantities: dict[str, int] = {}
    for entry in result.ledger_entries:
        if entry.instrument_id:
            quantities[entry.instrument_id] = quantities.get(entry.instrument_id, 0) + entry.quantity_change
    _write_csv(
        run_dir / "positions.csv",
        [{"instrument_id": instrument_id, "terminal_quantity": quantity} for instrument_id, quantity in sorted(quantities.items())],
    )
    _write_csv(run_dir / "pnl-attribution.csv", [asdict(item) for item in result.pnl_attribution])
    _write_json(run_dir / "summary.json", summarize(result).as_dict())


def write_manifest(path: Path, manifest: SimulationManifest) -> None:
    _write_json(path, manifest.model_dump(mode="json"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_value) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame([{key: _json_value(value) for key, value in row.items()} for row in rows]).to_csv(path, index=False)


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
