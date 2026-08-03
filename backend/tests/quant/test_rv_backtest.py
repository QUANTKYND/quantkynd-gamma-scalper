import math

import pandas as pd

from app.quant.rv_backtest import (
    backtest_rv_forecast,
    evaluate_forecast,
    make_forward_target,
    walk_forward_split,
)


def _prices(n: int = 160) -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=n)
    returns = pd.Series(
        [0.0005 + ((i % 17) - 8) * 0.0008 for i in range(n)],
        index=index,
    )
    return 100 * (1 + returns).cumprod()


def test_forward_target_aligns_with_future_window():
    rv = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    target = make_forward_target(rv, horizon=2)

    assert target.tolist()[:3] == [2.5, 3.5, 4.5]
    assert math.isnan(target.iloc[-2])
    assert math.isnan(target.iloc[-1])


def test_forecast_metrics_compute_without_error():
    metrics = evaluate_forecast(
        pd.Series([1.0, 2.0, 3.0, 4.0]),
        pd.Series([1.1, 1.9, 3.2, 3.8]),
    )

    assert metrics["n_obs"] == 4
    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0
    assert -1 <= metrics["correlation"] <= 1
    assert 0 <= metrics["directional_accuracy"] <= 1


def test_walk_forward_splits_do_not_overlap_train_and_test():
    df = pd.DataFrame({"x": range(10)})

    splits = list(walk_forward_split(df, train_size=4, test_size=2, step=2))

    assert len(splits) == 3
    for train, test in splits:
        assert len(train) == 4
        assert len(test) == 2
        assert train.index.max() < test.index.min()
        assert set(train.index).isdisjoint(set(test.index))


def test_backtest_returns_metrics_and_report():
    result = backtest_rv_forecast(_prices(), horizon=5)

    assert result["horizon"] == 5
    assert {"naive", "ewma"} == set(result["metrics"])
    assert result["metrics"]["naive"]["n_obs"] > 0
    assert not result["report"].empty
    assert result["report"].index.equals(_prices().index)
