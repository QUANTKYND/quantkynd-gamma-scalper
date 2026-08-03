"""Realized-volatility estimators built from close-to-close log returns."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def _validate_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _price_series(prices: pd.Series) -> pd.Series:
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")

    numeric = pd.to_numeric(prices, errors="coerce").astype(float)
    return numeric.where(numeric > 0)


def log_returns(prices: pd.Series) -> pd.Series:
    """Compute close-to-close log returns, preserving the input index."""

    clean_prices = _price_series(prices)
    returns = np.log(clean_prices).diff()
    returns.name = "log_return"
    return returns.replace([np.inf, -np.inf], np.nan)


def realized_variance(prices: pd.Series, window: int = 21) -> pd.Series:
    """Estimate rolling close-to-close variance from log returns.

    For windows greater than one this uses the sample variance of returns. For
    ``window=1`` there is no sample variance, so the single squared return is
    used as the realized one-period variance proxy.
    """

    _validate_positive_int(window, "window")
    returns = log_returns(prices)

    if window == 1:
        variance = returns.pow(2)
    else:
        variance = returns.rolling(window=window, min_periods=window).var(ddof=1)

    variance.name = f"rv_var_{window}"
    return variance


def annualize_vol(vol: Any, periods_per_year: int = TRADING_DAYS_PER_YEAR):
    """Annualize a volatility estimate using square-root-of-time scaling."""

    _validate_positive_int(periods_per_year, "periods_per_year")
    return vol * math.sqrt(periods_per_year)


def realized_volatility(
    prices: pd.Series,
    window: int = 21,
    annualize: bool = True,
) -> pd.Series:
    """Compute rolling close-to-close realized volatility."""

    variance = realized_variance(prices, window=window)
    vol = np.sqrt(variance.clip(lower=0))

    if annualize:
        vol = annualize_vol(vol)

    vol.name = f"rv_{window}"
    return vol


def parkinson_volatility(ohlc: pd.DataFrame):
    """Placeholder for a high-low range estimator."""

    raise NotImplementedError("Parkinson volatility will be added with OHLC support.")


def yang_zhang_volatility(ohlc: pd.DataFrame):
    """Placeholder for a gap-aware OHLC estimator."""

    raise NotImplementedError("Yang-Zhang volatility will be added with OHLC support.")

