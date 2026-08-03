import numpy as np
import pandas as pd

from app.quant.rv_engine import log_returns, realized_variance, realized_volatility


def test_constant_prices_have_zero_realized_volatility():
    prices = pd.Series([100.0] * 8)

    rv = realized_volatility(prices, window=3)

    assert rv.iloc[:3].isna().all()
    assert (rv.dropna() == 0).all()


def test_monotonic_prices_have_positive_realized_volatility():
    prices = pd.Series([100.0, 101.0, 102.5, 104.0, 107.0, 111.0])

    rv = realized_volatility(prices, window=3)

    assert (rv.dropna() > 0).all()


def test_rolling_window_requires_enough_returns():
    prices = pd.Series([100.0, 101.0, 99.0, 102.0, 101.0, 103.0])

    variance = realized_variance(prices, window=4)

    assert variance.iloc[:4].isna().all()
    assert variance.iloc[4:].notna().all()


def test_insufficient_data_returns_nan():
    prices = pd.Series([100.0, 101.0, 102.0])

    rv = realized_volatility(prices, window=3)

    assert rv.isna().all()


def test_log_returns_handle_missing_and_non_positive_prices():
    prices = pd.Series([100.0, np.nan, 101.0, 0.0, 102.0])

    returns = log_returns(prices)

    assert returns.index.equals(prices.index)
    assert np.isfinite(returns.dropna()).all()

