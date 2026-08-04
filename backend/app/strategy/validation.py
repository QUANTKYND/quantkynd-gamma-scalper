from app.strategy.models import StrategyContractV1


def validate_strategy_contract(config: StrategyContractV1) -> StrategyContractV1:
    return StrategyContractV1.model_validate(config.model_dump(mode="python"))
