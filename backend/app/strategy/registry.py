from __future__ import annotations

from pathlib import Path

from app.strategy.config import load_strategy_config
from app.strategy.models import StrategyContractV1


class StrategyRegistry:
    def __init__(self, paths: tuple[Path, ...]):
        self._contracts = tuple(load_strategy_config(path) for path in paths)

    def get(self, strategy_id: str, strategy_version: int) -> StrategyContractV1:
        for contract in self._contracts:
            if contract.strategy_id == strategy_id and contract.strategy_version == strategy_version:
                return contract
        raise KeyError(f"unknown strategy contract: {strategy_id}@{strategy_version}")
