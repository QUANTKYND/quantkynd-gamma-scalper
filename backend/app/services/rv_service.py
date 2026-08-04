"""Data loading and response formatting for close-to-close volatility endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.core.config import settings
from app.quant.rv_backtest import (
    EVALUATION_METHOD,
    backtest_rv_forecast,
)
from app.quant.rv_engine import TRADING_DAYS_PER_YEAR
from app.quant.rv_features import DEFAULT_HORIZONS, FEATURE_COLUMNS, build_rv_feature_frame
from app.schemas.rv import (
    RVBacktestMetrics,
    RVBacktestSummary,
    RVDatasetMetadata,
    RVEstimatorMetadata,
    RVFeaturePoint,
    RVFeatureResponse,
    RVForecastHistoryPoint,
    RVHealthResponse,
    RVHistoryResponse,
    RVHorizonEstimate,
    RVLatestResponse,
    RVRegimeMetric,
    RVSyntheticDatasetParameters,
    RVRunsResponse,
)
from app.services.rv_run_store import RVRunStore


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_CSV_PATH = BACKEND_ROOT / "data" / "NIFTY.csv"
DEFAULT_ARTIFACT_ROOT = BACKEND_ROOT / "artifacts" / "rv"
ESTIMATOR_ID = "close_to_close_squared_log_returns_v1"


@dataclass(frozen=True)
class LoadedPriceDataset:
    prices: pd.Series
    source: Literal["csv", "synthetic", "upstox_historical"]
    synthetic_parameters: RVSyntheticDatasetParameters | None


@dataclass(frozen=True)
class RVResearchSnapshot:
    symbol: str
    prices: pd.Series
    features: pd.DataFrame
    backtest: dict[str, Any]
    estimator_metadata: RVEstimatorMetadata
    dataset_metadata: RVDatasetMetadata


def _optional_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _required_float(value: object, field: str) -> float:
    number = _optional_float(value)
    if number is None:
        raise ValueError(f"{field} is not finite")
    return number


def _as_date(value: object) -> date:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("date value is missing")
    return timestamp.date()


def synthetic_prices(
    *,
    periods: int,
    seed: int,
    end_date: date,
    initial_price: float,
) -> pd.Series:
    """Build deterministic business-day synthetic prices with fixed dates."""

    if periods < 1:
        raise ValueError("periods must be positive")
    if initial_price <= 0:
        raise ValueError("initial_price must be positive")

    rng = np.random.default_rng(seed)
    segment_lengths = (periods // 3, periods // 3, periods - 2 * (periods // 3))
    returns = np.concatenate(
        [
            rng.normal(0.0003, 0.007, segment_lengths[0]),
            rng.normal(-0.0001, 0.017, segment_lengths[1]),
            rng.normal(0.0004, 0.010, segment_lengths[2]),
        ]
    )
    dates = pd.bdate_range(end=pd.Timestamp(end_date), periods=periods)
    values = initial_price * np.exp(np.cumsum(returns))
    return pd.Series(values, index=dates, name="price")


def read_prices(csv_path: Path) -> pd.Series | None:
    """Read a CSV with date/timestamp and close/price columns if available."""

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


def load_price_dataset(
    *,
    csv_path: Path,
    force_synthetic: bool,
    synthetic_seed: int,
    synthetic_periods: int,
    synthetic_end_date: date,
    synthetic_initial_price: float,
) -> LoadedPriceDataset:
    """Load configured CSV prices or fall back to explicit synthetic prices."""

    csv_prices = None if force_synthetic else read_prices(csv_path)
    if csv_prices is not None:
        return LoadedPriceDataset(
            prices=csv_prices,
            source="csv",
            synthetic_parameters=None,
        )

    parameters = RVSyntheticDatasetParameters(
        seed=synthetic_seed,
        periods=synthetic_periods,
        end_date=synthetic_end_date,
        initial_price=synthetic_initial_price,
    )
    return LoadedPriceDataset(
        prices=synthetic_prices(
            periods=parameters.periods,
            seed=parameters.seed,
            end_date=parameters.end_date,
            initial_price=parameters.initial_price,
        ),
        source="synthetic",
        synthetic_parameters=parameters,
    )


def dataset_id_for_prices(
    *,
    symbol: str,
    prices: pd.Series,
    source: Literal["csv", "synthetic", "upstox_historical"],
    synthetic_parameters: RVSyntheticDatasetParameters | None,
) -> str:
    """Calculate a stable SHA-256 dataset identifier from normalized prices."""

    observations = [
        {
            "timestamp": pd.Timestamp(index).isoformat(),
            "price": format(float(price), ".12g"),
        }
        for index, price in prices.sort_index().items()
    ]
    payload: dict[str, Any] = {
        "symbol": symbol,
        "frequency": "1d_close",
        "source": source,
        "observations": observations,
    }
    if synthetic_parameters is not None:
        payload["synthetic_parameters"] = synthetic_parameters.model_dump(mode="json")

    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def estimator_metadata() -> RVEstimatorMetadata:
    return RVEstimatorMetadata(
        estimator_id=ESTIMATOR_ID,
        input_frequency="1d_close",
        return_type="log",
        annualization_periods=TRADING_DAYS_PER_YEAR,
        observation_timing="end_of_day",
        is_intraday_realized_variance=False,
    )


def build_research_snapshot(
    *,
    symbol: str,
    csv_path: Path = DEFAULT_CSV_PATH,
    force_synthetic: bool = False,
    synthetic_seed: int = settings.rv_synthetic_seed,
    synthetic_periods: int = settings.rv_synthetic_periods,
    synthetic_end_date: date = settings.rv_synthetic_end_date,
    synthetic_initial_price: float = settings.rv_synthetic_initial_price,
    horizon_sessions: int = 5,
) -> RVResearchSnapshot:
    """Build one internally consistent close-to-close research snapshot."""

    loaded = load_price_dataset(
        csv_path=csv_path,
        force_synthetic=force_synthetic,
        synthetic_seed=synthetic_seed,
        synthetic_periods=synthetic_periods,
        synthetic_end_date=synthetic_end_date,
        synthetic_initial_price=synthetic_initial_price,
    )
    features = build_rv_feature_frame(loaded.prices)
    backtest = backtest_rv_forecast(loaded.prices, horizon_sessions=horizon_sessions)
    computed_at = datetime.now(UTC)
    dataset_id = dataset_id_for_prices(
        symbol=symbol,
        prices=loaded.prices,
        source=loaded.source,
        synthetic_parameters=loaded.synthetic_parameters,
    )
    dataset = RVDatasetMetadata(
        dataset_id=dataset_id,
        source=loaded.source,
        symbol=symbol,
        observations=len(loaded.prices),
        start_date=_as_date(loaded.prices.index[0]),
        end_date=_as_date(loaded.prices.index[-1]),
        computed_at=computed_at,
        synthetic_parameters=loaded.synthetic_parameters,
    )
    return RVResearchSnapshot(
        symbol=symbol,
        prices=loaded.prices,
        features=features,
        backtest=backtest,
        estimator_metadata=estimator_metadata(),
        dataset_metadata=dataset,
    )


def build_research_snapshot_from_prices(
    *,
    symbol: str,
    prices: pd.Series,
    source: Literal["upstox_historical"],
    dataset_key: str | None = None,
    horizon_sessions: int = 5,
) -> RVResearchSnapshot:
    normalized_prices = prices.copy().sort_index()
    features = build_rv_feature_frame(normalized_prices)
    backtest = backtest_rv_forecast(normalized_prices, horizon_sessions=horizon_sessions)
    computed_at = datetime.now(UTC)
    dataset = RVDatasetMetadata(
        dataset_id=dataset_id_for_prices(
            symbol=dataset_key or symbol,
            prices=normalized_prices,
            source=source,
            synthetic_parameters=None,
        ),
        source=source,
        symbol=symbol,
        observations=len(normalized_prices),
        start_date=_as_date(normalized_prices.index[0]),
        end_date=_as_date(normalized_prices.index[-1]),
        computed_at=computed_at,
        synthetic_parameters=None,
    )
    return RVResearchSnapshot(
        symbol=symbol,
        prices=normalized_prices,
        features=features,
        backtest=backtest,
        estimator_metadata=estimator_metadata(),
        dataset_metadata=dataset,
    )


class RVService:
    """Serve one immutable RV research snapshot plus persisted run manifests."""

    def __init__(
        self,
        symbol: str = "NIFTY",
        csv_path: Path = DEFAULT_CSV_PATH,
        artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
        snapshot: RVResearchSnapshot | None = None,
    ):
        self.symbol = symbol
        self.csv_path = csv_path
        self.run_store = RVRunStore(artifact_root)
        self._snapshot = snapshot or build_research_snapshot(symbol=symbol, csv_path=csv_path)

    @property
    def snapshot(self) -> RVResearchSnapshot:
        return self._snapshot

    @property
    def prices(self) -> pd.Series:
        return self.snapshot.prices

    @property
    def features(self) -> pd.DataFrame:
        return self.snapshot.features

    def refresh(self) -> None:
        """Reload source data and atomically replace the current snapshot."""

        self._snapshot = build_research_snapshot(symbol=self.symbol, csv_path=self.csv_path)

    def latest(self) -> RVLatestResponse:
        snapshot = self.snapshot
        frame = snapshot.features.assign(price=snapshot.prices)
        complete = frame.dropna(subset=_estimate_columns())
        if complete.empty:
            raise ValueError("Price history is too short to compute an RV snapshot")

        as_of = complete.index[-1]
        row = complete.iloc[-1]
        return RVLatestResponse(
            symbol=snapshot.symbol,
            as_of=_as_date(as_of),
            price=_required_float(row["price"], "price"),
            estimates=_estimates_from_row(row),
            variance_ratio_5_21=_optional_float(row["variance_ratio_5_21"]),
            volatility_zscore_21=_optional_float(row["volatility_zscore_21"]),
            regime=str(row["regime"]),
            estimator=snapshot.estimator_metadata,
            dataset=snapshot.dataset_metadata,
        )

    def feature_series(self, limit: int = 260) -> RVFeatureResponse:
        snapshot = self.snapshot
        frame = snapshot.features.assign(price=snapshot.prices)
        complete = frame.dropna(subset=["price", *_estimate_columns()])
        points = [
            RVFeaturePoint(
                date=_as_date(index),
                price=_required_float(row["price"], "price"),
                estimates=_estimates_from_row(row),
                variance_ratio_5_21=_optional_float(row["variance_ratio_5_21"]),
                volatility_zscore_21=_optional_float(row["volatility_zscore_21"]),
                regime=str(row["regime"]),
            )
            for index, row in complete.tail(limit).iterrows()
        ]
        return RVFeatureResponse(
            symbol=snapshot.symbol,
            estimator=snapshot.estimator_metadata,
            dataset=snapshot.dataset_metadata,
            points=points,
        )

    def backtest_summary(self, model: str = "ewma") -> RVBacktestSummary:
        snapshot = self.snapshot
        if model not in snapshot.backtest["models"]:
            raise ValueError(f"unknown RV model: {model}")

        model_result = snapshot.backtest["models"][model]
        rows = model_result["metric_rows"]
        if rows.empty:
            raise ValueError("Price history is too short to evaluate the RV forecast")

        return RVBacktestSummary(
            symbol=snapshot.symbol,
            model=model,
            model_parameters=model_result["model_parameters"],
            horizon_sessions=int(snapshot.backtest["horizon_sessions"]),
            evaluation_method=EVALUATION_METHOD,
            chart_stride=int(snapshot.backtest["chart_stride"]),
            metric_stride=int(snapshot.backtest["metric_stride"]),
            overlapping_chart_targets=bool(snapshot.backtest["overlapping_chart_targets"]),
            overlapping_metric_targets=bool(snapshot.backtest["overlapping_metric_targets"]),
            evaluation_start=_as_date(rows.index[0]),
            evaluation_end=_as_date(rows.index[-1]),
            estimator=snapshot.estimator_metadata,
            dataset=snapshot.dataset_metadata,
            variance_metrics=RVBacktestMetrics(**model_result["variance_metrics"]),
            volatility_metrics=RVBacktestMetrics(**model_result["volatility_metrics"]),
            regime_metrics=[
                RVRegimeMetric(
                    regime=item["regime"],
                    variance_metrics=RVBacktestMetrics(**item["variance_metrics"]),
                    volatility_metrics=RVBacktestMetrics(**item["volatility_metrics"]),
                )
                for item in model_result["regime_metrics"]
            ],
        )

    def runs(self) -> RVRunsResponse:
        return RVRunsResponse(runs=self.run_store.list_summaries())

    def history(self, limit: int = 260, model: str = "ewma") -> RVHistoryResponse:
        snapshot = self.snapshot
        if model not in snapshot.backtest["models"]:
            raise ValueError(f"unknown RV model: {model}")

        report = snapshot.backtest["report"].dropna(
            subset=[
                "price",
                "target_start",
                "target_end",
                f"{model}_forecast_annualized_variance",
                f"{model}_forecast_annualized_volatility",
                "forward_annualized_variance",
                "forward_annualized_volatility",
            ]
        )
        points = [
            RVForecastHistoryPoint(
                origin_date=_as_date(index),
                target_start=_as_date(row["target_start"]),
                target_end=_as_date(row["target_end"]),
                price=_required_float(row["price"], "price"),
                forecast_annualized_variance=_required_float(
                    row[f"{model}_forecast_annualized_variance"],
                    "forecast_annualized_variance",
                ),
                forecast_annualized_volatility=_required_float(
                    row[f"{model}_forecast_annualized_volatility"],
                    "forecast_annualized_volatility",
                ),
                actual_annualized_variance=_required_float(
                    row["forward_annualized_variance"],
                    "actual_annualized_variance",
                ),
                actual_annualized_volatility=_required_float(
                    row["forward_annualized_volatility"],
                    "actual_annualized_volatility",
                ),
            )
            for index, row in report.tail(limit).iterrows()
        ]
        return RVHistoryResponse(
            symbol=snapshot.symbol,
            model=model,
            horizon_sessions=int(snapshot.backtest["horizon_sessions"]),
            estimator=snapshot.estimator_metadata,
            dataset=snapshot.dataset_metadata,
            points=points,
        )

    def health(self) -> RVHealthResponse:
        snapshot = self.snapshot
        return RVHealthResponse(
            status="ok",
            service="close-to-close-volatility",
            source=snapshot.dataset_metadata.source,
            observations=snapshot.dataset_metadata.observations,
            estimator=snapshot.estimator_metadata,
            dataset=snapshot.dataset_metadata,
        )


def _estimate_columns() -> list[str]:
    columns: list[str] = []
    for horizon in DEFAULT_HORIZONS:
        columns.extend(
            [
                f"horizon_variance_{horizon}d",
                f"annualized_variance_{horizon}d",
                f"annualized_volatility_{horizon}d",
            ]
        )
    return columns


def _estimates_from_row(row: pd.Series) -> list[RVHorizonEstimate]:
    return [
        RVHorizonEstimate(
            horizon_sessions=horizon,
            horizon_variance=_required_float(row[f"horizon_variance_{horizon}d"], "horizon_variance"),
            annualized_variance=_required_float(
                row[f"annualized_variance_{horizon}d"],
                "annualized_variance",
            ),
            annualized_volatility=_required_float(
                row[f"annualized_volatility_{horizon}d"],
                "annualized_volatility",
            ),
        )
        for horizon in DEFAULT_HORIZONS
    ]


def feature_artifact_frame(snapshot: RVResearchSnapshot) -> pd.DataFrame:
    """Return feature rows with price for CSV artifact writing."""

    return snapshot.features.reindex(columns=FEATURE_COLUMNS).assign(price=snapshot.prices)


def history_artifact_frame(snapshot: RVResearchSnapshot, model: str) -> pd.DataFrame:
    """Return forecast-history rows for CSV artifact writing."""

    report = snapshot.backtest["report"].copy()
    return pd.DataFrame(
        {
            "origin_date": report.index,
            "target_start": report["target_start"],
            "target_end": report["target_end"],
            "price": report["price"],
            "forecast_annualized_variance": report[f"{model}_forecast_annualized_variance"],
            "forecast_annualized_volatility": report[f"{model}_forecast_annualized_volatility"],
            "actual_annualized_variance": report["forward_annualized_variance"],
            "actual_annualized_volatility": report["forward_annualized_volatility"],
        },
        index=report.index,
    ).dropna()


rv_service = RVService()
