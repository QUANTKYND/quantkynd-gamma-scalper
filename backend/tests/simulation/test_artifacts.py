import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.execution.models import ExecutionCostParameters
from app.simulation.artifacts import REQUIRED_SIMULATION_ARTIFACTS, SimulationManifest, write_simulation_artifacts
from app.simulation.engine import SIMULATOR_VERSION, run_simulation
from app.simulation.config import (
    load_simulation_market_config,
    policy_config_hash,
    simulation_run_config_hash,
    stable_hash,
)
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.simulation.run_store import SimulationRunStore
from app.strategy.config import load_strategy_config
from app.strategy.hashing import strategy_config_hash
from tests.simulation.support import sessions_for_path


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(
        GBMPathConfig(24000, 0.03, 0.2, 15, 1 / (252 * 3), 17),
        sessions_for_path(strategy, market, 15),
    )
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    return strategy, market, path, result


def manifest(root: Path, result, strategy, market, path) -> SimulationManifest:
    run_config = result.run_config
    return SimulationManifest(
        run_id=result.run_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=None,
        status="running",
        strategy_id=strategy.strategy_id,
        strategy_version=1,
        strategy_config_hash=strategy_config_hash(strategy),
        simulator_version=SIMULATOR_VERSION,
        market_config_hash=result.market_config_hash,
        path_generator=path.generator_id,
        path_config_hash=run_config.path_config_hash,
        path_hash=path.path_hash,
        seed=path.seed,
        policy_id="no_hedge",
        policy_config_hash=policy_config_hash("no_hedge", {}),
        option_cost_model_hash=stable_hash(run_config.option_cost_model),
        futures_cost_model_hash=stable_hash(run_config.futures_cost_model),
        runtime_risk_hash=stable_hash(run_config.runtime_risk_inputs),
        entry_assumptions=run_config.entry_assumptions.model_dump(mode="json"),
        run_config_hash=simulation_run_config_hash(run_config),
        simulation_clock_config=market.clock.model_dump(mode="json"),
        selected_expiry=result.call_contract.expiry,
        selected_strike=result.call_contract.strike,
        option_multiplier=result.call_contract.multiplier,
        futures_multiplier=result.futures_multiplier,
        futures_delta_per_contract=result.futures_delta_per_contract,
        accounting_tolerance=run_config.accounting_tolerance,
        quantity_rounding=run_config.quantity_rounding,
        git_commit=None,
        artifact_directory=str(root / "runs" / result.run_id),
        failure_reason=None,
    )


def test_completed_run_has_every_artifact_and_is_immutable(tmp_path) -> None:
    strategy, market, path, result = inputs()
    store = SimulationRunStore(tmp_path / "simulation")
    base = manifest(store.root, result, strategy, market, path)
    completed = store.create_run(
        base,
        lambda run_dir: write_simulation_artifacts(run_dir, base, strategy, market, path, result),
    )
    assert completed.status == "complete"
    assert all((store.runs_dir / result.run_id / name).is_file() for name in REQUIRED_SIMULATION_ARTIFACTS)
    assert store.list_manifests()[0].run_id == result.run_id
    with pytest.raises(FileExistsError):
        store.create_run(base, lambda _: None)
    run_dir = store.runs_dir / result.run_id
    with (run_dir / "hedge-decisions.csv").open() as stream:
        hedge_columns = set(next(csv.DictReader(stream)))
    with (run_dir / "risk-decisions.csv").open() as stream:
        risk_columns = set(next(csv.DictReader(stream)))
    with (run_dir / "option-valuations.csv").open() as stream:
        valuation_columns = set(next(csv.DictReader(stream)))
    assert {
        "session_date",
        "local_timestamp",
        "utc_timestamp",
        "net_delta_before_decision",
        "net_delta_after_fill",
        "continuous_target_futures_quantity",
        "rounded_requested_futures_quantity",
        "session_hedge_count",
        "total_hedge_count",
    } <= hedge_columns
    assert {"position_pnl_from_entry", "session_pnl", "session_hedge_count", "total_hedge_count"} <= risk_columns
    assert {"unit_price", "unit_delta", "market_value", "portfolio_delta"} <= valuation_columns


def test_failed_run_persists_manifest_and_temp_is_not_listed(tmp_path) -> None:
    strategy, market, path, result = inputs()
    store = SimulationRunStore(tmp_path / "simulation")
    base = manifest(store.root, result, strategy, market, path)
    failed = store.create_run(base, lambda _: (_ for _ in ()).throw(RuntimeError("failed deliberately")))
    assert failed.status == "failed"
    assert failed.failure_reason == "failed deliberately"
    assert failed.run_config_hash == simulation_run_config_hash(result.run_config)
    assert failed.simulation_clock_config == market.clock.model_dump(mode="json")
    assert store.list_manifests()[0].status == "failed"
    temp = store.runs_dir / ".tmp-sim-aaaaaaaaaaaaaaaaaaaa"
    temp.mkdir()
    assert all(item.run_id != "sim-aaaaaaaaaaaaaaaaaaaa" for item in store.list_manifests())


def test_deterministic_artifacts_match_across_roots(tmp_path) -> None:
    strategy, market, path, result = inputs()
    contents = []
    for name in ("one", "two"):
        store = SimulationRunStore(tmp_path / name)
        base = manifest(store.root, result, strategy, market, path)
        store.create_run(
            base,
            lambda run_dir: write_simulation_artifacts(run_dir, base, strategy, market, path, result),
        )
        run_dir = store.runs_dir / result.run_id
        contents.append(
            {
                file: (run_dir / file).read_bytes()
                for file in REQUIRED_SIMULATION_ARTIFACTS
                if file != "manifest.json"
            }
        )
    assert contents[0] == contents[1]
