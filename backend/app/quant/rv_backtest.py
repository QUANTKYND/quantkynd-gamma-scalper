"""Sequential close-to-close variance forecast evaluation."""

from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any

import numpy as np
import pandas as pd

from app.quant.rv_engine import TRADING_DAYS_PER_YEAR, squared_log_returns
from app.quant.rv_features import build_rv_feature_frame


EVALUATION_METHOD = "sequential_non_overlapping_metrics"


def _validate_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _validate_prices(prices: pd.Series) -> None:
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")


def _annualized_from_daily_variance(
    daily_variance: pd.Series,
    periods_per_year: int,
) -> pd.DataFrame:
    annualized = daily_variance * periods_per_year
    volatility = np.sqrt(annualized.clip(lower=0))
    return pd.DataFrame(
        {
            "forecast_daily_variance": daily_variance.replace([np.inf, -np.inf], np.nan),
            "forecast_annualized_variance": annualized.replace([np.inf, -np.inf], np.nan),
            "forecast_annualized_volatility": volatility.replace([np.inf, -np.inf], np.nan),
        },
        index=daily_variance.index,
    )


def make_forward_variance_target(
    prices: pd.Series,
    horizon_sessions: int = 5,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """
    Build subsequent realized-variance targets from returns t+1 through t+h.

    A row indexed by origin date t is known after the session t close. Its
    target starts at t+1 and ends at t+h.
    """

    _validate_prices(prices)
    _validate_positive_int(horizon_sessions, "horizon_sessions")
    _validate_positive_int(periods_per_year, "periods_per_year")

    daily_variance = squared_log_returns(prices)
    future_variance = pd.concat(
        [daily_variance.shift(-offset) for offset in range(1, horizon_sessions + 1)],
        axis=1,
    )
    horizon_variance = future_variance.sum(axis=1, min_count=horizon_sessions)
    annualized = horizon_variance * periods_per_year / horizon_sessions
    volatility = np.sqrt(annualized.clip(lower=0))
    target_dates = pd.Series(prices.index, index=prices.index, dtype="object")

    target = pd.DataFrame(
        {
            "forward_horizon_variance": horizon_variance,
            "forward_annualized_variance": annualized,
            "forward_annualized_volatility": volatility,
            "target_start": target_dates.shift(-1),
            "target_end": target_dates.shift(-horizon_sessions),
        },
        index=prices.index,
    )
    return target.replace([np.inf, -np.inf], np.nan)


def make_naive_variance_forecast(
    prices: pd.Series,
    horizon_sessions: int = 5,
    lookback_sessions: int | None = None,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Forecast annualized variance from trailing average daily variance."""

    _validate_prices(prices)
    _validate_positive_int(horizon_sessions, "horizon_sessions")
    _validate_positive_int(periods_per_year, "periods_per_year")
    lookback = horizon_sessions if lookback_sessions is None else lookback_sessions
    _validate_positive_int(lookback, "lookback_sessions")

    daily_variance = squared_log_returns(prices)
    forecast_daily_variance = daily_variance.rolling(
        window=lookback,
        min_periods=lookback,
    ).mean()
    return _annualized_from_daily_variance(forecast_daily_variance, periods_per_year)


def make_ewma_variance_forecast(
    prices: pd.Series,
    horizon_sessions: int = 5,
    ewma_span: int | None = None,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Forecast annualized variance from an EWMA of daily variance."""

    _validate_prices(prices)
    _validate_positive_int(horizon_sessions, "horizon_sessions")
    _validate_positive_int(periods_per_year, "periods_per_year")
    span = max(horizon_sessions, 2) if ewma_span is None else ewma_span
    _validate_positive_int(span, "ewma_span")

    daily_variance = squared_log_returns(prices)
    forecast_daily_variance = daily_variance.ewm(
        span=span,
        adjust=False,
        min_periods=span,
    ).mean()
    return _annualized_from_daily_variance(forecast_daily_variance, periods_per_year)


def walk_forward_split(
    df: pd.DataFrame,
    train_size: int,
    test_size: int,
    step: int,
) -> Generator[tuple[pd.DataFrame, pd.DataFrame], None, None]:
    """Future utility yielding fixed-size rolling train/test DataFrame slices."""

    _validate_positive_int(train_size, "train_size")
    _validate_positive_int(test_size, "test_size")
    _validate_positive_int(step, "step")

    split_end = train_size + test_size
    for start in range(0, len(df) - split_end + 1, step):
        train_end = start + train_size
        test_end = train_end + test_size
        yield df.iloc[start:train_end], df.iloc[train_end:test_end]


def metric_rows(
    report: pd.DataFrame,
    forecast_column: str,
    target_column: str,
    metric_stride: int,
) -> pd.DataFrame:
    """Select non-overlapping metric rows from eligible chart observations."""

    _validate_positive_int(metric_stride, "metric_stride")
    eligible = report.dropna(subset=[forecast_column, target_column]).copy()
    return eligible.iloc[::metric_stride]


def evaluate_forecast(y_true: Any, y_pred: Any) -> dict[str, float | int | None]:
    """Evaluate point forecasts against subsequent realized values."""

    aligned = pd.concat(
        [
            pd.Series(y_true, name="actual", dtype="float64"),
            pd.Series(y_pred, name="forecast", dtype="float64"),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()

    if aligned.empty:
        return {
            "mae": None,
            "rmse": None,
            "correlation": None,
            "change_direction_accuracy": None,
            "n_obs": 0,
        }

    errors = aligned["forecast"] - aligned["actual"]
    mae = float(errors.abs().mean())
    rmse = math.sqrt(float((errors**2).mean()))

    if (
        len(aligned) > 1
        and aligned["actual"].std(ddof=0) > 0
        and aligned["forecast"].std(ddof=0) > 0
    ):
        correlation = float(aligned["actual"].corr(aligned["forecast"]))
    else:
        correlation = None

    changes = aligned.diff().dropna()
    if changes.empty:
        change_direction_accuracy = None
    else:
        change_direction_accuracy = float(
            (np.sign(changes["actual"]) == np.sign(changes["forecast"])).mean()
        )

    return {
        "mae": mae,
        "rmse": rmse,
        "correlation": correlation if correlation is not None and np.isfinite(correlation) else None,
        "change_direction_accuracy": change_direction_accuracy,
        "n_obs": int(len(aligned)),
    }


def _model_metric_bundle(
    report: pd.DataFrame,
    model: str,
    stride: int,
) -> dict[str, Any]:
    forecast_variance = f"{model}_forecast_annualized_variance"
    forecast_volatility = f"{model}_forecast_annualized_volatility"
    rows = metric_rows(
        report,
        forecast_column=forecast_variance,
        target_column="forward_annualized_variance",
        metric_stride=stride,
    )
    return {
        "metric_rows": rows,
        "variance_metrics": evaluate_forecast(
            rows["forward_annualized_variance"],
            rows[forecast_variance],
        ),
        "volatility_metrics": evaluate_forecast(
            rows["forward_annualized_volatility"],
            rows[forecast_volatility],
        ),
    }


def _regime_metrics(report: pd.DataFrame, model: str, stride: int) -> list[dict[str, Any]]:
    forecast_variance = f"{model}_forecast_annualized_variance"
    rows = metric_rows(
        report,
        forecast_column=forecast_variance,
        target_column="forward_annualized_variance",
        metric_stride=stride,
    ).dropna(subset=["regime"])

    metrics: list[dict[str, Any]] = []
    for regime, group in rows.groupby("regime", sort=True):
        metrics.append(
            {
                "regime": str(regime),
                "variance_metrics": evaluate_forecast(
                    group["forward_annualized_variance"],
                    group[forecast_variance],
                ),
                "volatility_metrics": evaluate_forecast(
                    group["forward_annualized_volatility"],
                    group[f"{model}_forecast_annualized_volatility"],
                ),
            }
        )
    return metrics


def backtest_rv_forecast(
    prices: pd.Series,
    horizon_sessions: int = 5,
    *,
    horizon: int | None = None,
    metric_stride: int | None = None,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> dict[str, Any]:
    """Run deterministic sequential baseline forecasts."""

    if horizon is not None:
        horizon_sessions = horizon
    _validate_prices(prices)
    _validate_positive_int(horizon_sessions, "horizon_sessions")
    _validate_positive_int(periods_per_year, "periods_per_year")
    stride = horizon_sessions if metric_stride is None else metric_stride
    _validate_positive_int(stride, "metric_stride")

    target = make_forward_variance_target(
        prices,
        horizon_sessions=horizon_sessions,
        periods_per_year=periods_per_year,
    )
    naive = make_naive_variance_forecast(
        prices,
        horizon_sessions=horizon_sessions,
        lookback_sessions=horizon_sessions,
        periods_per_year=periods_per_year,
    ).add_prefix("naive_")
    ewma_span = max(horizon_sessions, 2)
    ewma = make_ewma_variance_forecast(
        prices,
        horizon_sessions=horizon_sessions,
        ewma_span=ewma_span,
        periods_per_year=periods_per_year,
    ).add_prefix("ewma_")
    features = build_rv_feature_frame(prices, periods_per_year=periods_per_year)

    report = pd.concat(
        [
            pd.DataFrame({"price": prices}, index=prices.index),
            target,
            naive,
            ewma,
            features[["regime"]],
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)

    model_parameters = {
        "naive": {"lookback_sessions": horizon_sessions},
        "ewma": {"ewma_span": ewma_span},
    }
    models: dict[str, dict[str, Any]] = {}
    for model in ("naive", "ewma"):
        bundle = _model_metric_bundle(report, model=model, stride=stride)
        models[model] = {
            "model": model,
            "model_parameters": model_parameters[model],
            "variance_metrics": bundle["variance_metrics"],
            "volatility_metrics": bundle["volatility_metrics"],
            "regime_metrics": _regime_metrics(report, model=model, stride=stride),
            "metric_rows": bundle["metric_rows"],
        }

    return {
        "horizon_sessions": horizon_sessions,
        "horizon": horizon_sessions,
        "evaluation_method": EVALUATION_METHOD,
        "chart_stride": 1,
        "metric_stride": stride,
        "overlapping_chart_targets": True,
        "overlapping_metric_targets": False,
        "models": models,
        "report": report,
        "features": features,
        "metrics": {model: models[model]["volatility_metrics"] for model in models},
        "regime_metrics": {model: models[model]["regime_metrics"] for model in models},
    }
