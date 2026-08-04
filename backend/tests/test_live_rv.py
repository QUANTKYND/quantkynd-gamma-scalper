import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import httpx

from app.instruments.models import InstrumentDefinition
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.errors import InstrumentNotFound, SubscriptionRejected
from app.market_data.models import HistoricalCloseDataset, LiveQuoteState
from app.market_data.metrics import MarketDataMetrics
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.history import normalize_daily_closes
from app.market_data.upstox.instruments import normalize_instrument
from app.market_data.upstox.normalization import market_status_for_segment, normalize_feed_quotes, normalize_segment_statuses
from app.market_data.upstox.streamer import UpstoxLiveMarketProvider
from app.api.market_streams import _stream, market_state_stream
from app.services.rv_live_overlay import RVLiveOverlayBuilder
from app.services.rv_registry import InstrumentRVServiceRegistry
from app.main import app


INSTRUMENT = InstrumentDefinition(
    instrument_key="NSE_INDEX|Nifty 50",
    exchange="NSE",
    segment="NSE_INDEX",
    kind="index",
    name="NIFTY 50",
    short_name="NIFTY 50",
    trading_symbol="NIFTY 50",
    isin=None,
    tick_size=0.05,
    lot_size=1,
)


class FakeInstruments:
    async def resolve(self, instrument_key):
        assert instrument_key == INSTRUMENT.instrument_key
        return INSTRUMENT

    async def search(self, query, exchanges, kinds, limit):
        return (INSTRUMENT,) if "NIFTY" in query.upper() else ()


class FakeHistory:
    def __init__(self, prices):
        self.prices = prices

    async def daily_closes(self, instrument_key, from_date, to_date):
        return HistoricalCloseDataset(instrument_key=instrument_key, prices=self.prices)


class FakeLiveProvider:
    def __init__(self):
        self.subscribes = []
        self.unsubscribes = []
        self.stopped = False

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def subscribe(self, keys):
        self.subscribes.append(keys)

    async def unsubscribe(self, keys):
        self.unsubscribes.append(keys)


class TokenState:
    def __init__(self, connected=True):
        self.connected = connected

    def is_connected(self):
        return self.connected


class ControlledLiveProvider(FakeLiveProvider):
    def __init__(self, fail=False):
        super().__init__()
        self.fail = fail
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def subscribe(self, keys):
        self.subscribes.append(keys)
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("provider failure")


class SelectiveLiveProvider(FakeLiveProvider):
    def __init__(self, pending_key):
        super().__init__()
        self.pending_key = pending_key
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def subscribe(self, keys):
        self.subscribes.append(keys)
        if keys == (self.pending_key,):
            self.entered.set()
            await self.release.wait()
            raise RuntimeError("provider failure")


class FakeWebSocket:
    def __init__(self, runtime):
        self.app = SimpleNamespace(state=SimpleNamespace(live_runtime=runtime))
        self.accepted = False
        self.denial = None
        self.closed = None
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_denial_response(self, response):
        self.denial = response

    async def close(self, code, reason):
        self.closed = (code, reason)

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive(self):
        return {"type": "websocket.disconnect", "code": 1000}


class EventWebSocket(FakeWebSocket):
    def __init__(self, runtime, stop_event_type):
        super().__init__(runtime)
        self.stop_event_type = stop_event_type
        self.disconnect = asyncio.Event()

    async def send_json(self, payload):
        self.sent.append(payload)
        if payload["event_type"] == self.stop_event_type:
            self.disconnect.set()

    async def receive(self):
        await self.disconnect.wait()
        return {"type": "websocket.disconnect", "code": 1000}


class HoldingWebSocket(FakeWebSocket):
    def __init__(self, runtime):
        super().__init__(runtime)
        self.status_seen = asyncio.Event()
        self.disconnect = asyncio.Event()

    async def send_json(self, payload):
        self.sent.append(payload)
        if payload["event_type"] == "feed_status_changed":
            self.status_seen.set()

    async def receive(self):
        await self.disconnect.wait()
        return {"type": "websocket.disconnect", "code": 1000}


class UnknownInstruments(FakeInstruments):
    async def resolve(self, instrument_key):
        raise InstrumentNotFound(instrument_key)


class FailingRegistry:
    async def get(self, instrument_key):
        raise RuntimeError("history unavailable")


def prices() -> pd.Series:
    index = pd.bdate_range(end="2026-08-03", periods=180)
    return pd.Series([20_000 + index_value * 2 for index_value in range(180)], index=index, dtype=float)


def quote(ltp: float, received_at: datetime | None = None) -> LiveQuoteState:
    timestamp = received_at or datetime(2026, 8, 4, 5, 0, tzinfo=UTC)
    return LiveQuoteState(
        instrument_key=INSTRUMENT.instrument_key,
        ltp=ltp,
        previous_close=20_358,
        last_trade_quantity=10,
        last_trade_at=timestamp,
        provider_message_at=timestamp,
        received_at=timestamp,
        processed_at=timestamp,
        market_status="open",
        sequence=1,
    )


def feed_payload(items, statuses=None):
    timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
    return {
        "currentTs": timestamp,
        "marketInfo": {"segmentStatus": statuses or {}},
        "feeds": {
            key: {"ltpc": {"ltp": ltp, "ltt": timestamp, "ltq": 1, "cp": ltp - 1}}
            for key, ltp in items
        },
    }


def test_historical_candles_are_sorted_deduplicated_and_filtered() -> None:
    payload = {"data": {"candles": [
        ["2026-08-03T15:30:00+05:30", 1, 2, 1, 101, 0, 0],
        ["2026-08-01T15:30:00+05:30", 1, 2, 1, -1, 0, 0],
        ["2026-08-02T15:30:00+05:30", 1, 2, 1, 99, 0, 0],
        ["2026-08-03T15:31:00+05:30", 1, 2, 1, 102, 0, 0],
    ]}}

    result = normalize_daily_closes(payload)

    assert list(result.index.strftime("%Y-%m-%d")) == ["2026-08-02", "2026-08-03"]
    assert result.iloc[-1] == 102


def test_instrument_normalization_rejects_derivatives() -> None:
    valid = normalize_instrument({
        "instrument_key": "NSE_EQ|INE002A01018",
        "segment": "NSE_EQ",
        "name": "Reliance Industries Ltd",
        "trading_symbol": "RELIANCE",
        "lot_size": 1,
    })
    invalid = normalize_instrument({
        "instrument_key": "NSE_FO|123",
        "segment": "NSE_FO",
        "name": "NIFTY FUT",
        "trading_symbol": "NIFTY26AUGFUT",
    })

    assert valid is not None and valid.kind == "equity"
    assert invalid is None


def test_registry_dataset_id_ignores_live_quotes() -> None:
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    service = asyncio.run(registry.get(INSTRUMENT.instrument_key))
    overlay = RVLiveOverlayBuilder()

    first = overlay.latest(service.snapshot, INSTRUMENT, quote(20_400), "fresh")
    second = overlay.latest(service.snapshot, INSTRUMENT, quote(20_500), "fresh")

    assert first.live.is_provisional is True
    assert second.live.is_provisional is True
    assert first.dataset.dataset_id == second.dataset.dataset_id == service.snapshot.dataset_metadata.dataset_id
    assert first.price != second.price


def test_live_quote_does_not_change_backtest() -> None:
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    service = asyncio.run(registry.get(INSTRUMENT.instrument_key))
    before = service.snapshot.backtest["models"]["ewma"]["variance_metrics"]
    RVLiveOverlayBuilder().latest(service.snapshot, INSTRUMENT, quote(20_500), "fresh")

    assert service.snapshot.backtest["models"]["ewma"]["variance_metrics"] == before


def test_quote_on_finalized_session_is_not_provisional() -> None:
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    service = asyncio.run(registry.get(INSTRUMENT.instrument_key))
    same_session = quote(20_500, datetime(2026, 8, 3, 5, 0, tzinfo=UTC))

    latest = RVLiveOverlayBuilder().latest(service.snapshot, INSTRUMENT, same_session, "fresh")

    assert latest.live.is_provisional is False
    assert latest.price == service.snapshot.prices.iloc[-1]


def test_subscription_reference_counts_share_upstream_subscription() -> None:
    asyncio.run(_verify_subscription_reference_counts())


async def _verify_subscription_reference_counts() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=50)

    first = await coordinator.subscribe(INSTRUMENT.instrument_key)
    second = await coordinator.subscribe(INSTRUMENT.instrument_key)
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, first)

    assert provider.subscribes == [(INSTRUMENT.instrument_key,)]
    assert provider.unsubscribes == []

    await coordinator.unsubscribe(INSTRUMENT.instrument_key, second)

    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]


def test_quote_store_marks_last_value_stale_without_removing_it() -> None:
    store = LiveQuoteStore(5)
    observed = datetime.now(UTC) - timedelta(seconds=6)
    state = quote(20_500, observed)
    store.put(state)

    assert store.freshness(INSTRUMENT.instrument_key) == "stale"
    assert store.get(INSTRUMENT.instrument_key) == state

    assert store.put(state) is False
    assert store.get(INSTRUMENT.instrument_key).sequence == 1


def test_multi_instrument_sequences_are_independent_and_monotonic() -> None:
    asyncio.run(_verify_multi_instrument_sequences())


async def _verify_multi_instrument_sequences() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=2, tokens=TokenState())
    second_key = "BSE_INDEX|SENSEX"
    await coordinator.subscribe(INSTRUMENT.instrument_key)
    await coordinator.subscribe(second_key)
    coordinator.receive_provider_message(feed_payload([(INSTRUMENT.instrument_key, 100), (second_key, 200)]))
    coordinator.receive_provider_message(feed_payload([(second_key, 201), (INSTRUMENT.instrument_key, 101)]))

    assert coordinator.quote_store.get(INSTRUMENT.instrument_key).sequence == 2
    assert coordinator.quote_store.get(second_key).sequence == 2
    normalized = normalize_feed_quotes(
        feed_payload([(INSTRUMENT.instrument_key, 102)]),
        requested_keys={INSTRUMENT.instrument_key},
        received_at=datetime.now(UTC),
    )
    assert not hasattr(normalized[0], "sequence")

    invalid = feed_payload([(INSTRUMENT.instrument_key, -1)])
    coordinator.receive_provider_message(invalid)

    assert coordinator.quote_store.get(INSTRUMENT.instrument_key).sequence == 2
    candidates = normalize_feed_quotes(invalid, requested_keys={INSTRUMENT.instrument_key}, received_at=datetime.now(UTC))
    assert candidates == ()


def test_segment_statuses_remain_instrument_specific() -> None:
    asyncio.run(_verify_segment_statuses())


async def _verify_segment_statuses() -> None:
    statuses = normalize_segment_statuses({"marketInfo": {"segmentStatus": {
        "NSE_EQ": "NORMAL_OPEN",
        "BSE_INDEX": "CLOSED",
        "NSE_INDEX": "PRE_OPEN_START",
    }}})
    assert statuses == {"NSE_EQ": "open", "BSE_INDEX": "closed", "NSE_INDEX": "pre_open"}
    assert market_status_for_segment(statuses, "NSE_EQ") == "open"
    assert market_status_for_segment(statuses, "BSE_INDEX") == "closed"
    assert market_status_for_segment(statuses, "BSE_EQ") == "unknown"

    coordinator = MarketDataCoordinator(FakeLiveProvider(), LiveQuoteStore(5), max_active=2, tokens=TokenState())
    nse_queue = await coordinator.subscribe("NSE_EQ|INE002A01018")
    await coordinator.subscribe("BSE_INDEX|SENSEX")
    coordinator.receive_provider_message({"marketInfo": {"segmentStatus": {"BSE_INDEX": "NORMAL_OPEN"}}})

    assert nse_queue.empty()
    assert coordinator.market_status("NSE_EQ|INE002A01018") == "unknown"


def test_subscription_status_remains_instrument_specific() -> None:
    asyncio.run(_verify_subscription_statuses())


async def _verify_subscription_statuses() -> None:
    pending_key = "NSE_EQ|INE002A01018"
    provider = SelectiveLiveProvider(pending_key)
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=2, tokens=TokenState())
    first_queue = await coordinator.subscribe(INSTRUMENT.instrument_key)
    pending = asyncio.create_task(coordinator.subscribe(pending_key))
    await provider.entered.wait()

    assert coordinator.status(INSTRUMENT.instrument_key).subscription_state == "subscribed"
    assert coordinator.status(pending_key).subscription_state == "subscribing"
    assert coordinator.status("BSE_INDEX|UNKNOWN").subscription_state == "unsubscribed"
    assert coordinator.status().subscription_state == "subscribing"

    provider.release.set()
    failure = await asyncio.gather(pending, return_exceptions=True)

    assert isinstance(failure[0], SubscriptionRejected)
    assert coordinator.status(INSTRUMENT.instrument_key).subscription_state == "subscribed"
    assert coordinator.status(pending_key).subscription_state == "unsubscribed"
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, first_queue)


def test_concurrent_subscription_success_shares_readiness() -> None:
    asyncio.run(_verify_concurrent_subscription_success())


async def _verify_concurrent_subscription_success() -> None:
    provider = ControlledLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    first = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await provider.entered.wait()
    second = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await asyncio.sleep(0)

    assert not first.done() and not second.done()
    assert coordinator.subscriber_counts()[INSTRUMENT.instrument_key] == 2
    provider.release.set()
    first_queue, second_queue = await asyncio.gather(first, second)
    assert provider.subscribes == [(INSTRUMENT.instrument_key,)]

    await coordinator.unsubscribe(INSTRUMENT.instrument_key, first_queue)
    assert provider.unsubscribes == []
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, second_queue)
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, second_queue)
    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]
    assert coordinator.subscriber_counts() == {}


def test_concurrent_subscription_failure_cleans_up_and_retries() -> None:
    asyncio.run(_verify_concurrent_subscription_failure())


async def _verify_concurrent_subscription_failure() -> None:
    provider = ControlledLiveProvider(fail=True)
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    first = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await provider.entered.wait()
    second = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await asyncio.sleep(0)
    provider.release.set()
    failures = await asyncio.gather(first, second, return_exceptions=True)

    assert all(isinstance(item, SubscriptionRejected) for item in failures)
    assert failures[0] is failures[1]
    assert provider.subscribes == [(INSTRUMENT.instrument_key,)]
    assert coordinator.subscriber_counts() == {}

    provider.fail = False
    provider.entered = asyncio.Event()
    provider.release = asyncio.Event()
    retry = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await provider.entered.wait()
    provider.release.set()
    queue = await retry
    assert len(provider.subscribes) == 2
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, queue)


def test_capacity_counts_pending_instruments() -> None:
    asyncio.run(_verify_capacity_counts_pending_instruments())


async def _verify_capacity_counts_pending_instruments() -> None:
    provider = ControlledLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    pending = asyncio.create_task(coordinator.subscribe(INSTRUMENT.instrument_key))
    await provider.entered.wait()
    try:
        await coordinator.subscribe("BSE_INDEX|SENSEX")
    except SubscriptionRejected:
        pass
    else:
        raise AssertionError("capacity was not enforced")
    provider.release.set()
    queue = await pending
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, queue)


def test_registry_uses_exchange_local_date_and_refreshes_on_rollover() -> None:
    asyncio.run(_verify_registry_exchange_date_rollover())


async def _verify_registry_exchange_date_rollover() -> None:
    current = [datetime(2026, 8, 3, 20, 0, tzinfo=UTC)]

    class RecordingHistory(FakeHistory):
        def __init__(self):
            super().__init__(prices())
            self.to_dates = []

        async def daily_closes(self, instrument_key, from_date, to_date):
            self.to_dates.append(to_date)
            if len(self.to_dates) > 1:
                extended = pd.concat([self.prices, pd.Series([20_500.0], index=[pd.Timestamp("2026-08-05")])])
                return HistoricalCloseDataset(instrument_key=instrument_key, prices=extended)
            return await super().daily_closes(instrument_key, from_date, to_date)

    history = RecordingHistory()
    registry = InstrumentRVServiceRegistry(
        FakeInstruments(),
        history,
        lookback_years=3,
        cache_seconds=900,
        now=lambda: current[0],
    )
    first = await registry.get(INSTRUMENT.instrument_key)
    assert history.to_dates == [date(2026, 8, 4)]

    current[0] = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    second = await registry.get(INSTRUMENT.instrument_key)

    assert history.to_dates[-1] == date(2026, 8, 5)
    assert first.snapshot.dataset_metadata.dataset_id != second.snapshot.dataset_metadata.dataset_id
    current_quote = quote(20_500, datetime(2026, 8, 5, 5, 0, tzinfo=UTC))
    latest = RVLiveOverlayBuilder().latest(second.snapshot, INSTRUMENT, current_quote, "fresh")
    assert latest.live.is_provisional is False
    assert latest.dataset.dataset_id == second.snapshot.dataset_metadata.dataset_id


def test_websocket_denies_missing_authentication_before_acceptance() -> None:
    asyncio.run(_verify_websocket_authentication_denial())


async def _verify_websocket_authentication_denial() -> None:
    coordinator = MarketDataCoordinator(FakeLiveProvider(), LiveQuoteStore(5), max_active=1, tokens=TokenState(False))
    runtime = SimpleNamespace(coordinator=coordinator, instruments=FakeInstruments())
    websocket = FakeWebSocket(runtime)

    await market_state_stream(websocket, INSTRUMENT.instrument_key)

    assert websocket.accepted is False
    assert websocket.denial.status_code == 401
    assert websocket.sent == []


def test_websocket_denies_unknown_instrument_before_acceptance() -> None:
    asyncio.run(_verify_websocket_unknown_instrument_denial())


async def _verify_websocket_unknown_instrument_denial() -> None:
    coordinator = MarketDataCoordinator(FakeLiveProvider(), LiveQuoteStore(5), max_active=1, tokens=TokenState())
    runtime = SimpleNamespace(coordinator=coordinator, instruments=UnknownInstruments())
    websocket = FakeWebSocket(runtime)

    await market_state_stream(websocket, INSTRUMENT.instrument_key)

    assert websocket.accepted is False
    assert websocket.denial.status_code == 404


def test_websocket_snapshot_is_first_and_disconnect_cleans_subscription() -> None:
    asyncio.run(_verify_websocket_snapshot_and_cleanup())


async def _verify_websocket_snapshot_and_cleanup() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    runtime = SimpleNamespace(
        coordinator=coordinator,
        instruments=FakeInstruments(),
        registry=registry,
        overlay=RVLiveOverlayBuilder(),
        metrics=MarketDataMetrics(),
    )
    websocket = FakeWebSocket(runtime)

    await market_state_stream(websocket, INSTRUMENT.instrument_key)

    assert websocket.accepted is True
    assert websocket.sent[0]["event_type"] == "market_state_snapshot"
    assert websocket.sent[0]["entity_id"] == INSTRUMENT.instrument_key
    assert [item["sequence"] for item in websocket.sent] == sorted(item["sequence"] for item in websocket.sent)
    assert coordinator.subscriber_counts() == {}
    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]
    assert "access_token" not in str(websocket.sent)
    assert "wss://" not in str(websocket.sent)


def test_websocket_subscription_rejection_closes_after_acceptance() -> None:
    asyncio.run(_verify_websocket_subscription_rejection())


async def _verify_websocket_subscription_rejection() -> None:
    provider = ControlledLiveProvider(fail=True)
    provider.release.set()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    runtime = SimpleNamespace(coordinator=coordinator, instruments=FakeInstruments())
    websocket = FakeWebSocket(runtime)

    await market_state_stream(websocket, INSTRUMENT.instrument_key)

    assert websocket.accepted is True
    assert websocket.closed == (4408, "subscription rejected")
    assert coordinator.subscriber_counts() == {}


def test_websocket_provider_failure_closes_and_releases_subscription() -> None:
    asyncio.run(_verify_websocket_provider_failure())


async def _verify_websocket_provider_failure() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    runtime = SimpleNamespace(coordinator=coordinator, instruments=FakeInstruments(), registry=FailingRegistry())
    websocket = FakeWebSocket(runtime)

    await market_state_stream(websocket, INSTRUMENT.instrument_key)

    assert websocket.accepted is True
    assert websocket.closed == (1011, "provider failure")
    assert coordinator.subscriber_counts() == {}
    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]


def test_reconnect_keeps_subscription_and_fresh_quote_clears_staleness() -> None:
    asyncio.run(_verify_reconnect_lifecycle())


async def _verify_reconnect_lifecycle() -> None:
    provider = FakeLiveProvider()
    store = LiveQuoteStore(30)
    coordinator = MarketDataCoordinator(provider, store, max_active=1, tokens=TokenState())
    queue = await coordinator.subscribe(INSTRUMENT.instrument_key)
    coordinator.receive_provider_message(feed_payload([(INSTRUMENT.instrument_key, 20_500)]))
    coordinator.receive_provider_state("connected", None)
    coordinator.receive_provider_state("reconnecting", "provider_error")

    assert store.get(INSTRUMENT.instrument_key).ltp == 20_500
    assert store.freshness(INSTRUMENT.instrument_key) == "stale"
    assert coordinator.status(INSTRUMENT.instrument_key).subscription_state == "subscribed"
    assert provider.unsubscribes == []
    events = [queue.get_nowait()["event_type"] for _ in range(queue.qsize())]
    assert "provider_error" not in events
    assert events.count("feed_status_changed") == 2

    coordinator.receive_provider_state("connected", None)
    coordinator.receive_provider_message(feed_payload([(INSTRUMENT.instrument_key, 20_501)]))

    assert store.freshness(INSTRUMENT.instrument_key) == "fresh"
    assert store.get(INSTRUMENT.instrument_key).ltp == 20_501

    class RecordingStreamer:
        def __init__(self):
            self.subscribes = []

        def subscribe(self, keys, mode):
            self.subscribes.append((keys, mode))

    streamer = RecordingStreamer()
    upstox = UpstoxLiveMarketProvider(tokens=TokenState())
    states = []
    upstox.bind(lambda payload: None, lambda state, error: states.append((state, error)))
    upstox._loop = asyncio.get_running_loop()
    upstox._connected_event = asyncio.Event()
    upstox._streamer = streamer
    upstox._active_keys = {INSTRUMENT.instrument_key}
    upstox._has_connected = True
    upstox._handle_error(RuntimeError("temporary"))
    upstox._handle_reconnecting()
    upstox._handle_open()
    await asyncio.sleep(0)

    assert states == [
        ("reconnecting", "provider_error"),
        ("reconnecting", None),
        ("connected", None),
    ]
    assert len(streamer.subscribes) == 1
    upstox._handle_reconnect_stopped()
    await asyncio.sleep(0)
    assert states[-1] == ("failed", "reconnect_exhausted")
    await coordinator.unsubscribe(INSTRUMENT.instrument_key, queue)


def test_browser_stream_stays_open_during_reconnect() -> None:
    asyncio.run(_verify_browser_stream_stays_open_during_reconnect())


async def _verify_browser_stream_stays_open_during_reconnect() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    runtime = SimpleNamespace(
        coordinator=coordinator,
        instruments=FakeInstruments(),
        registry=registry,
        overlay=RVLiveOverlayBuilder(),
        metrics=MarketDataMetrics(),
    )
    websocket = HoldingWebSocket(runtime)
    stream = asyncio.create_task(market_state_stream(websocket, INSTRUMENT.instrument_key))
    while not websocket.sent:
        await asyncio.sleep(0)
    coordinator.receive_provider_state("reconnecting", "provider_error")
    await asyncio.wait_for(websocket.status_seen.wait(), timeout=1)

    assert stream.done() is False
    assert websocket.closed is None
    assert coordinator.status(INSTRUMENT.instrument_key).subscription_state == "subscribed"
    assert provider.unsubscribes == []

    coordinator.receive_provider_state("connected", None)
    websocket.disconnect.set()
    await stream
    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]


def test_terminal_reconnect_exhaustion_closes_and_cleans_once() -> None:
    asyncio.run(_verify_terminal_reconnect_exhaustion())


async def _verify_terminal_reconnect_exhaustion() -> None:
    provider = FakeLiveProvider()
    coordinator = MarketDataCoordinator(provider, LiveQuoteStore(5), max_active=1, tokens=TokenState())
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    runtime = SimpleNamespace(
        coordinator=coordinator,
        instruments=FakeInstruments(),
        registry=registry,
        overlay=RVLiveOverlayBuilder(),
        metrics=MarketDataMetrics(),
    )
    websocket = EventWebSocket(runtime, "provider_error")
    stream = asyncio.create_task(market_state_stream(websocket, INSTRUMENT.instrument_key))
    while not websocket.sent:
        await asyncio.sleep(0)
    coordinator.receive_provider_state("reconnecting", None)
    coordinator.receive_provider_state("failed", "reconnect_exhausted")
    await stream

    assert any(item["event_type"] == "provider_error" for item in websocket.sent)
    assert websocket.closed == (1011, "provider failure")
    assert provider.unsubscribes == [(INSTRUMENT.instrument_key,)]
    assert coordinator.subscriber_counts() == {}


def test_stream_coalesces_quotes_and_emits_no_unchanged_status() -> None:
    asyncio.run(_verify_stream_coalescing())
    asyncio.run(_verify_unchanged_status_is_silent())


async def _stream_runtime():
    coordinator = MarketDataCoordinator(FakeLiveProvider(), LiveQuoteStore(5), max_active=1, tokens=TokenState())
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    service = await registry.get(INSTRUMENT.instrument_key)
    return SimpleNamespace(
        coordinator=coordinator,
        registry=registry,
        overlay=RVLiveOverlayBuilder(),
        metrics=MarketDataMetrics(),
    ), service


async def _verify_stream_coalescing() -> None:
    runtime, service = await _stream_runtime()
    queue = asyncio.Queue()
    queue.put_nowait({"event_type": "quote_updated"})
    queue.put_nowait({"event_type": "quote_updated"})
    websocket = EventWebSocket(runtime, "quote_updated")

    await _stream(websocket, runtime, service, queue)

    assert [item["event_type"] for item in websocket.sent].count("quote_updated") == 1
    assert websocket.sent[0]["event_type"] == "market_state_snapshot"


async def _verify_unchanged_status_is_silent() -> None:
    runtime, service = await _stream_runtime()
    queue = asyncio.Queue()
    websocket = EventWebSocket(runtime, "never")
    asyncio.get_running_loop().call_later(1.1, websocket.disconnect.set)

    await _stream(websocket, runtime, service, queue)

    assert [item["event_type"] for item in websocket.sent] == ["market_state_snapshot"]


def test_stream_emits_resync_on_exchange_date_rollover() -> None:
    asyncio.run(_verify_stream_rollover())


async def _verify_stream_rollover() -> None:
    runtime, service = await _stream_runtime()

    class RolloverRegistry:
        def __init__(self):
            self.calls = 0
            self.gets = 0

        def exchange_date(self):
            self.calls += 1
            return date(2026, 8, 4) if self.calls == 1 else date(2026, 8, 5)

        async def get(self, instrument_key):
            self.gets += 1
            return service

    rollover = RolloverRegistry()
    runtime.registry = rollover
    websocket = EventWebSocket(runtime, "resync_required")

    await _stream(websocket, runtime, service, asyncio.Queue())

    assert rollover.gets == 1
    assert [item["event_type"] for item in websocket.sent] == ["market_state_snapshot", "resync_required"]


def test_selected_instrument_rv_api_uses_one_finalized_dataset() -> None:
    responses = asyncio.run(_selected_instrument_responses())
    latest, features, backtest, history = responses

    assert {latest.status_code, features.status_code, backtest.status_code, history.status_code} == {200}
    payloads = [response.json() for response in responses]
    assert {payload["instrument"]["instrument_key"] for payload in payloads} == {INSTRUMENT.instrument_key}
    assert len({payload["dataset"]["dataset_id"] for payload in payloads}) == 1
    assert all(not point["is_provisional"] for point in features.json()["points"])


async def _selected_instrument_responses():
    registry = InstrumentRVServiceRegistry(FakeInstruments(), FakeHistory(prices()), lookback_years=3, cache_seconds=900)
    coordinator = MarketDataCoordinator(FakeLiveProvider(), LiveQuoteStore(5), max_active=50)
    runtime = SimpleNamespace(
        instruments=FakeInstruments(),
        registry=registry,
        coordinator=coordinator,
        overlay=RVLiveOverlayBuilder(),
    )
    app.state.live_runtime = runtime
    params = {"instrument_key": INSTRUMENT.instrument_key}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        latest = await client.get("/api/v1/rv/latest", params=params)
        features = await client.get("/api/v1/rv/features", params={**params, "limit": 40})
        backtest = await client.get("/api/v1/rv/backtest/latest", params=params)
        history = await client.get("/api/v1/rv/history", params={**params, "limit": 40})
    return latest, features, backtest, history


def test_instrument_search_api_rejects_short_query() -> None:
    response = asyncio.run(_short_instrument_search())

    assert response.status_code == 422


async def _short_instrument_search():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/instruments/search", params={"query": "N"})
