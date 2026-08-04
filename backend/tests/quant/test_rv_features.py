import math

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app.quant.rv_features import (
    FEATURE_COLUMNS,
    build_rv_feature_frame,
    classify_volatility_regime,
    volatility_zscore,
)


def _prices_from_returns(returns: list[float]) -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=len(returns) + 1)
    prices = 100.0 * np.exp(np.r_[0.0, np.cumsum(returns)])
    return pd.Series(prices, index=index)


def _prices(n: int = 140) -> pd.Series:
    returns = [0.001 + ((i % 17) - 8) * 0.0008 for i in range(n - 1)]
    return _prices_from_returns(returns)


def test_feature_frame_has_exact_columns_and_horizons() -> None:
    features = build_rv_feature_frame(_prices())

    assert list(features.columns) == FEATURE_COLUMNS
    assert {
        "horizon_variance_1d",
        "horizon_variance_5d",
        "horizon_variance_21d",
        "horizon_variance_63d",
    }.issubset(features.columns)


def test_each_horizon_uses_sum_of_squared_returns() -> None:
    returns = [0.01, -0.02, 0.03, 0.04, -0.01, 0.02]
    prices = _prices_from_returns(returns)
    features = build_rv_feature_frame(prices)
    expected = sum(value**2 for value in returns[-5:])

    assert features["horizon_variance_5d"].iloc[-1] == pytest.approx(expected)


def test_annualized_values_use_horizon_divisor() -> None:
    returns = [0.01, -0.02, 0.03, 0.04, -0.01, 0.02]
    prices = _prices_from_returns(returns)
    features = build_rv_feature_frame(prices)
    horizon_variance = sum(value**2 for value in returns[-5:])
    expected_ann_var = horizon_variance * 252 / 5
    expected_ann_vol = math.sqrt(expected_ann_var)

    assert features["annualized_variance_5d"].iloc[-1] == pytest.approx(expected_ann_var)
    assert features["annualized_volatility_5d"].iloc[-1] == pytest.approx(expected_ann_vol)


def test_variance_ratio_uses_annualized_variance() -> None:
    prices = _prices()
    features = build_rv_feature_frame(prices)
    row = features.dropna(subset=["variance_ratio_5_21"]).iloc[-1]
    expected = row["annualized_variance_5d"] / row["annualized_variance_21d"]

    assert row["variance_ratio_5_21"] == pytest.approx(expected)


def test_zero_denominator_ratio_yields_nan() -> None:
    prices = pd.Series([100.0] * 90, index=pd.bdate_range("2025-01-02", periods=90))

    features = build_rv_feature_frame(prices)

    assert math.isnan(features["variance_ratio_5_21"].dropna().iloc[0]) if not features[
        "variance_ratio_5_21"
    ].dropna().empty else True
    assert features["variance_ratio_5_21"].isna().all()


def test_zscore_benchmark_excludes_current_observation() -> None:
    values = pd.Series(
        list(range(1, 65)) + [200.0],
        index=pd.bdate_range("2025-01-02", periods=65),
        dtype=float,
    )

    zscore = volatility_zscore(values, window=63)
    prior = values.iloc[-64:-1]
    expected = (values.iloc[-1] - prior.mean()) / prior.std(ddof=0)

    assert zscore.iloc[-1] == pytest.approx(expected)


def test_regime_boundaries() -> None:
    regimes = classify_volatility_regime(pd.Series([-1.0, -0.999, 0.0, 0.999, 1.0, np.nan]))

    assert regimes.tolist() == ["low", "normal", "normal", "normal", "high", "unknown"]


def test_future_price_mutation_does_not_change_origin_or_prior_features() -> None:
    prices = _prices()
    origin_position = 80
    shocked = prices.copy()
    shocked.iloc[origin_position + 1 :] = shocked.iloc[origin_position + 1 :] * 1.5

    before = build_rv_feature_frame(prices)
    after = build_rv_feature_frame(shocked)

    assert_frame_equal(before.iloc[: origin_position + 1], after.iloc[: origin_position + 1])


def test_feature_frame_preserves_index() -> None:
    prices = _prices()

    features = build_rv_feature_frame(prices)

    assert features.index.equals(prices.index)


def test_feature_frame_has_no_infinite_values() -> None:
    features = build_rv_feature_frame(_prices())
    numeric = features.drop(columns=["regime"])

    assert not np.isinf(numeric.to_numpy(dtype=float)).any()
