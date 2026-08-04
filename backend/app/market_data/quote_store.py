from __future__ import annotations

from datetime import UTC, datetime

from app.market_data.models import FreshnessState, LiveQuoteState


class LiveQuoteStore:
    def __init__(self, stale_after_seconds: int) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._quotes: dict[str, LiveQuoteState] = {}
        self._forced_stale: set[str] = set()

    def put(self, quote: LiveQuoteState) -> bool:
        current = self._quotes.get(quote.instrument_key)
        if current is None or quote.sequence > current.sequence:
            self._quotes[quote.instrument_key] = quote
            self._forced_stale.discard(quote.instrument_key)
            return True
        return False

    def get(self, instrument_key: str) -> LiveQuoteState | None:
        return self._quotes.get(instrument_key)

    def freshness(self, instrument_key: str, now: datetime | None = None) -> FreshnessState:
        quote = self.get(instrument_key)
        if quote is None:
            return "awaiting_first_tick"
        if instrument_key in self._forced_stale:
            return "stale"
        reference = now or datetime.now(UTC)
        age = (reference - quote.received_at).total_seconds()
        return "fresh" if age <= self._stale_after_seconds else "stale"

    def mark_stale(self, instrument_keys: tuple[str, ...]) -> None:
        self._forced_stale.update(key for key in instrument_keys if key in self._quotes)
