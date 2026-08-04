import math

import numpy as np
import pandas as pd
import pytest

from app.quant.rv_engine import (
    annualized_variance,
    close_to_close_realized_variance,
    close_to_close_realized_volatility,
    log_returns,
    mean_absolute_return_volatility_proxy,
    realized_variance,
    realized_volatility,
    squared_log_returns,
)


def _hand_prices() -> pd.Series:
    return pd.Series(
        [100.0, 101.0, 99.0, 102.0],
        index=pd.date_range("2025-01-01", periods=4, freq="D"),
    )


def test_log_returns_are_close_to_close() -> None:
    prices = _hand_prices()
    returns = log_returns(prices)

    assert math.isnan(returns.iloc[0])
    assert returns.iloc[1] == pytest.approx(math.log(101.0 / 100.0))
    assert returns.iloc[2] == pytest.approx(math.log(99.0 / 101.0))
    assert returns.iloc[3] == pytest.approx(math.log(102.0 / 99.0))
    assert returns.index.equals(prices.index)


def test_squared_log_returns_are_variance_contributions() -> None:
    prices = _hand_prices()
    contributions = squared_log_returns(prices)
    r1 = math.log(101.0 / 100.0)
    r2 = math.log(99.0 / 101.0)

    assert contributions.iloc[1] == pytest.approx(r1**2)
    assert contributions.iloc[2] == pytest.approx(r2**2)


def test_one_session_variance_equals_squared_return() -> None:
    prices = _hand_prices()

    variance = close_to_close_realized_variance(prices, window=1)

    assert variance.iloc[1] == pytest.approx(math.log(101.0 / 100.0) ** 2)


def test_three_session_variance_sums_squared_returns() -> None:
    prices = _hand_prices()
    r1 = math.log(101.0 / 100.0)
    r2 = math.log(99.0 / 101.0)
    r3 = math.log(102.0 / 99.0)
    expected_rv = r1**2 + r2**2 + r3**2

    variance = realized_variance(prices, window=3)

    assert variance.iloc[:3].isna().all()
    assert variance.iloc[-1] == pytest.approx(expected_rv)


def test_annualized_variance_and_volatility_use_horizon_divisor() -> None:
    prices = _hand_prices()
    r1 = math.log(101.0 / 100.0)
    r2 = math.log(99.0 / 101.0)
    r3 = math.log(102.0 / 99.0)
    expected_rv = r1**2 + r2**2 + r3**2
    expected_ann_var = expected_rv * 252 / 3
    expected_ann_vol = math.sqrt(expected_ann_var)

    variance = close_to_close_realized_variance(prices, window=3)
    volatility = realized_volatility(prices, window=3)

    assert annualized_variance(variance.iloc[-1], horizon_sessions=3) == pytest.approx(
        expected_ann_var
    )
    assert volatility.iloc[-1] == pytest.approx(expected_ann_vol)


def test_constant_prices_produce_zero_after_warmup() -> None:
    prices = pd.Series([100.0] * 8)

    variance = realized_variance(prices, window=3)
    volatility = close_to_close_realized_volatility(prices, window=3)

    assert variance.iloc[:3].isna().all()
    assert (variance.dropna() == 0).all()
    assert (volatility.dropna() == 0).all()


def test_insufficient_history_returns_nan() -> None:
    prices = pd.Series([100.0, 101.0, 102.0])

    assert realized_variance(prices, window=3).isna().all()
    assert realized_volatility(prices, window=3).isna().all()


def test_invalid_prices_do_not_emit_infinity() -> None:
    prices = pd.Series([100.0, np.nan, 101.0, 0.0, -1.0, 102.0])

    returns = log_returns(prices)
    variance = realized_variance(prices, window=1)

    assert np.isfinite(returns.dropna()).all()
    assert np.isfinite(variance.dropna()).all()


def test_non_series_input_raises() -> None:
    with pytest.raises(TypeError):
        log_returns([100.0, 101.0])


@pytest.mark.parametrize("window", [0, -1, 1.5, True])
def test_invalid_window_raises(window) -> None:
    with pytest.raises(ValueError):
        realized_variance(pd.Series([100.0, 101.0]), window=window)


def test_non_zero_mean_path_is_not_sample_variance() -> None:
    returns = pd.Series([0.01, 0.02, 0.03])
    prices = pd.Series(100.0 * np.exp(np.r_[0.0, returns.cumsum()]))
    expected_sum = float((returns**2).sum())
    sample_variance = float(returns.var(ddof=1))

    variance = realized_variance(prices, window=3).iloc[-1]

    assert variance == pytest.approx(expected_sum)
    assert variance != pytest.approx(sample_variance)


def test_legacy_absolute_return_proxy_is_explicit_and_distinct() -> None:
    prices = _hand_prices()

    proxy = mean_absolute_return_volatility_proxy(prices, window=3).iloc[-1]
    volatility = realized_volatility(prices, window=3).iloc[-1]

    assert proxy > 0
    assert proxy != pytest.approx(volatility)
