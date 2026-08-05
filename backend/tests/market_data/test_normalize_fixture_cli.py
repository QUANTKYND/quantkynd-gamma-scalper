from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.cli.normalize_market_event_fixture import run
from tools.generate_market_event_fixtures import FIXTURE_DIR
from app.market_data.upstox.proto import MarketDataFeed_pb2


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
    assert "capture_provenance" not in payload["result"]
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


def test_fixture_cli_exit_four_for_real_raw_identity_conflict(tmp_path) -> None:
    baseline_bytes = (FIXTURE_DIR / "nifty-index-direct-ltpc.bin").read_bytes()
    baseline_frame = tmp_path / "baseline.bin"
    baseline_frame.write_bytes(baseline_bytes)
    capture = json.loads((FIXTURE_DIR / "nifty-option-live-market-ff-d5.capture.json").read_text(encoding="utf-8"))
    capture["frame_sha256"] = f"sha256:{hashlib.sha256(baseline_bytes).hexdigest()}"
    baseline_capture = tmp_path / "baseline.capture.json"
    baseline_capture.write_text(json.dumps(capture), encoding="utf-8")
    args = _arguments()
    args.extend(
        [
            "--identity-baseline-frame",
            str(baseline_frame),
            "--identity-baseline-capture-manifest",
            str(baseline_capture),
        ]
    )
    assert run(args)[0] == 4


def _structural_failure_args(tmp_path, frame_bytes):
    frame_path = tmp_path / "structural.bin"
    frame_path.write_bytes(frame_bytes)
    capture = json.loads((FIXTURE_DIR / "nifty-index-direct-ltpc.capture.json").read_text(encoding="utf-8"))
    capture["frame_sha256"] = f"sha256:{hashlib.sha256(frame_bytes).hexdigest()}"
    capture_path = tmp_path / "structural.capture.json"
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")[:-1]
    args[1] = str(frame_path)
    args[3] = str(capture_path)
    return args


@pytest.mark.parametrize(
    "frame_bytes,reason,response_type",
    [
        (b"\x80", "protobuf_decode_failed", None),
        (MarketDataFeed_pb2.FeedResponse(type=99, currentTs=1).SerializeToString(), "unsupported_response_type", None),
        (MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed).SerializeToString(), "missing_provider_timestamp", None),
        (MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed, currentTs=1).SerializeToString(), "empty_primary_payload", None),
    ],
)
def test_fixture_cli_structural_failures_are_canonical_without_traceback(tmp_path, frame_bytes, reason, response_type) -> None:
    code, output = run(_structural_failure_args(tmp_path, frame_bytes))
    assert code == 1
    payload = json.loads(output)
    assert payload["result"]["frame_failure"]["reason_code"] == reason
    assert payload["result"]["response_type"] == response_type
    assert "traceback" not in output.lower()
    assert "frame_bytes" not in output


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "other"),
        ("provider_schema_id", "other"),
        ("provider_schema_sha256", "sha256:" + "0" * 64),
        ("source_order", True),
    ],
)
def test_fixture_cli_rejects_hostile_capture_manifest_as_schema_error(tmp_path, field, value) -> None:
    capture = json.loads((FIXTURE_DIR / "nifty-index-direct-ltpc.capture.json").read_text(encoding="utf-8"))
    capture[field] = value
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")
    args[3] = str(path)
    expected = 3 if field != "source_order" else 2
    assert run(args)[0] == expected


def test_fixture_cli_rejects_boolean_subject_lot_size(tmp_path) -> None:
    subjects = json.loads((FIXTURE_DIR / "subjects.json").read_text(encoding="utf-8"))
    subjects["subjects"][0]["contract_version"]["lot_size"] = True
    path = tmp_path / "subjects.json"
    path.write_text(json.dumps(subjects), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")
    args[5] = str(path)
    assert run(args)[0] == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.pop("available_at"),
        lambda payload: payload.__setitem__("available_at", 1),
        lambda payload: payload.pop("capture_basis"),
        lambda payload: payload.__setitem__("capture_basis", {}),
    ],
)
def test_fixture_cli_rejects_malformed_capture_configuration_canonically(tmp_path, mutation) -> None:
    capture = json.loads((FIXTURE_DIR / "nifty-index-direct-ltpc.capture.json").read_text(encoding="utf-8"))
    mutation(capture)
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")
    args[3] = str(path)
    code, output = run(args)
    assert code == 2
    assert json.loads(output) == {"error": "manifest_configuration_error"}
    assert "traceback" not in output.lower()
    assert "frame_bytes" not in output


def _option_subject(payload):
    return next(item for item in payload["subjects"] if item["instrument_kind"] == "option")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.pop("subjects"),
        lambda payload: payload.__setitem__("subjects", {}),
        lambda payload: payload["subjects"][0].pop("economic_identity"),
        lambda payload: _option_subject(payload)["economic_identity"].pop("expiry"),
        lambda payload: _option_subject(payload)["economic_identity"].__setitem__("strike", 1),
        lambda payload: _option_subject(payload)["economic_identity"].__setitem__("strike", 0.05),
        lambda payload: _option_subject(payload)["economic_identity"].__setitem__("multiplier", True),
        lambda payload: payload["subjects"][0]["contract_version"].__setitem__("tick_size", 0.05),
        lambda payload: payload["subjects"][0]["provider_mapping"].pop("recorded_at"),
        lambda payload: payload["subjects"][0]["provider_mapping"].__setitem__("effective_from", 1),
    ],
)
def test_fixture_cli_rejects_hostile_subject_manifest_canonically(tmp_path, mutation) -> None:
    subjects = json.loads((FIXTURE_DIR / "subjects.json").read_text(encoding="utf-8"))
    mutation(subjects)
    path = tmp_path / "subjects.json"
    path.write_text(json.dumps(subjects), encoding="utf-8")
    args = _arguments("nifty-index-direct-ltpc")
    args[5] = str(path)
    code, output = run(args)
    assert code == 2
    assert json.loads(output) == {"error": "manifest_configuration_error"}
    assert "traceback" not in output.lower()
    assert "frame_bytes" not in output


def test_expected_hashes_cannot_approve_structural_frame_failure(tmp_path) -> None:
    args = _structural_failure_args(tmp_path, b"\x80")
    code, output = run(args)
    assert code == 1
    result = json.loads(output)["result"]
    capture_path = Path(args[3])
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["expected_event_ids"] = []
    capture["expected_full_result_sha256"] = result["full_result_hash"]
    capture["expected_adopted_semantics_sha256"] = result["adopted_semantics_hash"]
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    code, output = run(args + ["--verify-expected-hash"])
    assert code == 1
    assert json.loads(output)["result"]["frame_failure"] is not None


@pytest.mark.parametrize(
    "frame_bytes,reason,response_type",
    [
        (
            (lambda response: response.SerializeToString())(
                MarketDataFeed_pb2.FeedResponse(
                    type=MarketDataFeed_pb2.live_feed,
                    currentTs=1_754_365_200_123,
                    feeds={" bad": MarketDataFeed_pb2.Feed(requestMode=MarketDataFeed_pb2.ltpc, ltpc=MarketDataFeed_pb2.LTPC())},
                )
            ),
            "invalid_provider_contract_key",
            "live_feed",
        ),
        (
            (lambda response: response.SerializeToString())(
                MarketDataFeed_pb2.FeedResponse(
                    type=MarketDataFeed_pb2.market_info,
                    currentTs=1_754_365_200_123,
                    marketInfo=MarketDataFeed_pb2.MarketInfo(segmentStatus={"bad ": MarketDataFeed_pb2.NORMAL_OPEN}),
                )
            ),
            "invalid_market_segment",
            "market_info",
        ),
    ],
)
def test_cli_provider_identity_failures_are_canonical(tmp_path, frame_bytes, reason, response_type) -> None:
    code, output = run(_structural_failure_args(tmp_path, frame_bytes))
    assert code == 1
    assert output == json.dumps(json.loads(output), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    result = json.loads(output)["result"]
    assert result["frame_failure"]["reason_code"] == reason
    assert result["response_type"] == response_type
    assert "traceback" not in output.lower()
    assert "frame_bytes" not in output


def test_hostile_provider_identity_cli_output_is_hash_seed_independent(tmp_path) -> None:
    frames = []
    quote = MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed, currentTs=1_754_365_200_123)
    quote.feeds["\x00bad"].requestMode = MarketDataFeed_pb2.ltpc
    quote.feeds["\x00bad"].ltpc.CopyFrom(MarketDataFeed_pb2.LTPC())
    frames.append(quote.SerializeToString())
    status = MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.market_info, currentTs=1_754_365_200_123)
    status.marketInfo.segmentStatus[" bad"] = MarketDataFeed_pb2.NORMAL_OPEN
    frames.append(status.SerializeToString())
    for index, frame_bytes in enumerate(frames):
        case_path = tmp_path / str(index)
        case_path.mkdir()
        arguments = _structural_failure_args(case_path, frame_bytes)
        outputs = []
        for seed in ("1", "999"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            for name in ("DATABASE_URL", "DATABASE_RESTORE_TEST_URL", "UPSTOX_ACCESS_TOKEN", "REDIS_URL"):
                environment.pop(name, None)
            completed = subprocess.run(
                [sys.executable, "-m", "app.cli.normalize_market_event_fixture", *arguments],
                check=False,
                capture_output=True,
                env=environment,
            )
            assert completed.returncode == 1
            outputs.append(completed.stderr)
        assert outputs[0] == outputs[1]


def test_entry_only_failed_result_is_successful_when_reconciled_and_expected(tmp_path) -> None:
    response = MarketDataFeed_pb2.FeedResponse(type=MarketDataFeed_pb2.live_feed, currentTs=1_754_365_200_123)
    response.feeds["NSE_FO|unknown"].requestMode = MarketDataFeed_pb2.ltpc
    response.feeds["NSE_FO|unknown"].ltpc.CopyFrom(MarketDataFeed_pb2.LTPC())
    arguments = _structural_failure_args(tmp_path, response.SerializeToString())
    code, output = run(arguments)
    assert code == 0
    result = json.loads(output)["result"]
    assert result["status"] == "failed"
    assert result["frame_failure"] is None
    capture_path = Path(arguments[3])
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    capture["expected_event_ids"] = []
    capture["expected_full_result_sha256"] = result["full_result_hash"]
    capture["expected_adopted_semantics_sha256"] = result["adopted_semantics_hash"]
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    verified_code, verified_output = run(arguments + ["--verify-expected-hash"])
    assert verified_code == 0
    assert json.loads(verified_output)["result"]["status"] == "failed"
