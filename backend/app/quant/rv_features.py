"""Feature engineering for realized-volatility forecasting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.quant.rv_engine import realized_volatility


def _rv_series(rv: pd.Series) -> pd.Series:
    if not isinstance(rv, pd.Series):
        raise TypeError("rv must be a pandas Series")

    numeric = pd.to_numeric(rv, errors="coerce").astype(float)
    return numeric.replace([np.inf, -np.inf], np.nan)


def rv_lag_features(rv: pd.Series, lags=(1, 5, 21)) -> pd.DataFrame:
    """Return lagged RV values so each row uses only older observations."""

    clean_rv = _rv_series(rv)
    return pd.DataFrame(
        {f"rv_lag_{lag}": clean_rv.shift(lag) for lag in lags},
        index=clean_rv.index,
    )


def rv_rolling_features(rv: pd.Series, windows=(5, 21, 63)) -> pd.DataFrame:
    """Return HAR-style rolling mean RV features using prior observations."""

    clean_rv = _rv_series(rv)
    past_rv = clean_rv.shift(1)
    return pd.DataFrame(
        {
            f"rv_{window}d": past_rv.rolling(window=window, min_periods=window).mean()
            for window in windows
        },
        index=clean_rv.index,
    )


def rv_ratio_short_long(
    rv: pd.Series,
    short: int = 5,
    long: int = 21,
) -> pd.Series:
    """Ratio of short-horizon to long-horizon prior RV."""

    clean_rv = _rv_series(rv)
    past_rv = clean_rv.shift(1)
    short_mean = past_rv.rolling(window=short, min_periods=short).mean()
    long_mean = past_rv.rolling(window=long, min_periods=long).mean()
    ratio = short_mean / long_mean.replace(0, np.nan)
    ratio = ratio.replace([np.inf, -np.inf], np.nan)
    ratio.name = f"rv_ratio_{short}_{long}"
    return ratio


def rv_zscore(rv: pd.Series, window: int = 21) -> pd.Series:
    """Z-score of prior RV against its prior rolling distribution."""

    clean_rv = _rv_series(rv)
    past_rv = clean_rv.shift(1)
    mean = past_rv.rolling(window=window, min_periods=window).mean()
    std = past_rv.rolling(window=window, min_periods=window).std(ddof=0)
    zscore = (past_rv - mean) / std.replace(0, np.nan)
    zscore = zscore.replace([np.inf, -np.inf], np.nan)
    zscore.name = f"rv_z_{window}"
    return zscore


def rv_regime(rv: pd.Series, window: int = 63) -> pd.Series:
    """Classify prior RV as low, normal, or high versus its rolling history."""

    clean_rv = _rv_series(rv)
    past_rv = clean_rv.shift(1)
    mean = past_rv.rolling(window=window, min_periods=window).mean()
    std = past_rv.rolling(window=window, min_periods=window).std(ddof=0)
    zscore = (past_rv - mean) / std.replace(0, np.nan)

    regime = pd.Series(pd.NA, index=clean_rv.index, dtype="object", name="rv_regime")
    eligible = mean.notna()
    regime.loc[eligible] = "normal"
    regime.loc[zscore <= -1.0] = "low"
    regime.loc[zscore >= 1.0] = "high"
    return regime


def build_rv_feature_frame(prices: pd.Series) -> pd.DataFrame:
    """Build aligned, time-safe RV features from a close price series."""

    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")

    daily_rv = realized_volatility(prices, window=1, annualize=True)
    features = rv_rolling_features(daily_rv, windows=(1, 5, 21, 63))
    features["rv_ratio_5_21"] = rv_ratio_short_long(daily_rv, short=5, long=21)
    features["rv_z_21"] = rv_zscore(daily_rv, window=21)
    features["rv_regime"] = rv_regime(daily_rv, window=63)
    return features.reindex(prices.index)

