import json
from dataclasses import replace
from pathlib import Path

import app.cli.run_gamma_simulation as simulation_cli
import app.simulation.engine as simulation_engine
from app.cli.run_gamma_simulation import main


CONFIG = Path(__file__).parents[3] / "config/strategies/nifty-long-gamma-v1.yaml"
MARKET_CONFIG = Path(__file__).parents[3] / "config/simulation/nifty-synthetic-market-v1.yaml"


def test_simulation_cli_writes_completed_run(tmp_path, capsys) -> None:
    result = main(
        [
            "--strategy-config",
            str(CONFIG),
            "--market-config",
            str(MARKET_CONFIG),
            "--path-generator",
            "gbm",
            "--seed",
            "17",
            "--policy",
            "no_hedge",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["policy"] == "no_hedge"
    assert output["reconciliation_residual"] == "0.00"
    assert Path(output["artifact_directory"]).is_dir()
    assert {
        "simulator_version",
        "strategy_config_hash",
        "market_config_hash",
        "path_config_hash",
        "path_hash",
        "executable_market_state_hash",
        "run_config_hash",
        "policy_config_hash",
        "option_cost_model_hash",
        "futures_cost_model_hash",
        "runtime_risk_hash",
    } <= output.keys()


def test_simulation_cli_rejects_unsupported_policy(tmp_path, capsys) -> None:
    result = main(
        [
            "--strategy-config",
            str(CONFIG),
            "--market-config",
            str(MARKET_CONFIG),
            "--policy",
            "unknown",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    assert result == 1
    assert "unsupported policy" in capsys.readouterr().err


def cli_args(tmp_path: Path) -> list[str]:
    return [
        "--strategy-config",
        str(CONFIG),
        "--market-config",
        str(MARKET_CONFIG),
        "--policy",
        "no_hedge",
        "--artifact-root",
        str(tmp_path),
    ]


def assert_failed_post_identity_run(tmp_path: Path, expected_reason: str) -> None:
    manifests = list((tmp_path / "runs").glob("*/manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["status"] == "failed"
    assert expected_reason in manifest["failure_reason"]
    assert manifest["run_config_hash"].startswith("sha256:")
    assert manifest["selected_expiry"] is None
    assert manifest["selected_strike"] is None
    assert manifest["executable_market_state_hash"] is None
    assert not list((tmp_path / "runs").glob(".tmp-*"))


def test_contract_selection_failure_persists_failed_manifest(tmp_path, capsys, monkeypatch) -> None:
    def fail_selection(*_args, **_kwargs):
        raise ValueError("no eligible expiry")

    monkeypatch.setattr(simulation_engine, "select_simulation_contracts", fail_selection)
    assert main(cli_args(tmp_path)) == 1
    assert "no eligible expiry" in capsys.readouterr().err
    assert_failed_post_identity_run(tmp_path, "no eligible expiry")


def test_engine_failure_persists_failed_manifest(tmp_path, capsys, monkeypatch) -> None:
    def fail_engine(*_args, **_kwargs):
        raise RuntimeError("engine failed")

    monkeypatch.setattr(simulation_cli, "run_simulation", fail_engine)
    assert main(cli_args(tmp_path)) == 1
    assert "engine failed" in capsys.readouterr().err
    assert_failed_post_identity_run(tmp_path, "engine failed")


def test_reconciliation_failure_persists_failed_manifest(tmp_path, capsys, monkeypatch) -> None:
    run = simulation_cli.run_simulation

    def fail_reconciliation(*args, **kwargs):
        return replace(run(*args, **kwargs), status="failed", exit_reason="reconciliation_failure")

    monkeypatch.setattr(simulation_cli, "run_simulation", fail_reconciliation)
    assert main(cli_args(tmp_path)) == 1
    assert "reconciliation_failure" in capsys.readouterr().err
    assert_failed_post_identity_run(tmp_path, "reconciliation_failure")


def test_all_policies_share_non_policy_provenance(tmp_path, capsys) -> None:
    policies = (
        "no_hedge",
        "fixed_interval",
        "delta_threshold",
        "constant_band",
        "whalley_wilmott",
    )
    outputs = []
    for policy in policies:
        args = cli_args(tmp_path) + ["--seed", "29"]
        args[args.index("no_hedge")] = policy
        assert main(args) == 0
        outputs.append(json.loads(capsys.readouterr().out))
    shared_keys = (
        "simulator_version",
        "strategy_config_hash",
        "market_config_hash",
        "path_config_hash",
        "path_hash",
        "executable_market_state_hash",
        "option_cost_model_hash",
        "futures_cost_model_hash",
        "runtime_risk_hash",
        "seed",
    )
    assert all(
        {key: output[key] for key in shared_keys}
        == {key: outputs[0][key] for key in shared_keys}
        for output in outputs[1:]
    )
    assert len({output["policy_config_hash"] for output in outputs}) == len(policies)
    assert len({output["run_config_hash"] for output in outputs}) == len(policies)
