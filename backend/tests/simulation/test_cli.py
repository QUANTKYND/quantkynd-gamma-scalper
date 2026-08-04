import json
from pathlib import Path

from app.cli.run_gamma_simulation import main


CONFIG = Path(__file__).parents[3] / "config/strategies/nifty-long-gamma-v1.yaml"


def test_simulation_cli_writes_completed_run(tmp_path, capsys) -> None:
    result = main(
        [
            "--strategy-config",
            str(CONFIG),
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


def test_simulation_cli_rejects_unsupported_policy(tmp_path, capsys) -> None:
    result = main(["--strategy-config", str(CONFIG), "--policy", "unknown", "--artifact-root", str(tmp_path)])
    assert result == 1
    assert "unsupported policy" in capsys.readouterr().err
