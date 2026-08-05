from dataclasses import replace
from datetime import timedelta

import pytest

from app.market_data.upstox.proto import MarketDataFeed_pb2
from tests.market_data.normalization.helpers import AT
from tests.market_data.upstox.test_v3_normalizer import feed_response, normalize


def _status_event():
    response = feed_response(MarketDataFeed_pb2.market_info)
    response.marketInfo.segmentStatus["NSE_FO"] = MarketDataFeed_pb2.NORMAL_OPEN
    return normalize(response).accepted_events[0]


@pytest.mark.parametrize(
    "changes,pattern",
    [
        ({"provider": "other"}, "subject identity"),
        ({"segment": "other"}, "subject identity"),
        ({"source_order": -1}, "source_order"),
        ({"source_order": True}, "source_order"),
        ({"source_order_scope_id": ""}, "non-empty"),
        ({"provider_status_name": "NORMAL_CLOSE"}, "known provider status"),
        ({"status_is_known": False}, "known provider status"),
        ({"available_at": AT - timedelta(seconds=1)}, "available_at"),
        ({"recorded_at": AT - timedelta(seconds=1)}, "recorded_at"),
    ],
)
def test_status_direct_construction_rejects_invalid_invariants(changes, pattern) -> None:
    with pytest.raises(ValueError, match=pattern):
        replace(_status_event(), **changes)


def test_unknown_status_requires_unknown_name_and_flag() -> None:
    event = _status_event()
    unknown = replace(
        event,
        provider_status_numeric=99,
        provider_status_name="UNKNOWN",
        status_is_known=False,
    )
    assert unknown.status_is_known is False
    with pytest.raises(ValueError, match="unknown provider status"):
        replace(unknown, provider_status_name="OTHER")
    with pytest.raises(ValueError, match="unknown provider status"):
        replace(unknown, status_is_known=True)
