from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.core.hashing import canonical_json
from app.market_data.normalization.errors import ConflictingRawIdentityError
from app.market_data.normalization.manifests import load_capture_manifest, load_subject_manifest
from app.market_data.normalization.serialization import canonical_normalization_json
from app.market_data.upstox.schema_verification import verify_upstox_v3_schema
from app.market_data.upstox.v3_decoder import decode_upstox_v3_frame
from app.services.market_frame_normalization_service import MarketFrameNormalizationService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize one deterministic Upstox V3 fixture")
    parser.add_argument("--frame", required=True, type=Path)
    parser.add_argument("--capture-manifest", required=True, type=Path)
    parser.add_argument("--subject-manifest", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), default="json")
    parser.add_argument("--verify-expected-hash", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> tuple[int, str]:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code), canonical_json({"error": "manifest_configuration_error"})
    try:
        verify_upstox_v3_schema()
    except (OSError, ValueError):
        return 3, canonical_json({"error": "schema_hash_verification_error"})
    try:
        frame_bytes = args.frame.read_bytes()
        frame, market_as_of, known_as_of, capture = load_capture_manifest(args.capture_manifest, frame_bytes)
        resolver = load_subject_manifest(args.subject_manifest)
    except FileNotFoundError:
        return 2, canonical_json({"error": "manifest_configuration_error"})
    except ValueError as error:
        code = 3 if "frame hash" in str(error) else 2
        reason = "schema_hash_verification_error" if code == 3 else "manifest_configuration_error"
        return code, canonical_json({"error": reason})
    try:
        decoded = decode_upstox_v3_frame(frame)
        result = asyncio.run(
            MarketFrameNormalizationService(resolver).normalize(
                frame,
                market_as_of=market_as_of,
                known_as_of=known_as_of,
            )
        )
    except ConflictingRawIdentityError:
        return 4, canonical_json({"error": "raw_identity_conflict"})
    result_payload = json.loads(canonical_normalization_json(result))
    payload = {
        "fixture_schema_version": capture["fixture_schema_version"],
        "response_type": {"0": "initial_feed", "1": "live_feed", "2": "market_info"}[
            str(decoded.response_type_numeric)
        ],
        "result": result_payload,
    }
    if args.verify_expected_hash:
        expected = (
            tuple(capture.get("expected_event_ids", ())),
            capture.get("expected_full_result_sha256"),
            capture.get("expected_adopted_semantics_sha256"),
        )
        actual = (
            tuple(event.event_id for event in result.accepted_events),
            result.full_result_hash,
            result.adopted_semantics_hash,
        )
        if actual != expected:
            return 1, canonical_json({"error": "normalization_result_mismatch"})
    return 0, canonical_json(payload)


def main(argv: list[str] | None = None) -> int:
    code, output = run(argv)
    stream = sys.stdout if code == 0 else sys.stderr
    stream.write(output + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
