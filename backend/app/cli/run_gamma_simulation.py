from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.execution.models import ExecutionCostParameters
from app.services.rv_run_store import current_git_commit
from app.simulation.artifacts import SimulationManifest, write_simulation_artifacts
from app.simulation.clock import generate_simulation_sessions
from app.simulation.config import (
    load_simulation_market_config,
    policy_config_hash,
    simulation_market_config_hash,
    simulation_run_config_hash,
    stable_hash,
)
from app.simulation.engine import (
    SIMULATOR_VERSION,
    build_simulation_run_config,
    run_simulation,
    simulation_run_id,
)
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
    parser.add_argument("--market-config", required=True, type=Path)
    parser.add_argument("--path-generator", choices=("gbm", "piecewise_volatility"), default="gbm")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--policy")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        strategy = load_strategy_config(args.strategy_config)
        market = load_simulation_market_config(args.market_config)
        policy_id = args.policy or strategy.hedging.default_policy
        if policy_id not in strategy.hedging.benchmark_policies:
            raise ValueError(f"unsupported policy: {policy_id}")
        path = _path(args.path_generator, args.seed, strategy, market)
        config_hash = strategy_config_hash(strategy)
        market_hash = simulation_market_config_hash(market)
        run_config = build_simulation_run_config(
            strategy,
            market,
            path,
            policy_id,
            OPTION_COSTS,
            FUTURES_COSTS,
        )
        run_id = simulation_run_id(run_config)
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
            market_config_hash=market_hash,
            path_generator=path.generator_id,
            path_config_hash=run_config.path_config_hash,
            path_hash=path.path_hash,
            executable_market_state_hash=None,
            seed=path.seed,
            policy_id=policy_id,
            policy_config_hash=policy_config_hash(policy_id, run_config.policy_parameters),
            option_cost_model_hash=stable_hash(run_config.option_cost_model),
            futures_cost_model_hash=stable_hash(run_config.futures_cost_model),
            runtime_risk_hash=stable_hash(run_config.runtime_risk_inputs),
            entry_assumptions=run_config.entry_assumptions.model_dump(mode="json"),
            run_config_hash=simulation_run_config_hash(run_config),
            simulation_clock_config=market.clock.model_dump(mode="json"),
            selected_expiry=None,
            selected_strike=None,
            option_multiplier=market.options.multiplier,
            futures_multiplier=market.futures.multiplier,
            futures_delta_per_contract=market.futures.delta_per_contract,
            accounting_tolerance=run_config.accounting_tolerance,
            quantity_rounding=run_config.quantity_rounding,
            git_commit=current_git_commit(REPO_ROOT),
            artifact_directory=str(final_dir),
            failure_reason=None,
        )
        holder = {}

        def write(run_dir: Path) -> dict[str, object]:
            result = run_simulation(strategy, market, path, policy_id, OPTION_COSTS, FUTURES_COSTS)
            if result.status != "complete":
                raise RuntimeError(result.exit_reason)
            holder["result"] = result
            write_simulation_artifacts(run_dir, manifest, strategy, market, path, result)
            return {
                "selected_expiry": result.call_contract.expiry,
                "selected_strike": result.call_contract.strike,
                "executable_market_state_hash": result.executable_market_state_hash,
            }

        completed = SimulationRunStore(args.artifact_root).create_run(manifest, write)
        if completed.status == "failed":
            print(completed.failure_reason or "simulation failed", file=sys.stderr)
            return 1
        summary = summarize(holder["result"])
        output = {
            "run_id": completed.run_id,
            "strategy_id": strategy.strategy_id,
            "strategy_config_hash": strategy_config_hash(strategy),
            "market_config_hash": market_hash,
            "path_generator": path.generator_id,
            "seed": path.seed,
            "policy": policy_id,
            "exit_reason": summary.exit_reason,
            "terminal_pnl": str(summary.terminal_net_pnl),
            "total_costs": str(summary.total_transaction_costs),
            "hedge_count": summary.hedge_count,
            "maximum_absolute_pre_hedge_delta": summary.maximum_absolute_pre_hedge_net_delta,
            "maximum_absolute_post_hedge_delta": summary.maximum_absolute_post_hedge_residual_delta,
            "reconciliation_residual": str(summary.ledger_reconciliation_residual),
            "artifact_directory": completed.artifact_directory,
        }
        print(json.dumps(output, sort_keys=True))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _path(generator: str, seed: int, strategy, market):
    decision_count = strategy.expiry.holding_horizon_sessions * len(market.clock.decision_times_local) + 1
    exchange_timezone = ZoneInfo(market.clock.timezone)
    sessions = generate_simulation_sessions(
        DEFAULT_START.astimezone(exchange_timezone).date(),
        strategy.expiry.holding_horizon_sessions + 1,
        market.clock,
        strategy.entry.entry_time_local,
    )[:decision_count]
    step_fraction = 1 / (market.clock.trading_periods_per_year * len(market.clock.decision_times_local))
    if generator == "gbm":
        return generate_gbm_path(
            GBMPathConfig(
                24000,
                0.04,
                0.20,
                decision_count - 1,
                step_fraction,
                seed,
            ),
            sessions,
        )
    midpoint = (decision_count - 1) // 2
    return generate_piecewise_path(
        PiecewisePathConfig(
            24000,
            0.04,
            (
                VolatilityRegime(1, midpoint, 0.12),
                VolatilityRegime(midpoint + 1, decision_count - 1, 0.30),
            ),
            decision_count - 1,
            step_fraction,
            seed,
        ),
        sessions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
