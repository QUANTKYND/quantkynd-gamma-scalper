from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.hashing import canonical_json
from app.market_data.normalization.identities import RawMarketFrameV1
from app.market_data.normalization.ports import StaticSubjectManifestResolver
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.market_data.upstox.v3_schema import UPSTOX_V3_SCHEMA_ID, UPSTOX_V3_SCHEMA_SHA256
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tests.market_data.normalization.helpers import AT, subjects


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "upstox" / "market_feed_v3"


def _ltpc(ltp=25000.5, ltq=4, cp=24950.0):
    return MarketDataFeed_pb2.LTPC(ltp=ltp, ltt=1_754_365_200_000, ltq=ltq, cp=cp)


def _response(response_type=MarketDataFeed_pb2.live_feed):
    return MarketDataFeed_pb2.FeedResponse(type=response_type, currentTs=1_754_365_200_123)


def _market_feed(key, *, levels=1, mode=MarketDataFeed_pb2.full_d5):
    response = _response()
    feed = response.feeds[key]
    feed.requestMode = mode
    payload = feed.fullFeed.marketFF
    payload.ltpc.CopyFrom(_ltpc())
    for index in range(levels):
        payload.marketLevel.bidAskQuote.add(
            bidQ=10 + index,
            bidP=100.25 - index * 0.05,
            askQ=20 + index,
            askP=100.5 + index * 0.05,
        )
    payload.vtt = 300
    payload.oi = 500.0
    return response


def fixture_bytes() -> dict[str, bytes]:
    fixtures: dict[str, bytes] = {}

    response = _response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus["NSE_EQ"] = MarketDataFeed_pb2.NORMAL_OPEN
    response.marketInfo.segmentStatus["NSE_FO"] = MarketDataFeed_pb2.PRE_OPEN_END
    fixtures["multiple-segment-market-info"] = response.SerializeToString(deterministic=True)

    response = _response(MarketDataFeed_pb2.initial_feed)
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.indexFF.ltpc.CopyFrom(_ltpc())
    fixtures["nifty-index-initial-index-ff"] = response.SerializeToString(deterministic=True)
    fixtures["nifty-future-live-market-ff-d5"] = _market_feed("NSE_FO|future").SerializeToString(deterministic=True)
    fixtures["nifty-option-live-market-ff-d5"] = _market_feed("NSE_FO|option", levels=5).SerializeToString(deterministic=True)

    response = _response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.option_greeks
    feed.firstLevelWithGreeks.ltpc.CopyFrom(_ltpc())
    feed.firstLevelWithGreeks.firstDepth.CopyFrom(
        MarketDataFeed_pb2.Quote(bidQ=2, bidP=20.0, askQ=3, askP=20.5)
    )
    feed.firstLevelWithGreeks.optionGreeks.delta = 0.5
    feed.firstLevelWithGreeks.iv = 0.2
    fixtures["nifty-option-first-level-with-greeks"] = response.SerializeToString(deterministic=True)

    response = _response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(_ltpc())
    fixtures["nifty-index-direct-ltpc"] = response.SerializeToString(deterministic=True)

    map_feeds = (
        ("NSE_INDEX|Nifty 50", MarketDataFeed_pb2.Feed(ltpc=_ltpc(), requestMode=MarketDataFeed_pb2.ltpc)),
        ("NSE_FO|option", MarketDataFeed_pb2.Feed(ltpc=_ltpc(20.5), requestMode=MarketDataFeed_pb2.ltpc)),
    )
    fixtures["multi-feed-map-order-a"] = _feed_response_wire(map_feeds)
    fixtures["multi-feed-map-order-b"] = _feed_response_wire(tuple(reversed(map_feeds)))

    response = _response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(MarketDataFeed_pb2.LTPC())
    fixtures["all-adopted-zero-values"] = response.SerializeToString(deterministic=True)

    response = _response()
    for key in ("NSE_INDEX|Nifty 50", "NSE_FO|unknown"):
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(_ltpc())
    fixtures["mixed-valid-and-unknown-provider-key"] = response.SerializeToString(deterministic=True)

    response = _response()
    feed = response.feeds["NSE_FO|option"]
    feed.requestMode = MarketDataFeed_pb2.full_d5
    feed.fullFeed.indexFF.ltpc.CopyFrom(_ltpc())
    fixtures["subject-union-mismatch"] = response.SerializeToString(deterministic=True)

    response = _response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus["NSE_EQ"] = 99
    fixtures["unknown-market-status"] = response.SerializeToString(deterministic=True)

    response = _response()
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(_ltpc())
    response.marketInfo.segmentStatus["NSE_EQ"] = MarketDataFeed_pb2.NORMAL_OPEN
    fixtures["secondary-payload-coexistence"] = response.SerializeToString(deterministic=True)

    deferred = _market_feed("NSE_FO|option", levels=5)
    payload = deferred.feeds["NSE_FO|option"].fullFeed.marketFF
    payload.optionGreeks.CopyFrom(MarketDataFeed_pb2.OptionGreeks(delta=0.1, theta=0.2, gamma=0.3, vega=0.4, rho=0.5))
    payload.marketOHLC.ohlc.add(interval="1d", open=1, high=2, low=0.5, close=1.5, vol=10, ts=1)
    payload.atp = 101
    payload.iv = 0.2
    payload.tbq = 1000
    payload.tsq = 2000
    fixtures["all-deferred-fields-populated"] = deferred.SerializeToString(deterministic=True)

    changed = MarketDataFeed_pb2.FeedResponse()
    changed.CopyFrom(deferred)
    payload = changed.feeds["NSE_FO|option"].fullFeed.marketFF
    payload.optionGreeks.delta = 0.9
    payload.marketOHLC.ohlc[0].high = 999
    payload.atp = 888
    payload.iv = 0.8
    payload.tbq = 3000
    payload.tsq = 4000
    for quote in payload.marketLevel.bidAskQuote[1:]:
        quote.bidP += 50
    fixtures["changed-deferred-fields"] = changed.SerializeToString(deterministic=True)

    fixtures["unknown-wire-field"] = fixtures["nifty-index-direct-ltpc"] + b"\x98\x06\x01"
    fixtures["nifty-option-live-market-ff-d30"] = _market_feed(
        "NSE_FO|option", levels=30, mode=MarketDataFeed_pb2.full_d30
    ).SerializeToString(deterministic=True)
    return fixtures


def _feed_response_wire(items) -> bytes:
    chunks = [b"\x08\x01"]
    for key, feed in items:
        key_bytes = key.encode("utf-8")
        feed_bytes = feed.SerializeToString(deterministic=True)
        entry = b"\x0a" + _varint(len(key_bytes)) + key_bytes + b"\x12" + _varint(len(feed_bytes)) + feed_bytes
        chunks.append(b"\x12" + _varint(len(entry)) + entry)
    timestamp = 1_754_365_200_123
    chunks.append(b"\x18" + _varint(timestamp))
    return b"".join(chunks)


def _varint(value: int) -> bytes:
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def build_tree(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    subject_values = subjects()
    from app.market_data.normalization.manifests import subject_manifest_payload

    (target / "subjects.json").write_text(canonical_json(subject_manifest_payload(subject_values)), encoding="utf-8")
    service = MarketFrameNormalizationService(StaticSubjectManifestResolver(subject_values))
    inventory = []
    for source_order, (name, frame_bytes) in enumerate(sorted(fixture_bytes().items()), start=1):
        frame_hash = f"sha256:{hashlib.sha256(frame_bytes).hexdigest()}"
        frame = RawMarketFrameV1(
            provider="upstox",
            provider_schema_id=UPSTOX_V3_SCHEMA_ID,
            provider_schema_sha256=UPSTOX_V3_SCHEMA_SHA256,
            connection_session_id="fixture-connection-1",
            source_order_scope_id="fixture-capture-1",
            source_order=source_order,
            frame_bytes=frame_bytes,
            frame_content_hash=frame_hash,
            received_at=AT,
            available_at=AT,
            recorded_at=AT,
            capture_basis="live_received",
            source_file_id="synthetic-upstox-v3-fixtures",
            source_record_id=name,
        )
        result = asyncio.run(service.normalize(frame, market_as_of=AT, known_as_of=AT))
        capture = {
            "fixture_schema_version": "data-1.3-fixture-v1",
            "provider_schema_id": UPSTOX_V3_SCHEMA_ID,
            "provider_schema_sha256": UPSTOX_V3_SCHEMA_SHA256,
            "connection_session_id": frame.connection_session_id,
            "source_order_scope_id": frame.source_order_scope_id,
            "source_order": source_order,
            "capture_basis": frame.capture_basis.value,
            "received_at": AT,
            "available_at": AT,
            "recorded_at": AT,
            "source_file_id": frame.source_file_id,
            "source_record_id": frame.source_record_id,
            "resolution_market_as_of": AT,
            "resolution_known_as_of": AT,
            "frame_sha256": frame_hash,
            "expected_event_ids": tuple(event.event_id for event in result.accepted_events),
            "expected_full_result_sha256": result.full_result_hash,
            "expected_adopted_semantics_sha256": result.adopted_semantics_hash,
        }
        (target / f"{name}.bin").write_bytes(frame_bytes)
        (target / f"{name}.capture.json").write_text(canonical_json(capture), encoding="utf-8")
        inventory.append({"file": f"{name}.bin", "bytes": len(frame_bytes), "sha256": frame_hash})
    (target / "inventory.json").write_text(canonical_json({"files": tuple(inventory)}), encoding="utf-8")


def verify_tree(target: Path) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as directory:
        generated = Path(directory)
        build_tree(generated)
        expected = tuple(sorted(path.relative_to(generated).as_posix() for path in generated.iterdir()))
        actual = tuple(name for name in expected if (target / name).is_file())
        if actual != expected:
            raise ValueError("fixture inventory drift")
        drift = tuple(name for name in expected if (target / name).read_bytes() != (generated / name).read_bytes())
        if drift:
            raise ValueError(f"fixture content drift: {', '.join(drift)}")
        return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        build_tree(FIXTURE_DIR)
    else:
        verify_tree(FIXTURE_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
