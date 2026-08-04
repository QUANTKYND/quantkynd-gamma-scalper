from __future__ import annotations

from pathlib import Path

import yaml

from app.strategy.models import StrategyContractV1


def load_strategy_config(path: Path | str) -> StrategyContractV1:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("strategy configuration must be a YAML mapping")
    return StrategyContractV1.model_validate(payload)
