import pytest
from pydantic import ValidationError

from app.api.rv import (
    backtest_runs,
    latest_backtest,
    latest_rv,
    rv_features,
    rv_health,
    rv_history,
)
from app.main import app
from app.schemas.rv import RVLatestResponse
from app.services.rv_service import RVService, build_research_snapshot


OLD_KEYS = {
    "rv_1d",
    "rv_5d",
    "rv_21d",
    "rv_63d",
    "rv_ratio_5_21",
    "rv_zscore_21",
    "forecast_5d",
    "actual_forward_5d",
    "horizon_days",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "directional_accuracy",
}


def _route_paths() -> set[str]:
    paths: set[str] = set()

    def visit(route) -> None:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            for candidate in candidates():
                visit(candidate)

    for route in app.routes:
        visit(route)
    return paths


def _keys_recursive(value) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_keys_recursive(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_keys_recursive(item))
        return keys
    return set()


def test_rv_routes_are_registered() -> None:
    paths = _route_paths()
    assert {
        "/api/v1/rv/latest",
        "/api/v1/rv/features",
        "/api/v1/rv/backtest/latest",
        "/api/v1/rv/backtest/runs",
        "/api/v1/rv/history",
        "/api/v1/rv/health",
    }.issubset(paths)


def test_rv_contracts_are_populated_and_serializable() -> None:
    latest = latest_rv()
    features = rv_features(limit=40)
    backtest = latest_backtest()
    runs = backtest_runs()
    history = rv_history(limit=40)
    health = rv_health()

    assert latest.symbol == "NIFTY"
    assert latest.price > 0
    assert latest.regime in {"low", "normal", "high", "unknown"}
    assert [estimate.horizon_sessions for estimate in latest.estimates] == [1, 5, 21, 63]
    assert len(features.points) == 40
    assert len(history.points) == 40
    assert backtest.model == "ewma"
    assert backtest.evaluation_method == "sequential_non_overlapping_metrics"
    assert backtest.metric_stride == backtest.horizon_sessions
    assert backtest.variance_metrics.n_obs > 0
    assert backtest.volatility_metrics.n_obs > 0
    assert health.observations >= 100

    dataset_ids = {
        latest.dataset.dataset_id,
        features.dataset.dataset_id,
        backtest.dataset.dataset_id,
        history.dataset.dataset_id,
        health.dataset.dataset_id,
    }
    assert len(dataset_ids) == 1
    assert latest.estimator.estimator_id == "close_to_close_squared_log_returns_v1"
    assert latest.estimator.is_intraday_realized_variance is False

    for response in (latest, features, backtest, runs, history, health):
        payload = response.model_dump(mode="json")
        assert response.model_dump_json()
        assert OLD_KEYS.isdisjoint(_keys_recursive(payload))


def test_backtest_response_has_no_train_test_fields() -> None:
    payload = latest_backtest().model_dump(mode="json")

    assert "train_start" not in payload
    assert "test_start" not in payload
    assert "variance_metrics" in payload
    assert "volatility_metrics" in payload


def test_empty_run_store_returns_empty_list(tmp_path) -> None:
    service = RVService(artifact_root=tmp_path / "rv")

    assert service.runs().runs == []


def test_latest_response_rejects_undeclared_fields() -> None:
    payload = latest_rv().model_dump(mode="json")
    payload["rv_5d"] = 0.1

    with pytest.raises(ValidationError):
        RVLatestResponse.model_validate(payload)


def test_synthetic_dataset_id_is_stable() -> None:
    first = build_research_snapshot(
        symbol="NIFTY",
        force_synthetic=True,
        synthetic_seed=17,
        synthetic_periods=180,
    )
    second = build_research_snapshot(
        symbol="NIFTY",
        force_synthetic=True,
        synthetic_seed=17,
        synthetic_periods=180,
    )
    changed = build_research_snapshot(
        symbol="NIFTY",
        force_synthetic=True,
        synthetic_seed=18,
        synthetic_periods=180,
    )

    assert first.dataset_metadata.dataset_id == second.dataset_metadata.dataset_id
    assert first.prices.equals(second.prices)
    assert first.dataset_metadata.dataset_id != changed.dataset_metadata.dataset_id
