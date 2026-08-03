from urllib.parse import parse_qs, urlparse

from app.api import auth as auth_api
from app.auth.state import generate_state, validate_state
from app.auth.token_store import TokenStore
from app.main import app


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


def test_auth_routes_are_registered_at_api_and_root_prefixes() -> None:
    paths = _route_paths()
    assert {
        "/api/v1/auth/upstox/login",
        "/api/v1/auth/upstox/callback",
        "/api/v1/auth/status",
        "/api/v1/auth/disconnect",
        "/auth/upstox/login",
        "/auth/upstox/callback",
        "/auth/status",
        "/auth/disconnect",
    }.issubset(paths)


def test_state_is_signed_and_one_time() -> None:
    state = generate_state()

    first_result = validate_state(state)
    replay_result = validate_state(state)
    tampered_result = validate_state(f"{state}x")

    assert first_result.valid is True
    assert replay_result.valid is False
    assert replay_result.reason == "state_replayed"
    assert tampered_result.valid is False


def test_token_store_round_trips_server_side_token(tmp_path) -> None:
    token_path = tmp_path / "upstox_token.json"
    store = TokenStore(str(token_path))

    assert store.is_connected() is False

    store.save_token({"access_token": "secret-token", "extended_token": "read-token", "broker": "UPSTOX"})

    reloaded_store = TokenStore(str(token_path))
    public_profile = reloaded_store.get_public_profile()

    assert reloaded_store.is_connected() is True
    assert public_profile is not None
    assert public_profile["broker"] == "UPSTOX"
    assert "access_token" not in public_profile
    assert "extended_token" not in public_profile

    reloaded_store.delete_token()

    assert reloaded_store.is_connected() is False
    assert not token_path.exists()


def test_callback_exchanges_code_and_persists_token(monkeypatch) -> None:
    saved_tokens: list[dict] = []

    class FakeConnector:
        def exchange_code_for_token(self, code: str) -> dict:
            assert code == "auth-code"
            return {"access_token": "secret-token", "broker": "UPSTOX"}

    class FakeTokenStore:
        def save_token(self, token: dict) -> None:
            saved_tokens.append(token)

    monkeypatch.setattr(auth_api, "get_broker_connector", lambda broker: FakeConnector())
    monkeypatch.setattr(auth_api, "token_store", FakeTokenStore())

    response = auth_api.upstox_callback(code="auth-code", state=generate_state())
    query = parse_qs(urlparse(response.headers["location"]).query)

    assert query["auth"] == ["success"]
    assert saved_tokens == [{"access_token": "secret-token", "broker": "UPSTOX"}]


def test_callback_handles_missing_code() -> None:
    response = auth_api.upstox_callback(code=None, state=generate_state())
    query = parse_qs(urlparse(response.headers["location"]).query)

    assert query["auth"] == ["error"]
    assert query["reason"] == ["missing_code"]
