from __future__ import annotations

import json

from app.cli.normalize_market_event_fixture import run
from app.market_data.normalization.errors import ConflictingRawIdentityError
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tools.generate_market_event_fixtures import FIXTURE_DIR


def _arguments(name="nifty-option-live-market-ff-d5"):
    return [
        "--frame",
        str(FIXTURE_DIR / f"{name}.bin"),
        "--capture-manifest",
        str(FIXTURE_DIR / f"{name}.capture.json"),
        "--subject-manifest",
        str(FIXTURE_DIR / "subjects.json"),
        "--output",
        "json",
        "--verify-expected-hash",
    ]


def test_fixture_cli_success_is_canonical_json(monkeypatch) -> None:
    for name in ("DATABASE_URL", "DATABASE_RESTORE_TEST_URL", "UPSTOX_ACCESS_TOKEN", "REDIS_URL"):
        monkeypatch.delenv(name, raising=False)
    code, output = run(_arguments())
    assert code == 0
    assert output == json.dumps(json.loads(output), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload = json.loads(output)
    assert payload["response_type"] == "live_feed"
    assert payload["result"]["accepted_entry_count"] == "1"
    assert "frame_bytes" not in output


def test_fixture_cli_exit_one_for_expected_result_mismatch(tmp_path) -> None:
    capture = json.loads((FIXTURE_DIR / "nifty-index-direct-ltpc.capture.json").read_text(encoding="utf-8"))
    capture["expected_full_result_sha256"] = "sha256:" + "0" * 64
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")
    args[3] = str(path)
    assert run(args)[0] == 1


def test_fixture_cli_exit_two_for_manifest_configuration_error(tmp_path) -> None:
    args = _arguments()
    args[5] = str(tmp_path / "missing.json")
    assert run(args)[0] == 2


def test_fixture_cli_exit_three_for_frame_hash_error(tmp_path) -> None:
    path = tmp_path / "corrupt.bin"
    path.write_bytes(b"corrupt")
    args = _arguments()
    args[1] = str(path)
    assert run(args)[0] == 3


def test_fixture_cli_exit_four_for_raw_identity_conflict(monkeypatch) -> None:
    async def conflicting(self, frame, *, market_as_of, known_as_of):
        raise ConflictingRawIdentityError(frame.raw_event_id)

    monkeypatch.setattr(MarketFrameNormalizationService, "normalize", conflicting)
    assert run(_arguments())[0] == 4
