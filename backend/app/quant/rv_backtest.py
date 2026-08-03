"""Small walk-forward harness for realized-volatility forecasts."""

from __future__ import annotations

import math
from collections.abc import Generator

import numpy as np
import pandas as pd

from app.quant.rv_engine import realized_volatility
from app.quant.rv_features import build_rv_feature_frame


def _validate_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def make_forward_target(rv: pd.Series, horizon: int = 5) -> pd.Series:
    """Average future RV over the next ``horizon`` observations."""

    _validate_positive_int(horizon, "horizon")
    if not isinstance(rv, pd.Series):
        raise TypeError("rv must be a pandas Series")

    clean_rv = pd.to_numeric(rv, errors="coerce").astype(float)
    future = pd.concat(
        [clean_rv.shift(-offset) for offset in range(1, horizon + 1)],
        axis=1,
    )
    target = future.mean(axis=1, skipna=False)
    target.name = f"rv_target_{horizon}"
    return target


def walk_forward_split(
    df: pd.DataFrame,
    train_size: int,
    test_size: int,
    step: int,
) -> Generator[tuple[pd.DataFrame, pd.DataFrame], None, None]:
    """Yield fixed-size rolling train/test DataFrame slices."""

    _validate_positive_int(train_size, "train_size")
    _validate_positive_int(test_size, "test_size")
    _validate_positive_int(step, "step")

    split_end = train_size + test_size
    for start in range(0, len(df) - split_end + 1, step):
        train_end = start + train_size
        test_end = train_end + test_size
        yield df.iloc[start:train_end], df.iloc[train_end:test_end]


def evaluate_forecast(y_true, y_pred) -> dict:
    """Evaluate point forecasts against realized future RV."""

    aligned = pd.concat(
        [
            pd.Series(y_true, name="actual", dtype="float64"),
            pd.Series(y_pred, name="forecast", dtype="float64"),
        ],
        axis=1,
    ).dropna()

    if aligned.empty:
        return {
            "mae": math.nan,
            "rmse": math.nan,
            "correlation": math.nan,
            "directional_accuracy": math.nan,
            "n_obs": 0,
        }

    errors = aligned["forecast"] - aligned["actual"]
    mae = errors.abs().mean()
    rmse = math.sqrt(float((errors**2).mean()))

    if len(aligned) > 1 and aligned["actual"].std(ddof=0) > 0 and aligned["forecast"].std(ddof=0) > 0:
        correlation = aligned["actual"].corr(aligned["forecast"])
    else:
        correlation = math.nan

    changes = aligned.diff().dropna()
    if changes.empty:
        directional_accuracy = math.nan
    else:
        directional_accuracy = (
            np.sign(changes["actual"]) == np.sign(changes["forecast"])
        ).mean()

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "correlation": float(correlation) if pd.notna(correlation) else math.nan,
        "directional_accuracy": float(directional_accuracy)
        if pd.notna(directional_accuracy)
        else math.nan,
        "n_obs": int(len(aligned)),
    }


def _regime_metrics(report: pd.DataFrame, models: tuple[str, ...]) -> dict:
    regime_metrics: dict[str, dict[str, dict]] = {}
    valid_regimes = report["rv_regime"].dropna().unique()

    for regime in valid_regimes:
        regime_report = report.loc[report["rv_regime"] == regime]
        if len(regime_report) < 3:
            continue
        regime_metrics[str(regime)] = {
            model: evaluate_forecast(regime_report["target"], regime_report[model])
            for model in models
        }

    return regime_metrics


def backtest_rv_forecast(prices: pd.Series, horizon: int = 5) -> dict:
    """Run a simple, time-safe RV forecast backtest."""

    _validate_positive_int(horizon, "horizon")

    daily_rv = realized_volatility(prices, window=1, annualize=True)
    target = make_forward_target(daily_rv, horizon=horizon)
    features = build_rv_feature_frame(prices)

    past_rv = daily_rv.shift(1)
    naive = past_rv.rolling(window=horizon, min_periods=horizon).mean()
    ewma = past_rv.ewm(span=max(horizon, 2), adjust=False, min_periods=horizon).mean()

    report = pd.DataFrame(
        {
            "rv": daily_rv,
            "target": target,
            "naive": naive,
            "ewma": ewma,
            "rv_regime": features["rv_regime"],
        },
        index=prices.index,
    )

    eval_report = report.dropna(subset=["target"])
    models = ("naive", "ewma")
    metrics = {
        model: evaluate_forecast(eval_report["target"], eval_report[model])
        for model in models
    }

    return {
        "horizon": horizon,
        "metrics": metrics,
        "regime_metrics": _regime_metrics(eval_report, models),
        "report": report,
        "features": features,
    }

