"""Close-to-close variance and volatility estimators."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def _validate_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _price_series(prices: pd.Series) -> pd.Series:
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")

    numeric = pd.to_numeric(prices, errors="coerce").astype(float)
    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    return numeric.where(numeric > 0)


def log_returns(prices: pd.Series) -> pd.Series:
    """Compute close-to-close log returns, preserving the input index."""

    clean_prices = _price_series(prices)
    returns = np.log(clean_prices).diff()
    returns.name = "log_return"
    return returns.replace([np.inf, -np.inf], np.nan)


def squared_log_returns(prices: pd.Series) -> pd.Series:
    """Return per-session close-to-close variance contributions ``r_t ** 2``."""

    contributions = log_returns(prices).pow(2)
    contributions.name = "squared_log_return"
    return contributions.replace([np.inf, -np.inf], np.nan)


def close_to_close_realized_variance(
    prices: pd.Series,
    window: int = 21,
) -> pd.Series:
    """Rolling sum of squared log returns over completed sessions."""

    _validate_positive_int(window, "window")
    variance = squared_log_returns(prices).rolling(
        window=window,
        min_periods=window,
    ).sum()
    variance.name = f"horizon_variance_{window}d"
    return variance.replace([np.inf, -np.inf], np.nan)


def annualized_variance(
    horizon_variance: Any,
    horizon_sessions: int,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
):
    """Convert cumulative horizon variance into annualized variance."""

    _validate_positive_int(horizon_sessions, "horizon_sessions")
    _validate_positive_int(periods_per_year, "periods_per_year")
    annualized = horizon_variance * periods_per_year / horizon_sessions
    if isinstance(annualized, pd.Series):
        annualized = annualized.replace([np.inf, -np.inf], np.nan)
        annualized.name = f"annualized_variance_{horizon_sessions}d"
    elif isinstance(annualized, pd.DataFrame):
        annualized = annualized.replace([np.inf, -np.inf], np.nan)
    elif not np.isfinite(annualized):
        annualized = math.nan
    return annualized


def annualize_vol(vol: Any, periods_per_year: int = TRADING_DAYS_PER_YEAR):
    """Annualize a volatility estimate using square-root-of-time scaling."""

    _validate_positive_int(periods_per_year, "periods_per_year")
    return vol * math.sqrt(periods_per_year)


def close_to_close_realized_volatility(
    prices: pd.Series,
    window: int = 21,
    annualize: bool = True,
) -> pd.Series:
    """Return square root of horizon variance, optionally annualized."""

    variance = close_to_close_realized_variance(prices, window=window)
    if annualize:
        variance = annualized_variance(variance, horizon_sessions=window)

    vol = np.sqrt(variance.clip(lower=0))
    vol.name = f"annualized_volatility_{window}d" if annualize else f"horizon_volatility_{window}d"
    return vol.replace([np.inf, -np.inf], np.nan)


def mean_absolute_return_volatility_proxy(
    prices: pd.Series,
    window: int = 21,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Explicit legacy diagnostic; not a realized-variance estimator."""

    _validate_positive_int(window, "window")
    _validate_positive_int(periods_per_year, "periods_per_year")
    proxy = log_returns(prices).abs().rolling(window=window, min_periods=window).mean()
    proxy = proxy * math.sqrt(periods_per_year)
    proxy.name = f"mean_absolute_return_volatility_proxy_{window}d"
    return proxy.replace([np.inf, -np.inf], np.nan)


def realized_variance(prices: pd.Series, window: int = 21) -> pd.Series:
    """Alias for the corrected close-to-close horizon variance estimator."""

    return close_to_close_realized_variance(prices, window=window)


def realized_volatility(
    prices: pd.Series,
    window: int = 21,
    annualize: bool = True,
) -> pd.Series:
    """Alias for the corrected close-to-close volatility estimator."""

    return close_to_close_realized_volatility(
        prices,
        window=window,
        annualize=annualize,
    )


def parkinson_volatility(ohlc: pd.DataFrame):
    """Placeholder for a high-low range estimator."""

    raise NotImplementedError("Parkinson volatility will be added with OHLC support.")


def yang_zhang_volatility(ohlc: pd.DataFrame):
    """Placeholder for a gap-aware OHLC estimator."""

    raise NotImplementedError("Yang-Zhang volatility will be added with OHLC support.")
