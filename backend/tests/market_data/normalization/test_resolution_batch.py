from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping

from app.market_data.normalization.ports import SubjectResolutionBatch, SubjectResolutionFailureV1
from app.market_data.upstox.proto import MarketDataFeed_pb2
from app.services.market_frame_normalization_service import MarketFrameNormalizationService
from tests.market_data.normalization.helpers import AT, raw_frame
from tests.market_data.upstox.test_v3_normalizer import feed_response, ltpc


class CountingMapping(Mapping):
    def __init__(self, values):
        self.values = values
        self.get_count = 0

    def __getitem__(self, key):
        self.get_count += 1
        return self.values[key]

    def __iter__(self) -> Iterator:
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class FixedResolver:
    def __init__(self, batch):
        self.batch = batch
        self.requested_keys = None

    async def resolve_many(self, provider, provider_contract_keys, market_as_of, known_as_of):
        self.requested_keys = provider_contract_keys
        return self.batch


def test_five_thousand_key_batch_uses_one_indexed_lookup_per_key() -> None:
    keys = tuple(f"key-{index:04d}" for index in range(5000))
    failures = tuple(SubjectResolutionFailureV1(key, "unknown_provider_key") for key in keys)
    batch = SubjectResolutionBatch((), failures)
    instrumented = CountingMapping(dict(zip(keys, failures, strict=True)))
    object.__setattr__(batch, "_failure_by_key", instrumented)
    resolver = FixedResolver(batch)
    response = feed_response()
    for key in keys:
        feed = response.feeds[key]
        feed.requestMode = MarketDataFeed_pb2.ltpc
        feed.ltpc.CopyFrom(ltpc())
    result = asyncio.run(
        MarketFrameNormalizationService(resolver).normalize(
            raw_frame(response.SerializeToString()),
            market_as_of=AT,
            known_as_of=AT,
        )
    )
    assert resolver.requested_keys == keys
    assert instrumented.get_count == 5000
    assert result.decoded_entry_count == 5000
    assert result.failed_entry_count == 5000


def test_service_rejects_missing_or_extra_resolver_keys() -> None:
    response = feed_response()
    feed = response.feeds["requested"]
    feed.requestMode = MarketDataFeed_pb2.ltpc
    feed.ltpc.CopyFrom(ltpc())
    for failures in (
        (),
        (SubjectResolutionFailureV1("extra", "unknown_provider_key"),),
    ):
        result = asyncio.run(
            MarketFrameNormalizationService(FixedResolver(SubjectResolutionBatch((), failures))).normalize(
                raw_frame(response.SerializeToString()),
                market_as_of=AT,
                known_as_of=AT,
            )
        )
        assert result.frame_failure is not None
        assert result.frame_failure.reason_code == "invalid_subject_resolution_batch"
        assert result.decoded_entry_count == 1
