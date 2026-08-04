import math

import numpy as np
import pandas as pd
import pytest

from app.quant.rv_backtest import (
    backtest_rv_forecast,
    evaluate_forecast,
    make_ewma_variance_forecast,
    make_forward_variance_target,
    make_naive_variance_forecast,
    metric_rows,
    walk_forward_split,
)


def _prices_from_returns(returns: list[float]) -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=len(returns) + 1)
    prices = 100.0 * np.exp(np.r_[0.0, np.cumsum(returns)])
    return pd.Series(prices, index=index)


def _prices(n: int = 180) -> pd.Series:
    returns = [0.0005 + ((i % 19) - 9) * 0.0007 for i in range(n - 1)]
    return _prices_from_returns(returns)


def test_forward_target_uses_returns_after_origin() -> None:
    returns = [0.01, -0.02, 0.03, 0.04, -0.01]
    prices = _prices_from_returns(returns)

    target = make_forward_variance_target(prices, horizon_sessions=2)
    origin = prices.index[2]
    expected_horizon_variance = returns[2] ** 2 + returns[3] ** 2

    assert target.loc[origin, "forward_horizon_variance"] == pytest.approx(
        expected_horizon_variance
    )
    assert target.loc[origin, "target_start"] == prices.index[3]
    assert target.loc[origin, "target_end"] == prices.index[4]


def test_forward_target_does_not_include_origin_return() -> None:
    returns = [0.01, -0.02, 0.03, 0.04, -0.01]
    prices = _prices_from_returns(returns)

    target = make_forward_variance_target(prices, horizon_sessions=2)
    origin = prices.index[2]
    wrong_including_origin = returns[1] ** 2 + returns[2] ** 2

    assert target.loc[origin, "forward_horizon_variance"] != pytest.approx(
        wrong_including_origin
    )


def test_last_horizon_rows_have_no_complete_target() -> None:
    target = make_forward_variance_target(_prices_from_returns([0.01] * 8), horizon_sessions=3)

    assert target["forward_horizon_variance"].iloc[-3:].isna().all()


def test_forecasts_do_not_change_when_future_prices_change() -> None:
    prices = _prices()
    origin_position = 40
    shocked = prices.copy()
    shocked.iloc[origin_position + 1 :] = shocked.iloc[origin_position + 1 :] * 2.0

    before_naive = make_naive_variance_forecast(prices, horizon_sessions=5)
    after_naive = make_naive_variance_forecast(shocked, horizon_sessions=5)
    before_ewma = make_ewma_variance_forecast(prices, horizon_sessions=5)
    after_ewma = make_ewma_variance_forecast(shocked, horizon_sessions=5)
    origin = prices.index[origin_position]

    assert before_naive.loc[origin, "forecast_annualized_variance"] == pytest.approx(
        after_naive.loc[origin, "forecast_annualized_variance"]
    )
    assert before_ewma.loc[origin, "forecast_annualized_variance"] == pytest.approx(
        after_ewma.loc[origin, "forecast_annualized_variance"]
    )


def test_naive_forecast_calculation() -> None:
    returns = [0.01, 0.02, 0.03]
    prices = _prices_from_returns(returns)

    forecast = make_naive_variance_forecast(prices, horizon_sessions=3)
    expected_daily_variance = sum(value**2 for value in returns) / 3
    expected_annualized_variance = expected_daily_variance * 252

    assert forecast["forecast_annualized_variance"].iloc[-1] == pytest.approx(
        expected_annualized_variance
    )


def test_ewma_forecast_calculation() -> None:
    returns = [0.01, 0.02, 0.03, 0.04]
    prices = _prices_from_returns(returns)
    squared_returns = pd.Series([math.nan, *[value**2 for value in returns]])
    expected = squared_returns.ewm(span=3, adjust=False, min_periods=3).mean().iloc[-1] * 252

    forecast = make_ewma_variance_forecast(prices, horizon_sessions=3, ewma_span=3)

    assert forecast["forecast_annualized_variance"].iloc[-1] == pytest.approx(expected)


def test_variance_and_volatility_targets_are_consistent() -> None:
    target = make_forward_variance_target(_prices_from_returns([0.01, 0.02, 0.03, 0.04]), 2)
    row = target.dropna().iloc[1]

    assert row["forward_annualized_volatility"] ** 2 == pytest.approx(
        row["forward_annualized_variance"]
    )


def test_metric_stride_selects_non_overlapping_targets() -> None:
    result = backtest_rv_forecast(_prices(), horizon_sessions=5)
    report = result["report"]
    rows = metric_rows(
        report,
        forecast_column="ewma_forecast_annualized_variance",
        target_column="forward_annualized_variance",
        metric_stride=5,
    )

    assert result["metric_stride"] == 5
    assert result["models"]["ewma"]["variance_metrics"]["n_obs"] == len(rows)
    positions = [report.index.get_loc(index) for index in rows.index[:4]]
    assert np.diff(positions).tolist() == [5, 5, 5]


def test_metric_stride_must_prevent_overlapping_targets() -> None:
    with pytest.raises(ValueError, match="metric_stride must be at least horizon_sessions"):
        backtest_rv_forecast(_prices(), horizon_sessions=5, metric_stride=1)


def test_metrics_include_n_obs_and_null_undefined_correlation() -> None:
    metrics = evaluate_forecast(pd.Series([1.0, 1.0, 1.0]), pd.Series([2.0, 2.0, 2.0]))

    assert metrics["n_obs"] == 3
    assert metrics["correlation"] is None
    assert "change_direction_accuracy" in metrics
    assert "directional_accuracy" not in metrics


def test_regime_metrics_use_origin_regime() -> None:
    result = backtest_rv_forecast(_prices(), horizon_sessions=5)
    model_metrics = result["models"]["ewma"]["regime_metrics"]
    report = result["report"]
    rows = metric_rows(
        report,
        forecast_column="ewma_forecast_annualized_variance",
        target_column="forward_annualized_variance",
        metric_stride=5,
    )

    for item in model_metrics:
        expected_count = int((rows["regime"] == item["regime"]).sum())
        assert item["variance_metrics"]["n_obs"] == expected_count


def test_walk_forward_split_is_future_utility() -> None:
    df = pd.DataFrame({"x": range(10)})

    splits = list(walk_forward_split(df, train_size=4, test_size=2, step=2))

    assert len(splits) == 3
    for train, test in splits:
        assert train.index.max() < test.index.min()
