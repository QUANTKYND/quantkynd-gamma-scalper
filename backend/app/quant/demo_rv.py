"""Synthetic realized-volatility demo.

Run from ``backend`` with:
    python -m app.quant.demo_rv
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.quant.rv_backtest import backtest_rv_forecast
from app.quant.rv_engine import realized_volatility
from app.quant.rv_features import build_rv_feature_frame


def synthetic_prices(n: int = 300, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    low_vol = rng.normal(0.0004, 0.006, n // 2)
    high_vol = rng.normal(-0.0001, 0.018, n - len(low_vol))
    returns = np.concatenate([low_vol, high_vol])
    dates = pd.bdate_range("2025-01-02", periods=n)
    prices = 100 * np.exp(np.cumsum(returns))
    return pd.Series(prices, index=dates, name="synthetic_close")


def main() -> None:
    prices = synthetic_prices()
    rv_21 = realized_volatility(prices, window=21)
    features = build_rv_feature_frame(prices)
    result = backtest_rv_forecast(prices, horizon=5)

    latest = pd.DataFrame(
        {
            "latest_21d_rv": [rv_21.dropna().iloc[-1]],
            "rv_5d": [features["rv_5d"].dropna().iloc[-1]],
            "rv_21d": [features["rv_21d"].dropna().iloc[-1]],
            "rv_63d": [features["rv_63d"].dropna().iloc[-1]],
            "rv_ratio_5_21": [features["rv_ratio_5_21"].dropna().iloc[-1]],
            "rv_regime": [features["rv_regime"].dropna().iloc[-1]],
        }
    )
    metrics = pd.DataFrame(result["metrics"]).T

    print("Latest realized-volatility features")
    print(latest.round(4).to_string(index=False))
    print()
    print("Forecast metrics")
    print(metrics.round(4).to_string())


if __name__ == "__main__":
    main()

