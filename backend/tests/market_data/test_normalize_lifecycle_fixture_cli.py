from __future__ import annotations

import json

import pytest

from app.cli.normalize_market_lifecycle_fixture import run
from tools.generate_market_event_fixtures import FIXTURE_DIR


def _args(name):
    return ["--fixture", str(FIXTURE_DIR / name), "--output", "json"]


def test_lifecycle_cli_normalizes_connection_subscription_and_reconnect() -> None:
    for name in ("connection-lifecycle.json", "subscription-lifecycle.json", "reconnect-lifecycle.json"):
        code, output = run(_args(name))
        assert code == 0
        assert output == json.dumps(json.loads(output), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        assert json.loads(output)["normalized_sequence_hash"].startswith("sha256:")


def test_lifecycle_cli_reports_invalid_transition() -> None:
    code, output = run(_args("invalid-lifecycle.json"))
    assert code == 1
    assert json.loads(output)["error"] == "invalid_connection_lifecycle_transition"


def test_lifecycle_cli_has_sorted_digest_and_redacted_reason() -> None:
    code, output = run(_args("subscription-lifecycle.json"))
    assert code == 0
    events = json.loads(output)["events"]
    assert len({item["instrument_keys_digest"] for item in events}) == 1
    assert events[-1]["redacted_reason_code"] == "provider_rejected_request"
    assert "NSE_FO" not in events[-1]["instrument_keys_digest"]


def test_lifecycle_cli_uses_real_identity_collision_check(tmp_path) -> None:
    payload = json.loads((FIXTURE_DIR / "connection-lifecycle.json").read_text(encoding="utf-8"))
    conflicting = dict(payload["events"][0])
    conflicting["occurred_at"] = "2026-08-05T03:59:59+00:00"
    payload["events"] = [payload["events"][0], conflicting]
    path = tmp_path / "collision.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, output = run(["--fixture", str(path), "--output", "json"])
    assert code == 1
    assert json.loads(output)["error"] == "raw_identity_conflict"


def test_lifecycle_cli_rejects_boolean_source_order(tmp_path) -> None:
    payload = json.loads((FIXTURE_DIR / "connection-lifecycle.json").read_text(encoding="utf-8"))
    payload["events"][0]["source_order"] = True
    path = tmp_path / "boolean-order.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert run(["--fixture", str(path), "--output", "json"])[0] == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.pop("fixture_schema_version"),
        lambda payload: payload.__setitem__("fixture_schema_version", "wrong"),
        lambda payload: payload["events"][0].__setitem__("occurred_at", 1),
        lambda payload: payload["events"][0].__setitem__("occurred_at", {}),
        lambda payload: payload.pop("events"),
        lambda payload: payload.__setitem__("events", {}),
    ],
)
def test_lifecycle_cli_hostile_configuration_is_canonical(tmp_path, mutation) -> None:
    payload = json.loads((FIXTURE_DIR / "connection-lifecycle.json").read_text(encoding="utf-8"))
    mutation(payload)
    path = tmp_path / "hostile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, output = run(["--fixture", str(path), "--output", "json"])
    assert code == 2
    assert json.loads(output) == {"error": "lifecycle_fixture_configuration_error"}
    assert "traceback" not in output.lower()


@pytest.mark.parametrize("value", [{}, "not-an-array", [True]])
def test_lifecycle_cli_rejects_hostile_provider_keys(tmp_path, value) -> None:
    payload = json.loads((FIXTURE_DIR / "subscription-lifecycle.json").read_text(encoding="utf-8"))
    payload["events"][0]["provider_contract_keys"] = value
    path = tmp_path / "hostile-subscription.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert run(["--fixture", str(path), "--output", "json"])[0] == 2


@pytest.mark.parametrize("fixture", ["connection-lifecycle.json", "subscription-lifecycle.json"])
def test_lifecycle_cli_deduplicates_exact_raw_identity_in_capture_order(tmp_path, fixture) -> None:
    payload = json.loads((FIXTURE_DIR / fixture).read_text(encoding="utf-8"))
    payload["events"].insert(1, dict(payload["events"][0]))
    path = tmp_path / fixture
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, output = run(["--fixture", str(path), "--output", "json"])
    assert code == 0
    result = json.loads(output)
    assert len(result["events"]) == len(payload["events"]) - 1
    assert len(result["exact_duplicate_raw_event_ids"]) == 1
