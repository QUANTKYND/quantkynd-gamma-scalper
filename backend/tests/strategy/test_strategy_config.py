from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.strategy.config import load_strategy_config
from app.strategy.hashing import strategy_config_hash
from app.strategy.models import StrategyContractV1


CONFIG_PATH = Path(__file__).parents[3] / "config/strategies/nifty-long-gamma-v1.yaml"


def payload() -> dict:
    return load_strategy_config(CONFIG_PATH).model_dump(mode="python")


def test_valid_yaml_loads() -> None:
    contract = load_strategy_config(CONFIG_PATH)
    assert contract.strategy_id == "nifty-long-gamma-straddle"
    assert contract.position.structure == "long_straddle"


@pytest.mark.parametrize("field", ["mode", "position", "hedging"])
def test_missing_required_fields_fail(field: str) -> None:
    candidate = payload()
    candidate.pop(field)
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


def test_unknown_fields_fail() -> None:
    candidate = payload()
    candidate["unexpected"] = True
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("mode",), "paper"),
        (("position", "structure"), "long_call"),
        (("hedging", "default_policy"), "future_policy"),
        (("expiry", "choose"), "latest_eligible"),
    ],
)
def test_unsupported_values_fail(path: tuple[str, ...], value: object) -> None:
    candidate = payload()
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("expiry", "minimum_remaining_sessions"), 6),
        (("expiry", "maximum_remaining_sessions"), 6),
        (("position", "maximum_concurrent_positions"), 2),
        (("position", "units"), 0),
        (("hedging", "fixed_interval", "interval_steps"), 0),
        (("hedging", "whalley_wilmott", "risk_aversion_per_inr"), 0),
        (("hedging", "whalley_wilmott", "transaction_cost_rate"), -0.1),
        (("risk", "maximum_hedges_per_session"), 0),
    ],
)
def test_cross_field_and_numeric_constraints(path: tuple[str, ...], value: object) -> None:
    candidate = payload()
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


def test_constant_band_boundaries_are_ordered() -> None:
    candidate = payload()
    candidate["hedging"]["constant_band"]["lower_net_delta_units"] = 0.05
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


def test_entry_timezone_is_valid() -> None:
    candidate = payload()
    candidate["entry"]["exchange_timezone"] = "Mars/Olympus"
    with pytest.raises(ValidationError):
        StrategyContractV1.model_validate(candidate)


def test_hash_is_stable_and_excludes_created_at() -> None:
    contract = load_strategy_config(CONFIG_PATH)
    changed_timestamp = contract.model_copy(update={"created_at": datetime(2030, 1, 1, tzinfo=UTC)})
    reordered = StrategyContractV1.model_validate(dict(reversed(list(payload().items()))))
    assert strategy_config_hash(contract) == strategy_config_hash(changed_timestamp)
    assert strategy_config_hash(contract) == strategy_config_hash(reordered)


def test_behavioral_change_changes_hash() -> None:
    contract = load_strategy_config(CONFIG_PATH)
    candidate = payload()
    candidate["risk"]["maximum_quote_age_seconds"] = 4
    changed = StrategyContractV1.model_validate(candidate)
    assert strategy_config_hash(contract) != strategy_config_hash(changed)
