import json
from pathlib import Path

from app.cli.run_gamma_simulation import main
from app.simulation.artifacts import MANIFEST_SCHEMA_VERSION, SimulationManifest
from app.simulation.config import stable_hash
from app.simulation.engine import SIMULATOR_VERSION


STRATEGY_CONFIG = Path(__file__).parents[3] / "config/strategies/nifty-long-gamma-v1.yaml"
MARKET_CONFIG = Path(__file__).parents[3] / "config/simulation/nifty-synthetic-market-v2.yaml"


def test_cli_and_completed_artifacts_have_consistent_version_identity(tmp_path, capsys) -> None:
    status = main(
        [
            "--strategy-config",
            str(STRATEGY_CONFIG),
            "--market-config",
            str(MARKET_CONFIG),
            "--path-generator",
            "gbm",
            "--seed",
            "17",
            "--policy",
            "constant_band",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    artifact_directory = Path(output["artifact_directory"])
    manifest_payload = json.loads((artifact_directory / "manifest.json").read_text())
    run_config_payload = json.loads((artifact_directory / "run-config.json").read_text())
    market_config_payload = json.loads((artifact_directory / "market-config.json").read_text())
    path_config_payload = json.loads((artifact_directory / "path-config.json").read_text())
    manifest = SimulationManifest.model_validate(manifest_payload)

    assert status == 0
    assert output["simulator_version"] == manifest.simulator_version
    assert manifest.simulator_version == run_config_payload["simulator_version"]
    assert run_config_payload["simulator_version"] == SIMULATOR_VERSION == "sim-1.2"
    assert output["market_schema_version"] == market_config_payload["schema_version"] == 2
    assert output["run_schema_version"] == run_config_payload["schema_version"] == 2
    assert output["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION == 2
    assert manifest.manifest_schema_version == MANIFEST_SCHEMA_VERSION
    assert output["path_generator_version"] == path_config_payload["generator_version"] == 2
    assert manifest.market_config_hash == stable_hash(market_config_payload)
    assert manifest.run_config_hash == stable_hash(run_config_payload)
    assert output["market_config_hash"] == manifest.market_config_hash
    assert output["run_config_hash"] == manifest.run_config_hash
