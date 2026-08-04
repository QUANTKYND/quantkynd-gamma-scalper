from __future__ import annotations

import threading


class MarketDataMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {
            "instrument_search_requests_total": 0,
            "historical_candle_requests_total": 0,
            "historical_candle_failures_total": 0,
            "market_feed_connections_total": 0,
            "market_feed_reconnects_total": 0,
            "market_feed_messages_total": 0,
            "market_feed_invalid_messages_total": 0,
            "market_feed_subscription_changes_total": 0,
            "market_feed_dropped_or_coalesced_updates_total": 0,
            "rv_live_recomputations_total": 0,
        }

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)
