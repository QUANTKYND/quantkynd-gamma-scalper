from app.api.routes import health
from app.main import app


def _route_paths():
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            yield path

        effective_candidates = getattr(route, "effective_candidates", None)
        if callable(effective_candidates):
            for candidate in effective_candidates():
                candidate_path = getattr(candidate, "path", None)
                if candidate_path:
                    yield candidate_path


def test_health():
    assert "/api/v1/health" in set(_route_paths())

    res = health()

    assert res.status == "ok"
    assert res.service == "Trading Platform API"
