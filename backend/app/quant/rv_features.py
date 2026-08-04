"""Feature engineering for close-to-close volatility forecasting."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from app.quant.rv_engine import (
    TRADING_DAYS_PER_YEAR,
    annualized_variance,
    close_to_close_realized_variance,
)


DEFAULT_HORIZONS = (1, 5, 21, 63)
FEATURE_COLUMNS = [
    "horizon_variance_1d",
    "horizon_variance_5d",
    "horizon_variance_21d",
    "horizon_variance_63d",
    "annualized_variance_1d",
    "annualized_variance_5d",
    "annualized_variance_21d",
    "annualized_variance_63d",
    "annualized_volatility_1d",
    "annualized_volatility_5d",
    "annualized_volatility_21d",
    "annualized_volatility_63d",
    "variance_ratio_5_21",
    "volatility_zscore_21",
    "regime",
]


def _validate_prices(prices: pd.Series) -> None:
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")


def _validate_horizon(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("horizons must contain positive integers")


def _replace_infinite(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.replace([np.inf, -np.inf], np.nan)


def volatility_zscore(
    annualized_volatility: pd.Series,
    window: int = 63,
) -> pd.Series:
    """Compare current volatility with its prior rolling distribution."""

    current = pd.to_numeric(annualized_volatility, errors="coerce").astype(float)
    prior_mean = current.shift(1).rolling(window=window, min_periods=window).mean()
    prior_std = current.shift(1).rolling(window=window, min_periods=window).std(ddof=0)
    zscore = (current - prior_mean) / prior_std.replace(0, np.nan)
    zscore.name = "volatility_zscore_21"
    return zscore.replace([np.inf, -np.inf], np.nan)


def classify_volatility_regime(zscore: pd.Series) -> pd.Series:
    """Classify volatility as low, normal, high, or unknown from z-scores."""

    clean_zscore = pd.to_numeric(zscore, errors="coerce").astype(float)
    regime = pd.Series("unknown", index=clean_zscore.index, dtype="object", name="regime")
    known = clean_zscore.notna()
    regime.loc[known] = "normal"
    regime.loc[clean_zscore <= -1.0] = "low"
    regime.loc[clean_zscore >= 1.0] = "high"
    return regime


def build_rv_feature_frame(
    prices: pd.Series,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Build explicit, time-safe close-to-close variance features."""

    _validate_prices(prices)
    horizon_list = tuple(horizons)
    for horizon in horizon_list:
        _validate_horizon(horizon)

    features = pd.DataFrame(index=prices.index)
    for horizon in horizon_list:
        horizon_variance = close_to_close_realized_variance(prices, window=horizon)
        ann_variance = annualized_variance(
            horizon_variance,
            horizon_sessions=horizon,
            periods_per_year=periods_per_year,
        )
        ann_volatility = np.sqrt(ann_variance.clip(lower=0))

        features[f"horizon_variance_{horizon}d"] = horizon_variance
        features[f"annualized_variance_{horizon}d"] = ann_variance
        features[f"annualized_volatility_{horizon}d"] = ann_volatility.replace(
            [np.inf, -np.inf],
            np.nan,
        )

    denominator = features["annualized_variance_21d"].replace(0, np.nan)
    features["variance_ratio_5_21"] = features["annualized_variance_5d"] / denominator
    features["volatility_zscore_21"] = volatility_zscore(
        features["annualized_volatility_21d"],
        window=63,
    )
    features["regime"] = classify_volatility_regime(features["volatility_zscore_21"])

    return _replace_infinite(features.reindex(columns=FEATURE_COLUMNS))
