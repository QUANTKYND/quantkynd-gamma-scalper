import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import httpx

from app.instruments.models import InstrumentDefinition
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.models import HistoricalCloseDataset, LiveQuoteState
from app.market_data.quote_store import LiveQuoteStore
from app.market_data.upstox.history import normalize_daily_closes
from app.market_data.upstox.instruments import normalize_instrument
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
