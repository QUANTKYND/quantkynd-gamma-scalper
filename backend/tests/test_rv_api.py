from app.api.rv import (
    backtest_runs,
    latest_backtest,
    latest_rv,
    rv_features,
    rv_health,
    rv_history,
)
from app.main import app
from app.services.rv_service import rv_service


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
    assert latest.regime in {"low", "normal", "high"}
    assert len(features.points) == 40
    assert len(history.points) == 40
    assert history.points[-1].rv_5d == rv_service.features.loc[history.points[-1].date.strftime("%Y-%m-%d"), "rv_5d"]
    assert backtest.model == "ewma"
    assert backtest.metrics.rmse >= 0
    assert all(metric.count >= 3 for metric in backtest.regime_metrics)
    assert {run.model for run in runs.runs} == {"ewma", "naive"}
    assert health.observations >= 100

    for response in (latest, features, backtest, runs, history, health):
        assert response.model_dump_json()
