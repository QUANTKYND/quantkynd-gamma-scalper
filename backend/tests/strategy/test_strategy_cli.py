from pathlib import Path

from app.cli.validate_strategy_config import main


CONFIG_PATH = Path(__file__).parents[3] / "config/strategies/nifty-long-gamma-v1.yaml"


def test_valid_configuration_exits_zero(capsys) -> None:
    result = main(["--config", str(CONFIG_PATH)])
    output = capsys.readouterr()
    assert result == 0
    assert "validation status: valid" in output.out
    assert "configuration hash: sha256:" in output.out


def test_invalid_configuration_exits_nonzero(tmp_path, capsys) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("mode: paper\n")
    result = main(["--config", str(path)])
    output = capsys.readouterr()
    assert result == 1
    assert "validation status: invalid" in output.err
