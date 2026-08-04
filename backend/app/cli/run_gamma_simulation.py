from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.execution.models import ExecutionCostParameters
from app.services.rv_run_store import current_git_commit
from app.simulation.artifacts import SimulationManifest, stable_payload_hash, write_simulation_artifacts
from app.simulation.engine import SIMULATOR_VERSION, run_simulation, simulation_run_id
from app.simulation.metrics import summarize
from app.simulation.paths import (
    GBMPathConfig,
    PiecewisePathConfig,
    VolatilityRegime,
    generate_gbm_path,
    generate_piecewise_path,
)
from app.simulation.run_store import SimulationRunStore
from app.strategy.config import load_strategy_config
from app.strategy.hashing import strategy_config_hash


REPO_ROOT = Path(__file__).parents[3]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "backend/artifacts/simulation"
DEFAULT_START = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
OPTION_COSTS = ExecutionCostParameters(Decimal("20"), Decimal("0.0005"), Decimal("0.50"), Decimal("0.25"))
FUTURES_COSTS = ExecutionCostParameters(Decimal("5"), Decimal("0.0001"), Decimal("0.25"), Decimal("0.10"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an offline deterministic gamma simulation")
    parser.add_argument("--strategy-config", required=True, type=Path)
    parser.add_argument("--path-generator", choices=("gbm", "piecewise_volatility"), default="gbm")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--policy")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        strategy = load_strategy_config(args.strategy_config)
        policy_id = args.policy or strategy.hedging.default_policy
        if policy_id not in strategy.hedging.benchmark_policies:
            raise ValueError(f"unsupported policy: {policy_id}")
        path = _path(args.path_generator, args.seed)
        config_hash = strategy_config_hash(strategy)
        run_id = simulation_run_id(config_hash, path.path_hash, policy_id, OPTION_COSTS, FUTURES_COSTS)
        policy_parameters = strategy.hedging.model_dump(mode="json").get(policy_id, {})
        cost_hash = stable_payload_hash({"options": asdict(OPTION_COSTS), "futures": asdict(FUTURES_COSTS)})
        final_dir = args.artifact_root.resolve() / "runs" / run_id
        manifest = SimulationManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            completed_at=None,
            status="running",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            strategy_config_hash=config_hash,
            simulator_version=SIMULATOR_VERSION,
            path_generator=path.generator_id,
            path_config_hash=stable_payload_hash(path.canonical_parameters),
            seed=path.seed,
            market_scenario_hash=path.path_hash,
            policy_id=policy_id,
            policy_parameters=policy_parameters,
            cost_model_hash=cost_hash,
            git_commit=current_git_commit(REPO_ROOT),
            artifact_directory=str(final_dir),
            failure_reason=None,
        )
        holder = {}

        def write(run_dir: Path) -> None:
            result = run_simulation(strategy, path, policy_id, OPTION_COSTS, FUTURES_COSTS)
            if result.status != "complete":
                raise RuntimeError(result.exit_reason)
            holder["result"] = result
            write_simulation_artifacts(run_dir, manifest, strategy, path, result)

        completed = SimulationRunStore(args.artifact_root).create_run(manifest, write)
        if completed.status == "failed":
            print(completed.failure_reason or "simulation failed", file=sys.stderr)
            return 1
        summary = summarize(holder["result"])
        output = {
            "run_id": completed.run_id,
            "strategy_id": strategy.strategy_id,
            "strategy_config_hash": strategy_config_hash(strategy),
            "path_generator": path.generator_id,
            "seed": path.seed,
            "policy": policy_id,
            "exit_reason": summary.exit_reason,
            "terminal_pnl": str(summary.terminal_net_pnl),
            "total_costs": str(summary.total_transaction_costs),
            "hedge_count": summary.hedge_count,
            "maximum_absolute_delta": summary.maximum_absolute_net_delta,
            "reconciliation_residual": str(summary.ledger_reconciliation_residual),
            "artifact_directory": completed.artifact_directory,
        }
        print(json.dumps(output, sort_keys=True))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _path(generator: str, seed: int):
    if generator == "gbm":
        return generate_gbm_path(GBMPathConfig(24000, 0.04, 0.20, 5, 1 / 252, seed, DEFAULT_START))
    return generate_piecewise_path(
        PiecewisePathConfig(
            24000,
            0.04,
            (VolatilityRegime(1, 2, 0.12), VolatilityRegime(3, 5, 0.30)),
            5,
            1 / 252,
            seed,
            DEFAULT_START,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
