from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.execution.models import ExecutionCostParameters
from app.services.rv_run_store import current_git_commit
from app.simulation.artifacts import REQUIRED_SIMULATION_ARTIFACTS, SimulationManifest, stable_payload_hash, write_simulation_artifacts
from app.simulation.engine import SIMULATOR_VERSION, run_simulation
from app.simulation.config import load_simulation_market_config
from app.simulation.paths import GBMPathConfig, generate_gbm_path
from app.simulation.run_store import SimulationRunStore
from app.strategy.config import load_strategy_config
from app.strategy.hashing import strategy_config_hash


ZERO = ExecutionCostParameters(*(Decimal("0"),) * 4)


def inputs():
    strategy = load_strategy_config("../config/strategies/nifty-long-gamma-v1.yaml")
    market = load_simulation_market_config("../config/simulation/nifty-synthetic-market-v1.yaml")
    path = generate_gbm_path(GBMPathConfig(24000, 0.03, 0.2, 5, 1 / 252, 17, datetime(2026, 1, 1, tzinfo=UTC)))
    result = run_simulation(strategy, market, path, "no_hedge", ZERO, ZERO)
    return strategy, path, result


def manifest(root: Path, result, strategy, path) -> SimulationManifest:
    return SimulationManifest(
        run_id=result.run_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=None,
        status="running",
        strategy_id=strategy.strategy_id,
        strategy_version=1,
        strategy_config_hash=strategy_config_hash(strategy),
        simulator_version=SIMULATOR_VERSION,
        path_generator=path.generator_id,
        path_config_hash=stable_payload_hash(path.canonical_parameters),
        seed=path.seed,
        market_scenario_hash=path.path_hash,
        policy_id="no_hedge",
        policy_parameters={},
        cost_model_hash=stable_payload_hash({"zero": True}),
        git_commit=None,
        artifact_directory=str(root / "runs" / result.run_id),
        failure_reason=None,
    )


def test_completed_run_has_every_artifact_and_is_immutable(tmp_path) -> None:
    strategy, path, result = inputs()
    store = SimulationRunStore(tmp_path / "simulation")
    base = manifest(store.root, result, strategy, path)
    completed = store.create_run(base, lambda run_dir: write_simulation_artifacts(run_dir, base, strategy, path, result))
    assert completed.status == "complete"
    assert all((store.runs_dir / result.run_id / name).is_file() for name in REQUIRED_SIMULATION_ARTIFACTS)
    assert store.list_manifests()[0].run_id == result.run_id
    with pytest.raises(FileExistsError):
        store.create_run(base, lambda _: None)


def test_failed_run_persists_manifest_and_temp_is_not_listed(tmp_path) -> None:
    strategy, path, result = inputs()
    store = SimulationRunStore(tmp_path / "simulation")
    base = manifest(store.root, result, strategy, path)
    failed = store.create_run(base, lambda _: (_ for _ in ()).throw(RuntimeError("failed deliberately")))
    assert failed.status == "failed"
    assert failed.failure_reason == "failed deliberately"
    assert store.list_manifests()[0].status == "failed"
    temp = store.runs_dir / ".tmp-sim-aaaaaaaaaaaaaaaaaaaa"
    temp.mkdir()
    assert all(item.run_id != "sim-aaaaaaaaaaaaaaaaaaaa" for item in store.list_manifests())


def test_deterministic_artifacts_match_across_roots(tmp_path) -> None:
    strategy, path, result = inputs()
    contents = []
    for name in ("one", "two"):
        store = SimulationRunStore(tmp_path / name)
        base = manifest(store.root, result, strategy, path)
        store.create_run(base, lambda run_dir: write_simulation_artifacts(run_dir, base, strategy, path, result))
        run_dir = store.runs_dir / result.run_id
        contents.append({file: (run_dir / file).read_bytes() for file in REQUIRED_SIMULATION_ARTIFACTS if file != "manifest.json"})
    assert contents[0] == contents[1]
