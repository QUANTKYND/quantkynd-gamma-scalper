from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

from app.market_data.normalization.manifests import load_capture_manifest, load_subject_manifest
from app.market_data.upstox.schema_verification import verify_upstox_v3_schema
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tools.generate_market_event_fixtures import FIXTURE_DIR, verify_tree


def _normalize(name: str):
    frame_path = FIXTURE_DIR / f"{name}.bin"
    capture_path = FIXTURE_DIR / f"{name}.capture.json"
    frame, market_as_of, known_as_of, capture = load_capture_manifest(capture_path, frame_path.read_bytes())
    resolver = load_subject_manifest(FIXTURE_DIR / "subjects.json")
    result = asyncio.run(
        MarketFrameNormalizationService(resolver).normalize(
            frame,
            market_as_of=market_as_of,
            known_as_of=known_as_of,
        )
    )
    return frame, capture, result


def test_fixture_inventory_and_every_sidecar_hash_replay() -> None:
    inventory = json.loads((FIXTURE_DIR / "inventory.json").read_text(encoding="utf-8"))["files"]
    assert len(inventory) == 17
    for item in inventory:
        name = Path(item["file"]).stem
        frame, capture, result = _normalize(name)
        assert len(frame.frame_bytes) == int(item["bytes"])
        assert frame.frame_content_hash == item["sha256"] == capture["frame_sha256"]
        assert tuple(event.event_id for event in result.accepted_events) == tuple(capture["expected_event_ids"])
        assert result.full_result_hash == capture["expected_full_result_sha256"]
        assert result.adopted_semantics_hash == capture["expected_adopted_semantics_sha256"]


def test_fixture_regeneration_is_byte_identical() -> None:
    assert len(verify_tree(FIXTURE_DIR)) == 36


def test_schema_ownership_and_hashes_are_current() -> None:
    verify_upstox_v3_schema()


def test_deferred_field_pair_proves_hash_boundary() -> None:
    left_frame, _, left = _normalize("all-deferred-fields-populated")
    right_frame, _, right = _normalize("changed-deferred-fields")
    assert left_frame.frame_content_hash != right_frame.frame_content_hash
    assert left.full_result_hash != right.full_result_hash
    assert left.adopted_semantics_hash == right.adopted_semantics_hash
    left_event = left.accepted_events[0]
    right_event = right.accepted_events[0]
    adopted_fields = (
        "bid_price",
        "bid_size",
        "ask_price",
        "ask_size",
        "last_price",
        "last_size",
        "previous_close_price",
        "reported_volume",
        "open_interest",
        "provider_depth_levels_present",
        "normalized_depth_levels",
    )
    assert tuple(getattr(left_event, name) for name in adopted_fields) == tuple(
        getattr(right_event, name) for name in adopted_fields
    )


def test_map_wire_order_is_semantically_deterministic() -> None:
    left_frame, _, left = _normalize("multi-feed-map-order-a")
    right_frame, _, right = _normalize("multi-feed-map-order-b")
    assert left_frame.frame_bytes != right_frame.frame_bytes
    assert left.adopted_semantics_hash == right.adopted_semantics_hash
    assert [event.economic_subject_id for event in left.accepted_events] == [
        event.economic_subject_id for event in right.accepted_events
    ]


def test_capture_identity_changes_full_identity_but_not_adopted_semantics() -> None:
    frame, _, left = _normalize("nifty-index-direct-ltpc")
    changed = replace(frame, source_order=frame.source_order + 100)
    resolver = load_subject_manifest(FIXTURE_DIR / "subjects.json")
    right = asyncio.run(MarketFrameNormalizationService(resolver).normalize(changed, market_as_of=frame.available_at, known_as_of=frame.available_at))
    assert left.full_result_hash != right.full_result_hash
    assert left.accepted_events[0].event_id != right.accepted_events[0].event_id
    assert left.adopted_semantics_hash == right.adopted_semantics_hash


def test_adopted_field_change_changes_adopted_semantics_hash() -> None:
    frame, _, left = _normalize("nifty-index-direct-ltpc")
    response = MarketDataFeed_pb2.FeedResponse()
    response.ParseFromString(frame.frame_bytes)
    response.feeds["NSE_INDEX|Nifty 50"].ltpc.ltp += 1
    changed_bytes = response.SerializeToString(deterministic=True)
    import hashlib

    changed = replace(
        frame,
        source_order=frame.source_order + 101,
        frame_bytes=changed_bytes,
        frame_content_hash=f"sha256:{hashlib.sha256(changed_bytes).hexdigest()}",
    )
    resolver = load_subject_manifest(FIXTURE_DIR / "subjects.json")
    right = asyncio.run(MarketFrameNormalizationService(resolver).normalize(changed, market_as_of=frame.available_at, known_as_of=frame.available_at))
    assert left.adopted_semantics_hash != right.adopted_semantics_hash


def test_frame_and_lifecycle_cli_outputs_ignore_python_hash_seed() -> None:
    commands = (
        [
            sys.executable,
            "-m",
            "app.cli.normalize_market_event_fixture",
            "--frame",
            str(FIXTURE_DIR / "multi-feed-map-order-a.bin"),
            "--capture-manifest",
            str(FIXTURE_DIR / "multi-feed-map-order-a.capture.json"),
            "--subject-manifest",
            str(FIXTURE_DIR / "subjects.json"),
            "--output",
            "json",
            "--verify-expected-hash",
        ],
        [
            sys.executable,
            "-m",
            "app.cli.normalize_market_lifecycle_fixture",
            "--fixture",
            str(FIXTURE_DIR / "subscription-lifecycle.json"),
            "--output",
            "json",
        ],
    )
    for command in commands:
        outputs = []
        for seed in ("1", "999"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            for name in ("DATABASE_URL", "DATABASE_RESTORE_TEST_URL", "UPSTOX_ACCESS_TOKEN", "REDIS_URL"):
                environment.pop(name, None)
            outputs.append(subprocess.run(command, check=True, capture_output=True, env=environment).stdout)
        assert outputs[0] == outputs[1]
