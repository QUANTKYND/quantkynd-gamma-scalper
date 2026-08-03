"""Data loading and response formatting for realized-volatility endpoints."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.quant.rv_backtest import backtest_rv_forecast, evaluate_forecast
from app.quant.rv_features import build_rv_feature_frame
from app.schemas.rv import (
    RVBacktestMetrics,
    RVBacktestSummary,
    RVFeaturePoint,
    RVFeatureResponse,
    RVHealthResponse,
    RVHistoryResponse,
    RVLatestResponse,
    RVPoint,
    RVRegimeMetric,
    RVRunSummary,
    RVRunsResponse,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_PATH = BACKEND_ROOT / "data" / "NIFTY.csv"


def _finite(value: object, fallback: float = 0.0) -> float:
    number = float(value)
    return number if np.isfinite(number) else fallback


def _synthetic_prices(periods: int = 720, seed: int = 17) -> pd.Series:
    """Build deterministic business-day prices with several volatility regimes."""

    rng = np.random.default_rng(seed)
    segment_lengths = (periods // 3, periods // 3, periods - 2 * (periods // 3))
    returns = np.concatenate(
        [
            rng.normal(0.0003, 0.007, segment_lengths[0]),
            rng.normal(-0.0001, 0.017, segment_lengths[1]),
            rng.normal(0.0004, 0.010, segment_lengths[2]),
        ]
    )
    dates = pd.bdate_range(end=pd.Timestamp.now(tz="UTC").normalize().tz_localize(None), periods=periods)
    values = 24_000 * np.exp(np.cumsum(returns))
    return pd.Series(values, index=dates, name="price")


def _read_prices(csv_path: Path) -> pd.Series | None:
    if not csv_path.is_file():
        return None

    frame = pd.read_csv(csv_path)
    normalized = {column.lower().strip(): column for column in frame.columns}
    date_column = normalized.get("date") or normalized.get("timestamp")
    price_column = normalized.get("close") or normalized.get("price")
    if date_column is None or price_column is None:
        return None

    dates = pd.to_datetime(frame[date_column], errors="coerce", utc=True).dt.tz_localize(None)
    prices = pd.to_numeric(frame[price_column], errors="coerce")
    series = pd.Series(prices.to_numpy(), index=dates, name="price")
    series = series.loc[series.index.notna() & series.notna() & (series > 0)]
    series = series.groupby(level=0).last().sort_index()
    return series if len(series) >= 100 else None


class RVService:
    """Compute and cache one internally consistent RV research snapshot."""

    def __init__(self, symbol: str = "NIFTY", csv_path: Path = DEFAULT_CSV_PATH):
        csv_prices = _read_prices(csv_path)
        self.symbol = symbol
        self.source = "csv" if csv_prices is not None else "synthetic"
        self.prices = csv_prices if csv_prices is not None else _synthetic_prices()
        self.features = build_rv_feature_frame(self.prices)
        self.backtest = backtest_rv_forecast(self.prices, horizon=5)

    def latest(self) -> RVLatestResponse:
        complete = self.features.dropna(
            subset=["rv_1d", "rv_5d", "rv_21d", "rv_63d", "rv_ratio_5_21", "rv_z_21", "rv_regime"]
        )
        if complete.empty:
            raise ValueError("Price history is too short to compute an RV snapshot")

        as_of = complete.index[-1]
        row = complete.iloc[-1]
        return RVLatestResponse(
            symbol=self.symbol,
            as_of=as_of.date(),
            price=_finite(self.prices.loc[as_of]),
            rv_1d=_finite(row["rv_1d"]),
            rv_5d=_finite(row["rv_5d"]),
            rv_21d=_finite(row["rv_21d"]),
            rv_63d=_finite(row["rv_63d"]),
            rv_ratio_5_21=_finite(row["rv_ratio_5_21"]),
            rv_zscore_21=_finite(row["rv_z_21"]),
            regime=str(row["rv_regime"]),
            source=self.source,
        )

    def feature_series(self, limit: int = 260) -> RVFeatureResponse:
        frame = self.features.assign(price=self.prices).dropna()
        points = [
            RVFeaturePoint(
                date=index.date(),
                price=_finite(row["price"]),
                rv_1d=_finite(row["rv_1d"]),
                rv_5d=_finite(row["rv_5d"]),
                rv_21d=_finite(row["rv_21d"]),
                rv_63d=_finite(row["rv_63d"]),
                rv_ratio_5_21=_finite(row["rv_ratio_5_21"]),
                rv_zscore_21=_finite(row["rv_z_21"]),
                regime=str(row["rv_regime"]),
            )
            for index, row in frame.tail(limit).iterrows()
        ]
        return RVFeatureResponse(symbol=self.symbol, points=points)

    def _evaluation_window(self, model: str = "ewma") -> tuple[pd.DataFrame, pd.DataFrame]:
        report = self.backtest["report"].dropna(subset=["target", model]).copy()
        split = max(1, min(len(report) - 1, int(len(report) * 0.7)))
        return report.iloc[:split], report.iloc[split:]

    def backtest_summary(self, model: str = "ewma") -> RVBacktestSummary:
        train, test = self._evaluation_window(model)
        metrics = evaluate_forecast(test["target"], test[model])
        regime_metrics: list[RVRegimeMetric] = []
        for regime, rows in test.dropna(subset=["rv_regime"]).groupby("rv_regime"):
            if len(rows) < 3:
                continue
            values = evaluate_forecast(rows["target"], rows[model])
            regime_metrics.append(
                RVRegimeMetric(
                    regime=str(regime),
                    mae=_finite(values["mae"]),
                    rmse=_finite(values["rmse"]),
                    count=int(values["n_obs"]),
                )
            )

        return RVBacktestSummary(
            symbol=self.symbol,
            horizon_days=int(self.backtest["horizon"]),
            model=model,
            train_start=train.index[0].date(),
            train_end=train.index[-1].date(),
            test_start=test.index[0].date(),
            test_end=test.index[-1].date(),
            metrics=RVBacktestMetrics(
                mae=_finite(metrics["mae"]),
                rmse=_finite(metrics["rmse"]),
                correlation=_finite(metrics["correlation"]),
                directional_accuracy=_finite(metrics["directional_accuracy"]),
            ),
            regime_metrics=regime_metrics,
        )

    def runs(self) -> RVRunsResponse:
        as_of = self.prices.index[-1]
        created_at = datetime.combine(as_of.date(), time(5, 30), tzinfo=timezone.utc)
        date_token = as_of.strftime("%Y-%m-%d")
        return RVRunsResponse(
            runs=[
                RVRunSummary(
                    run_id=f"rv-{date_token}-{index:03d}",
                    created_at=created_at,
                    symbol=self.symbol,
                    model=model,
                    horizon_days=5,
                    status="complete",
                )
                for index, model in enumerate(("ewma", "naive"), start=1)
            ]
        )

    def history(self, limit: int = 260) -> RVHistoryResponse:
        report = self.backtest["report"].assign(
            price=self.prices,
            rv_5d=self.features["rv_5d"],
        ).dropna(subset=["rv_5d", "ewma", "target", "price"])
        points = [
            RVPoint(
                date=index.date(),
                price=_finite(row["price"]),
                rv_5d=_finite(row["rv_5d"]),
                forecast_5d=_finite(row["ewma"]),
                actual_forward_5d=_finite(row["target"]),
            )
            for index, row in report.tail(limit).iterrows()
        ]
        return RVHistoryResponse(symbol=self.symbol, points=points)

    def health(self) -> RVHealthResponse:
        return RVHealthResponse(
            status="ok",
            service="realized-volatility",
            source=self.source,
            observations=len(self.prices),
        )


rv_service = RVService()
